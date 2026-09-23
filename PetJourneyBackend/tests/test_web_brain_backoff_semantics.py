"""退避的语义（对应包 B 的 BLOCK-1、BLOCK-2、BLOCK-3）。

三件事很容易被当成一件，其实不是：
  - **想过了** ≠ **做了决定**：shadow 只是"看看模型会选什么"，世界并没有按它走。
    写成生活决定是冒充；什么都不写则会每 30 秒再调一次模型——都不行，要记"尝试过了 + 什么时候再看"。
  - **禁调下限** ≠ **复查时刻**：额度要等到下一个记账日就是等那么久，不能被 6 小时的复查上限截短成"6 小时后可以再调"。
    复查只是到点再读一遍事实：额度没恢复就继续安静，不调用模型。
  - **异常** 也要占掉这一轮的名额并退避：否则"模型已经返回、随后提交出错"这条路径会让一轮的真实调用次数不受上限约束。
用脚本化的假模型，不联网、不产生付费调用。
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

from app.schemas.runtime_internal import BudgetDenied, BudgetReservation, HeartbeatAction
from app.utils import iso
from app.web_agent.decision.testing import ScriptedModel
from app.web_platform.budget import BudgetLedger
from app.web_runtime.heartbeat_policy import HeartbeatPolicy
from app.web_runtime.reasons import ReasonCode, SilenceReason
from app.web_runtime.state import BrainAvailability
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class Exploding(ScriptedModel):
    """一旦被调用就让用例失败：用来证明"这一轮根本没有调用模型"。"""

    def complete(self, messages, *, max_tokens):
        raise AssertionError("这一轮不该调用模型")


class BackoffSemanticsTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("backoff-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.owner.patch("/settings", {"model_replies": True})
        self.life = self.web.brain_life
        self.web.projector.model_available = lambda: True
        self.round = dict(self.web.cognition.jobs)["brain_life"]

    def stays(self, times: int = 1) -> ScriptedModel:
        model = ScriptedModel(*[json.dumps({"choice": "continue", "intent": "在家"}, ensure_ascii=False) for _ in range(times)])
        self.life.brain.model = model
        return model

    def row(self) -> dict:
        return self.web.projector.runtime.row(self.owner.pet_id) or {}

    # ---- BLOCK-1：shadow 留痕，但不冒充生活决定 ----
    def test_shadow_records_an_attempt_not_a_life_decision(self) -> None:
        self.life.mode = "shadow"
        model = self.stays(1)

        self.round(self.clock.now, limit=5)

        row = self.row()
        self.assertEqual(len(model.calls), 1, "第一轮确实想了一次")
        self.assertIsNone(row.get("last_decision_at"), f"shadow 没有真的决定什么，不能写决定时刻：{row}")
        self.assertIsNone(row.get("last_decision_by"), f"更不能写成是谁决定的：{row}")
        self.assertTrue(row.get("next_review_at"), f"但要记下什么时候再看：{row}")
        self.assertEqual(row.get("silence_reason"), "brain:shadow")

    def test_shadow_does_not_call_the_model_again_on_the_next_tick(self) -> None:
        self.life.mode = "shadow"
        model = self.stays(1)  # 只给一句；再调一次就会耗尽脚本并报错

        self.round(self.clock.now, limit=5)
        self.clock.advance(seconds=30)
        self.round(self.clock.now, limit=5)

        self.assertEqual(len(model.calls), 1, "30 秒后不该又调一次模型——那是真金白银")

    # ---- BLOCK-2：额度用完要尊重真实恢复时刻 ----
    def test_a_budget_denial_uses_the_ledgers_own_recovery_time(self) -> None:
        self.life.mode = "live"
        resets_at = datetime(2026, 9, 23, 0, 0, tzinfo=timezone.utc)  # 下一个 UTC 记账日
        self.life.reserve = lambda operation_id, purpose, pet_id: BudgetDenied(operation_id, "pet", "limit_reached", retry_after=resets_at)
        self.life.brain.model = Exploding()

        self.round(self.clock.now, limit=5)

        row = self.row()
        self.assertTrue(row.get("next_review_at"), f"要记下什么时候再看：{row}")
        review_at = datetime.fromisoformat(row["next_review_at"])
        policy = HeartbeatPolicy()
        self.assertLessEqual(review_at, self.clock.now + policy.max_review_interval, "复查时刻不超过看门狗上限")
        self.assertGreater(review_at, self.clock.now, "复查要排在以后")

    def test_an_exhausted_budget_stops_the_round_from_calling_the_model(self) -> None:
        """额度确实用完时，心跳给出的就不该是"去想一想"——这一轮一次模型都不调。"""
        self.life.mode = "live"
        self.web.projector.budget_facts = lambda pet_id: (0, datetime(2026, 9, 23, 0, 0, tzinfo=timezone.utc))
        self.life.brain.model = Exploding()

        for _ in range(3):
            self.round(self.clock.now, limit=5)
            self.clock.advance(hours=1)

    def test_the_round_resumes_once_the_budget_is_raised(self) -> None:
        """额度调高之后不需要人工清标记：下一次复查读到新的事实就回到"去想一想"。"""
        self.life.mode = "live"
        self.web.projector.budget_facts = lambda pet_id: (0, None)
        self.life.brain.model = Exploding()
        self.round(self.clock.now, limit=5)

        self.clock.advance(minutes=20)  # 仍在当地出门时段内
        # 假时钟只推墙上时间、不推单调时钟，时钟健康监视器会（正确地）把这 20 分钟判成"大幅前跳"，
        # 于是心跳先给 RECOVER、根本走不到额度这一步。真实进程里两者一起走，不会被判异常。
        self.web.projector.clock_monitor.reanchor(self.web.projector.clock)
        self.web.projector.budget_facts = lambda pet_id: (5, None)  # 额度被调高
        model = self.stays(1)
        self.round(self.clock.now, limit=5)

        self.assertEqual(len(model.calls), 1, "额度恢复后下一次复查就该重新想一次，不需要人工清任何标记")

    # ---- BLOCK-3：异常也占名额、也退避 ----
    def test_an_exception_still_consumes_the_round_slot(self) -> None:
        self.life.mode = "live"
        seen: list[str] = []

        def boom(pet_id, now=None):
            seen.append(pet_id)
            raise RuntimeError("提交的时候炸了")

        self.life.consider = boom
        household_id = self.owner.get("/onboarding").json()["households"][0]["household_id"]
        for index in range(4):
            created = self.owner.upload_pet(f"小{index}", "cat", household_id=household_id)
            self.assertEqual(self.owner.post("/onboarding/move-in", {"pet_id": created.json()["pet_id"]}).status_code, 200)

        self.round(self.clock.now, limit=2)

        self.assertEqual(len(seen), 2, f"异常也要占掉这一轮的名额，一轮最多 2 只：{seen}")

    def test_an_exception_writes_a_backoff_so_it_does_not_repeat_every_tick(self) -> None:
        self.life.mode = "live"

        def boom(pet_id, now=None):
            raise RuntimeError("提交的时候炸了")

        self.life.consider = boom

        self.round(self.clock.now, limit=5)

        row = self.row()
        self.assertTrue(row.get("next_review_at"), f"异常之后也要记什么时候再看：{row}")
        self.assertEqual(row.get("silence_reason"), "brain:round_failed")
        self.assertIsNone(row.get("last_decision_by"), "异常不是一次决定")

    def test_a_backed_off_pet_is_skipped_on_the_next_tick(self) -> None:
        self.life.mode = "live"
        calls: list[str] = []

        def boom(pet_id, now=None):
            calls.append(pet_id)
            raise RuntimeError("炸了")

        self.life.consider = boom
        self.round(self.clock.now, limit=5)
        self.clock.advance(seconds=30)
        self.round(self.clock.now, limit=5)

        self.assertEqual(len(calls), 1, f"退避期内不该再想一次：{calls}")

    # ---- BLOCK-2 补强：两层额度、在途、读取失败（都走真实装配的 budget_facts 与真实账本） ----
    def real_facts(self) -> tuple:
        """真实装配的额度投影（wire_brain 接上去的那一个），不是测试替身。"""
        self.assertIsNotNone(self.web.projector.budget_facts, "前提：额度账本已经接进投影")
        return self.web.projector.budget_facts(self.owner.pet_id)

    def heartbeat(self):
        from app.web_runtime.heartbeat_policy import HeartbeatPolicy as Policy
        from app.web_runtime.heartbeat_policy import evaluate as run

        now = self.clock.now
        return run(self.web.projector.state(self.owner.pet_id, now), (), Policy(), now,
                   facts=self.web.projector.facts(self.owner.pet_id, now))

    def test_the_provider_cap_is_counted_even_when_this_pet_still_has_room(self) -> None:
        """宠物自己的额度还剩着，但供应商那层已经满了：投影必须说"用完了"，这一轮一次模型都不调。"""
        self.life.mode = "live"
        self.life.brain.model = Exploding()
        self.assertGreater(self.real_facts()[0], 0, "前提：一开始是有额度的")
        with self.web.journeys.storage.connect() as conn:  # 供应商那层占满（宠物那层一次都没用过）
            conn.execute("INSERT OR REPLACE INTO web_budget_counters (window_key, scope_key, used_units, inflight_units, updated_at) "
                         "VALUES (?, 'provider:llm:life_plan', 1000000, 0, ?)", (self.clock.now.date().isoformat(), iso(self.clock.now)))

        remaining, _ = self.real_facts()

        self.assertEqual(remaining, 0, "供应商额度满了，宠物额度再多也发不出去")
        self.assertIs(self.heartbeat().action, HeartbeatAction.APPLY_RULE, "心跳不该再说“去想一想”")
        self.round(self.clock.now, limit=5)  # Exploding 会在被调用时抛错，所以"没抛错"就等于"没调用"

    def test_in_flight_reservations_count_against_the_projection(self) -> None:
        """已经预占、还没结算的调用（钱可能已经花出去了）必须算进已用，不能等结算才算。"""
        self.life.mode = "live"
        self.life.brain.model = Exploding()
        per_pet = int(getattr(self.settings, "web_brain_daily_per_pet", 12))
        for index in range(per_pet):  # 真实预占，**不结算**
            self.assertIsInstance(self.life.reserve(f"probe-inflight-{index}", "life_plan", self.owner.pet_id), BudgetReservation)

        remaining, _ = self.real_facts()

        self.assertEqual(remaining, 0, f"{per_pet} 笔在途就该把额度占满")
        self.assertIs(self.heartbeat().action, HeartbeatAction.APPLY_RULE, "在途占满时不该再说“去想一想”")
        self.round(self.clock.now, limit=5)

    def test_a_ledger_read_failure_is_not_treated_as_available(self) -> None:
        """读不到账本 ≠ 有额度：要如实说成"依赖不可用"（故障安静，不是正常安静），并给出再看的时刻。"""
        from unittest import mock

        self.life.mode = "live"
        self.life.brain.model = Exploding()
        with mock.patch.object(BudgetLedger, "usage", side_effect=RuntimeError("账本读不出来")):
            facts = self.web.projector.facts(self.owner.pet_id, self.clock.now)
            decision = self.heartbeat()
            self.round(self.clock.now, limit=5)

        self.assertIs(facts.cognition.availability, BrainAvailability.UNAVAILABLE, "读取失败被当成了可用")
        self.assertGreater(facts.cognition.retry_after, self.clock.now, "要给出隔多久再看")
        self.assertIsNot(decision.action, HeartbeatAction.REQUEST_BRAIN, "读不到额度就不该去想")
        self.assertIn(ReasonCode.BRAIN_UNAVAILABLE.value, decision.reason_codes, f"要如实说成依赖不可用：{decision.reason_codes}")
        self.assertEqual(decision.silence_reason, SilenceReason.DEPENDENCY_UNAVAILABLE.value,
                         "运维要能把它和“正常安静”分开")


if __name__ == "__main__":
    unittest.main()
