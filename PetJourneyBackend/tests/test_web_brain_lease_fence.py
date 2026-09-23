"""进程租约围栏：被接手的旧执行者必须立刻停手（验收 CR-A4）。

同一时刻只有一个进程推进世界。旧进程失去租约之后，**它已经不是世界的推进者了**——
这时它再写任何东西都是在替新任期做决定。所以租约失效不是"这次没想成"：
  - 不写退避（那等于替新任期决定什么时候再想）；
  - 不清空这一轮的决策编号（新任期要靠同一个编号复用预占、不重复扣费）；
  - 不写生活决定、不让 TA 出门；
  - 本轮就此结束：同一任务里排在后面的宠物、以及这一轮后面的任务，都不再处理。
**已经发出的模型调用记录要留着**：额度账本不受租约围栏约束，预占与结算照常落库，
合法执行者据此对账，再决定要不要重来。

注入方式是真实的：直接把数据库里 web_worker_leases 的持有者改成另一个进程，
和真的被接管一模一样，再让真实装配（WorldTicker → 认知线 → BrainLife → C 的 unit_of_work）跑下去。
用脚本化的假模型，不联网、不产生付费调用。
"""

from __future__ import annotations

import json
import unittest
from datetime import timedelta

from app.utils import iso
from app.web_agent.decision import destination_key_of, offers_from_options
from app.web_agent.decision.testing import ScriptedModel
from app.web_agent.ticker import WorldTicker
from app.web_journey.local import job_of
from app.web_platform.budget import BudgetLedger
from app.web_platform.lease import LeaseLost, assert_lease_held
from app.web_platform.uow import lane_fence
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase

OTHER_PROCESS = "another-host:999#newtenure"


class BrainLeaseFenceTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("lease-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.owner.patch("/settings", {"model_replies": True})
        self.life = self.web.brain_life
        self.life.mode = "live"
        self.web.projector.model_available = lambda: True
        # 兜底：任何一个用例都不可能走到真实供应商（没有剧本就抛错），确保全程零付费调用
        self.life.brain.model = ScriptedModel(RuntimeError("这个用例不该调用模型"))
        self.storage = self.web.journeys.storage
        self.ran: list[str] = []  # 本轮后面的任务有没有被执行到
        self.web.cognition.jobs.append(("after_brain", lambda now: self.ran.append("after_brain")))
        self.considered: list[str] = []
        original = self.life.consider
        self.life.consider = lambda pet_id, now=None: (self.considered.append(pet_id), original(pet_id, now))[1]

    # ---- 注入与读取 ----
    def take_over(self, lane: str) -> None:
        """另一个进程接手了这条线：只改数据库里的持有者与期限，和真实接管走同一张表。"""
        ticker = self.web.ticker if lane == "world" else self.web.cognition
        self.assertTrue(ticker.lease.acquire(self.clock.now), f"先建起 {lane} 这条线的租约行（已持有时就是一次续期）")
        with self.storage.connect() as conn:
            changed = conn.execute("UPDATE web_worker_leases SET holder = ?, expires_at = ? WHERE name = ?",
                                   (OTHER_PROCESS, iso(self.clock.now + timedelta(hours=1)), lane)).rowcount
        self.assertEqual(changed, 1, f"注入没生效：{lane} 这条线还没有租约行")

    def stale_fence(self, lane: str):
        """旧任期的围栏闭包：和 WorldTicker.tick 里装的是同一个（assert_lease_held ＋ 本任期标识）。"""
        return lambda conn: assert_lease_held(conn, lane, "old-tenure-that-was-taken-over")

    def row(self, pet_id: str) -> dict:
        return dict(self.web.projector.runtime.row(pet_id) or {})

    def second_pet(self) -> str:
        household_id = self.owner.get("/onboarding").json()["households"][0]["household_id"]
        created = self.owner.upload_pet("小二", "cat", household_id=household_id)
        self.assertEqual(created.status_code, 201, created.text)
        pet_id = created.json()["pet_id"]
        self.assertEqual(self.owner.post("/onboarding/move-in", {"pet_id": pet_id}).status_code, 200)
        return pet_id

    def stroll_reply(self, pet_id: str) -> str:
        options = self.web.journeys.destinations(self.owner.user_id, pet_id, self.owner.home_id, self.clock.now)
        keys = [destination_key_of(o) for o in offers_from_options(
            options, pet_id=pet_id, as_of=self.clock.now, expected_versions=self.web.projector.versions(pet_id),
            income_of=lambda key: job_of(key).pay if job_of(key) else 0)]
        return json.dumps({"choice": f"o{keys.index('local:stroll') + 1}", "intent": "出去走走"}, ensure_ascii=False)

    def assert_nothing_written(self, pet_id: str, *, expect_operation_id: bool = True) -> None:
        """旧执行者什么都没往世界里写；只有"这次调用发生过"的痕迹留着给新任期对账。"""
        row = self.row(pet_id)
        self.assertIsNone(self.web.journeys.repo.active_for_pet(pet_id), f"不能出发：{row}")
        self.assertIsNone(row.get("next_review_at"), f"租约没了不能替新任期写退避：{row}")
        self.assertIsNone(row.get("last_decision_at"), f"没做成决定就不能写成生活决定：{row}")
        self.assertIsNone(row.get("last_decision_by"), f"没做成决定就不能写决定人：{row}")
        self.assertNotIn(str(row.get("silence_reason") or ""), ("brain:round_failed", "brain:evaluate_failed"),
                         f"租约失效被当成了普通模型失败：{row}")
        if expect_operation_id:
            self.assertTrue(row.get("decision_operation_id"), f"这一轮的决策编号要留给合法执行者复用：{row}")

    # ---- 认知线：模型答完之后失去租约 ----
    def test_losing_the_lease_after_the_model_answered_stops_the_old_executor(self) -> None:
        self.second_pet()
        pet = self.owner.pet_id
        model = ScriptedModel(self.stroll_reply(pet), on_call=lambda _n: self.take_over("cognition"))
        self.life.brain.model = model

        self.web.cognition.tick(self.clock.now)  # 真实装配：租约 → lane_fence → 认知线各任务

        self.assertEqual(len(model.calls), 1, "模型确实答完了一次（注入点在答完之后）")
        self.assertEqual(len(self.considered), 1, f"本轮必须就此停住，不再处理后面的宠物：{self.considered}")
        self.assertEqual(self.ran, [], "本轮后面的任务也不该再跑")
        self.assert_nothing_written(self.considered[0])

    def test_the_issued_model_call_is_still_on_the_books_for_the_next_holder(self) -> None:
        pet = self.owner.pet_id
        self.life.brain.model = ScriptedModel(self.stroll_reply(pet), on_call=lambda _n: self.take_over("cognition"))

        self.web.cognition.tick(self.clock.now)

        operation_id = self.row(pet).get("decision_operation_id")
        reservation = BudgetLedger(self.storage).get(operation_id)
        self.assertIsNotNone(reservation, f"已经发出的模型调用必须留在账本里：{operation_id}")
        self.assertEqual(reservation.status, "settled", f"结算不走租约围栏，钱花了就要记上：{reservation}")

    def test_an_ordinary_model_failure_still_backs_off_and_keeps_going(self) -> None:
        """对照组：普通失败仍按原样退避，并继续处理后面的宠物——租约的改动没有把它一起改掉。"""
        self.second_pet()
        self.life.brain.model = ScriptedModel(RuntimeError("模型这次挂了"), RuntimeError("第二只也挂了"))

        self.web.cognition.tick(self.clock.now)

        self.assertEqual(len(self.considered), 2, f"普通失败不该终止本轮：{self.considered}")
        self.assertEqual(self.ran, ["after_brain"], "本轮后面的任务照常跑")
        row = self.row(self.considered[0])
        self.assertTrue(row.get("next_review_at"), f"普通失败要写退避：{row}")
        # 编号**留着**不是租约的事：模型调用抛异常时账本判成 unknown（可能已被受理），
        # 结果未明就不能换新编号重发，下一轮必须沿用同一个（CR-Q14，见 test_web_brain_decision_recovery）。
        self.assertTrue(row.get("decision_operation_id"), f"结果未明时要留着编号：{row}")

    # ---- 留家提交 ----
    def test_the_stay_home_commit_is_refused_when_the_lease_is_gone(self) -> None:
        """"留在家里"也是一次真的决定，同样要过租约围栏（与 C 的 unit_of_work 对齐）。"""
        pet = self.owner.pet_id
        model = ScriptedModel(json.dumps({"choice": "continue", "intent": "今天想在家"}, ensure_ascii=False),
                              on_call=lambda _n: self.take_over("cognition"))
        self.life.brain.model = model

        self.web.cognition.tick(self.clock.now)

        self.assertEqual(len(model.calls), 1)
        self.assert_nothing_written(pet)

    def test_the_runtime_writes_themselves_refuse_to_run_without_the_lease(self) -> None:
        """退避、尝试、关闭编号、留家提交：四个写入口在围栏下都必须抛 LeaseLost 且什么都没写。"""
        pet = self.owner.pet_id
        runtime = self.web.projector.runtime
        now = self.clock.now
        versions = self.web.projector.versions(pet)
        self.take_over("cognition")  # 租约行由 take_over 自己建起，不跑任何一轮，免得先把这个时段用掉
        calls = {
            "record_backoff": lambda: runtime.record_backoff(pet, now, review_at=now + timedelta(minutes=15), reason="brain:probe"),
            "record_attempt": lambda: runtime.record_attempt(pet, now, review_at=now + timedelta(minutes=15), reason="brain:probe"),
            "close_decision": lambda: runtime.close_decision(pet, now),
            "record_decision": lambda: runtime.record_decision(pet, now, by="model", next_review_at=None),
            "record_decision_checked": lambda: runtime.record_decision_checked(pet, now, by="model", next_review_at=None, expected=versions),
            "open_decision": lambda: runtime.open_decision(pet, now, new_id=lambda: "probe"),
        }
        with lane_fence(self.stale_fence("cognition")):
            for name, call in calls.items():
                with self.subTest(write=name), self.assertRaises(LeaseLost, msg=f"{name} 在租约失效后仍然写了库"):
                    call()
        self.assert_nothing_written(pet, expect_operation_id=False)
        self.assertIsNone(self.row(pet).get("decision_operation_id"), "open_decision 也不能在租约失效后开新编号")

    def test_the_stay_home_version_check_still_works_when_the_lease_is_held(self) -> None:
        """对照组：围栏装着但租约还在自己手上时，同事务的版本复核照旧有效（没有被围栏盖掉）。"""
        pet = self.owner.pet_id
        runtime = self.web.projector.runtime
        stale = self.web.projector.versions(pet)
        self.assertTrue(self.web.cognition.lease.acquire(self.clock.now), "先让这条线建起自己的租约行")
        fence = lambda conn: assert_lease_held(conn, "cognition", self.web.cognition.lease.tenure())  # noqa: E731
        self.owner.patch("/settings", {"model_replies": False})  # 撤权：privacy_epoch 前进一代

        with lane_fence(fence):
            moved = runtime.record_decision_checked(pet, self.clock.now, by="model", next_review_at=None, expected=stale)

        self.assertIn("privacy_epoch", moved, f"旧版本的提案必须被挡下：{moved}")
        self.assertIsNone(self.row(pet).get("last_decision_at"), "被挡下就不能写成决定")

    # ---- 世界线 ----
    def test_the_rule_life_round_stops_instead_of_skipping_to_the_next_pet(self) -> None:
        self.second_pet()
        self.life.mode = "off"  # 世界照旧由规则生活推进
        self.take_over("world")
        self.assertFalse(self.web.projector.runtime.row(self.owner.pet_id).get("next_review_at"), "前提：这个时段还没被用掉")

        with lane_fence(self.stale_fence("world")), self.assertRaises(LeaseLost):
            self.web.life.run(self.clock.now)

        self.assertIsNone(self.web.journeys.repo.active_for_pet(self.owner.pet_id), "旧执行者不能把 TA 送出门")

    def test_the_ticker_skips_the_rest_of_the_round_on_lease_loss(self) -> None:
        done: list[str] = []
        ticker = WorldTicker([("first", lambda now: done.append("first")),
                              ("lost", lambda now: (_ for _ in ()).throw(LeaseLost("world", "taken_over"))),
                              ("third", lambda now: done.append("third"))], interval_seconds=0)

        self.assertTrue(ticker.tick(self.clock.now))

        self.assertEqual(done, ["first"], "租约失效之后，这一轮剩下的任务都不该再跑")


if __name__ == "__main__":
    unittest.main()
