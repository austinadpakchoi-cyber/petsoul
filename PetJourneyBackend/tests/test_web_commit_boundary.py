"""最终提交的边界：外部解析在事务外，复核在事务内、用同一个连接（CR-C1 / CR-A4）。

出发这件事分两段：先解析地点、算路线（要调地图，慢，必须在事务外），再写库。
中间这段时间里，家人可能撤回授权、改了 DNA、TA 的活动变了，或者这个打算本身已经过了时效。
所以**写之前的最后一刻**还要再核一遍——而且必须用写事务里的那个连接：
另开连接读到的是事务开始前的旧快照，还会和自己的写事务争锁，那样的"复核"既不准也会卡住。

这里在 `journeys.resolve`（外部解析）执行期间注入变化，看旧提案会不会仍被写进去。
"留在家里"同样是一次真的决定，走同一条复核。
用脚本化的假模型与假地图，不联网、不产生付费调用。
"""

from __future__ import annotations

import json
import unittest
from datetime import timedelta

from app.schemas.base import EconomyTransactionType
from app.web_agent.decision import destination_key_of, offers_from_options
from app.web_agent.decision.testing import ScriptedModel
from app.web_journey.errors import JourneyError
from app.web_journey.local import job_of
from app.web_platform.runtime_epochs import bump_in
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class CommitBoundaryBase(WebPlatformTestBase):
    """真实网页服务 + 一次性临时库 + 假模型；`tests/test_web_fare_settlement.py` 也用这一套工具。"""

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("boundary-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.owner.patch("/settings", {"model_replies": True})
        self.life = self.web.brain_life
        self.life.mode = "live"
        self.web.projector.model_available = lambda: True

    # ---- 工具 ----
    def offers(self):
        now = self.clock.now
        options = self.web.journeys.destinations(self.owner.user_id, self.owner.pet_id, self.owner.home_id, now)
        return list(offers_from_options(options, pet_id=self.owner.pet_id, as_of=now, expected_versions=self.web.projector.versions(self.owner.pet_id),
                                        income_of=lambda key: job_of(key).pay if job_of(key) else 0))

    def model_picks(self, key: str) -> None:
        keys = [destination_key_of(o) for o in self.offers()]
        alias = "continue" if key == "continue" else f"o{keys.index(key) + 1}"
        self.life.brain.model = ScriptedModel(json.dumps({"choice": alias, "intent": "出去走走"}, ensure_ascii=False))

    def during_resolve(self, change) -> None:
        """在外部解析（地图、地点）期间改变世界：这正是"提案已经做出、还没写库"的那段时间。"""
        original = self.web.journeys.resolve

        def resolved(*args, **kwargs):
            change()
            return original(*args, **kwargs)

        self.web.journeys.resolve = resolved

    def bump(self, field: str):
        def change() -> None:
            with self.app.state.storage.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                bump_in(conn, self.owner.pet_id, field, self.clock.now)

        return change

    def active(self):
        return self.web.journeys.repo.active_for_pet(self.owner.pet_id)

    def runtime_row(self) -> dict:
        return self.web.projector.runtime.row(self.owner.pet_id) or {}

    def coins(self, amount: int) -> None:
        self.web.economy.apply(self.owner.pet_id, amount, EconomyTransactionType.web_reward, f"test:topup:{amount}",
                               reason="测试用旅费", source="test.commit_boundary", now=self.clock.now)

    def balance(self) -> int:
        return self.web.economy.wallet(self.owner.pet_id).balance

    def fares(self) -> list[str]:
        with self.app.state.storage.connect() as conn:
            return [row["idempotency_key"] for row in
                    conn.execute("SELECT idempotency_key FROM economy_transactions WHERE pet_id = ? AND idempotency_key LIKE 'web:travel_fee:%'",
                                 (self.owner.pet_id,))]

    def journey_rows(self) -> int:
        """任何状态的行程条数——取消掉的也算，回滚应当连一条取消记录都不留。"""
        with self.app.state.storage.connect() as conn:
            return conn.execute("SELECT COUNT(*) AS n FROM web_journeys WHERE pet_id = ?", (self.owner.pet_id,)).fetchone()["n"]


class CommitBoundaryTests(CommitBoundaryBase):
    # ---- 出发：解析期间世界变了 ----
    def test_authorization_revoked_while_resolving_does_not_depart(self) -> None:
        self.model_picks("local:stroll")
        self.during_resolve(self.bump("privacy_epoch"))

        outcome = self.life.consider(self.owner.pet_id, self.clock.now)

        self.assertEqual(outcome.status, "rejected", f"撤权之后不能再按旧提案出门：{outcome}")
        self.assertTrue((outcome.reason or "").startswith("versions_changed"), outcome.reason)
        self.assertIsNone(self.active(), "一趟行程都不该建出来")

    def test_a_dna_change_while_resolving_does_not_depart(self) -> None:
        self.model_picks("local:stroll")
        self.during_resolve(lambda: self.owner.put(f"/pets/{self.owner.pet_id}/dna",
                                                   {"owner_title": "姐姐", "personality": "换了个说法", "catchphrase": "喵"}))

        outcome = self.life.consider(self.owner.pet_id, self.clock.now)

        self.assertEqual(outcome.status, "rejected", f"DNA 变了，旧提案不作数：{outcome}")
        self.assertIsNone(self.active())

    def test_activity_change_while_resolving_does_not_depart(self) -> None:
        self.model_picks("local:stroll")
        self.during_resolve(self.bump("activity_epoch"))

        outcome = self.life.consider(self.owner.pet_id, self.clock.now)

        self.assertEqual(outcome.status, "rejected", f"活动版本变了：{outcome}")
        self.assertIsNone(self.active())

    def test_an_offer_that_expires_while_resolving_does_not_depart(self) -> None:
        self.model_picks("local:stroll")
        self.during_resolve(lambda: self.clock.advance(minutes=11))  # 机会只有 10 分钟

        outcome = self.life.consider(self.owner.pet_id, self.clock.now)

        self.assertIn(outcome.status, ("rejected", "failed"), f"过了时效不能再出门：{outcome}")
        self.assertIsNone(self.active())

    def test_the_normal_path_still_departs(self) -> None:
        """复核只挡住真的变了的情况，正常路径不能被误拒。"""
        self.model_picks("local:stroll")

        outcome = self.life.consider(self.owner.pet_id, self.clock.now)

        self.assertEqual((outcome.status, outcome.composed_by), ("departed", "model"), outcome.reason)
        self.assertEqual(self.active().destination_key, "local:stroll")

    # ---- 留在家里也是一次真的决定 ----
    def test_staying_home_is_rejected_when_revoked_while_the_model_was_thinking(self) -> None:
        """撤权发生在模型思考期间：提案已经做出，但写"留在家里"之前的复核要挡住它。"""
        keys = [destination_key_of(o) for o in self.offers()]
        assert keys  # 前提：确实有可行机会
        self.life.brain.model = ScriptedModel(json.dumps({"choice": "continue", "intent": "在家"}, ensure_ascii=False),
                                              on_call=lambda _n: self.bump("privacy_epoch")())

        outcome = self.life.consider(self.owner.pet_id, self.clock.now)

        self.assertNotEqual(outcome.status, "stayed", f"撤权之后不能写成一次生活决定：{outcome}")
        self.assertIsNone(self.runtime_row().get("last_decision_by"), "没有决定就不能记谁决定的")
        self.assertTrue(self.runtime_row().get("next_review_at"), "被挡下也要记什么时候再看")

    def test_record_decision_checked_refuses_a_stale_version_inside_its_own_transaction(self) -> None:
        """写"留在家里"的那一步本身：用事务里的同一个连接复核，版本对不上就一个字都不写。"""
        runtime = self.web.projector.runtime
        stale = self.web.projector.versions(self.owner.pet_id)
        self.bump("privacy_epoch")()

        changed = runtime.record_decision_checked(self.owner.pet_id, self.clock.now, by="model", next_review_at=None, expected=stale)

        self.assertEqual(changed, ["privacy_epoch"], changed)
        self.assertIsNone(self.runtime_row().get("last_decision_at"), "被拒的那次不能留下痕迹")
        fresh = self.web.projector.versions(self.owner.pet_id)
        self.assertEqual(runtime.record_decision_checked(self.owner.pet_id, self.clock.now, by="model", next_review_at=None, expected=fresh), [])
        self.assertEqual(self.runtime_row().get("last_decision_by"), "model", "版本对得上就照常写")

    def test_staying_home_on_the_normal_path_is_recorded(self) -> None:
        self.model_picks("continue")

        outcome = self.life.consider(self.owner.pet_id, self.clock.now)

        self.assertEqual(outcome.status, "stayed", outcome.reason)
        self.assertEqual(self.runtime_row().get("last_decision_by"), "model")

    # ---- 直接调用出发接口时的复核（不经过大脑） ----
    def test_depart_rejects_a_stale_version_from_any_caller(self) -> None:
        stale = self.web.projector.versions(self.owner.pet_id)
        with self.app.state.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            bump_in(conn, self.owner.pet_id, "membership_epoch", self.clock.now)

        with self.assertRaises(JourneyError) as rejected:
            self.web.journeys.depart(self.owner.user_id, self.owner.pet_id, self.owner.home_id, "local:stroll", self.clock.now,
                                     expected_versions=stale)

        self.assertEqual(rejected.exception.reason, "versions_changed")
        self.assertIsNone(self.active())


    def test_depart_rejects_an_expired_window_from_any_caller(self) -> None:
        with self.assertRaises(JourneyError) as rejected:
            self.web.journeys.depart(self.owner.user_id, self.owner.pet_id, self.owner.home_id, "local:stroll", self.clock.now,
                                     valid_until=self.clock.now - timedelta(seconds=1))

        self.assertEqual(rejected.exception.reason, "offer_expired")
        self.assertIsNone(self.active())


if __name__ == "__main__":
    unittest.main()
