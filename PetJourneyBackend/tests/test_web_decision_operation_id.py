"""一轮自主决策的逻辑编号（对应包 A 的 CR-A2）。

编号是额度预占的操作号。如果每次重试都现生成一个新编号，同一轮思考崩溃后重来就会**再预占一次**，
额度按两次算，包 A 的重放保护（同编号在途 → 拒绝；已结算 → 原样返回）也永远触发不了。
所以编号在第一次创建后要存下来：重试、换进程重启、跨过整分钟再回来，都复用同一个；
这一轮有了明确结果才清掉，下一轮才是真正的新编号。
用脚本化的假模型，不联网、不产生付费调用。
"""

from __future__ import annotations

import json
import unittest
from datetime import timedelta

from app.web_agent.decision import destination_key_of, offers_from_options
from app.web_agent.decision.testing import ScriptedModel
from app.web_journey.local import job_of
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class DecisionOperationIdTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("opid-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.owner.patch("/settings", {"model_replies": True})
        self.life = self.web.brain_life
        self.life.mode = "live"
        self.web.projector.model_available = lambda: True
        self.reserved: list[str] = []
        real_reserve = self.life.reserve

        def watched(operation_id, purpose, pet_id):
            self.reserved.append(operation_id)
            return real_reserve(operation_id, purpose, pet_id) if real_reserve else None

        self.life.reserve = watched

    def stroll_reply(self) -> str:
        options = self.web.journeys.destinations(self.owner.user_id, self.owner.pet_id, self.owner.home_id, self.clock.now)
        keys = [destination_key_of(o) for o in offers_from_options(
            options, pet_id=self.owner.pet_id, as_of=self.clock.now, expected_versions=self.web.projector.versions(self.owner.pet_id),
            income_of=lambda key: job_of(key).pay if job_of(key) else 0)]
        return json.dumps({"choice": f"o{keys.index('local:stroll') + 1}", "intent": "出去走走"}, ensure_ascii=False)

    def open_id(self) -> str | None:
        return (self.web.projector.runtime.row(self.owner.pet_id) or {}).get("decision_operation_id")

    def test_a_crash_mid_decision_reuses_the_same_operation_id(self) -> None:
        self.life.brain.model = ScriptedModel(SystemExit("写回结果之前进程挂了"))
        with self.assertRaises(SystemExit):
            self.life.consider(self.owner.pet_id, self.clock.now)
        first = self.open_id()
        self.assertTrue(first, "崩溃时编号要留在运行记录里，才能让重试认出这是同一轮")

        self.clock.advance(minutes=2)  # 跨过整分钟再回来
        self.life.brain.model = ScriptedModel(self.stroll_reply())
        self.life.consider(self.owner.pet_id, self.clock.now)

        self.assertEqual(self.reserved, [first, first], f"重试要复用同一个编号：{self.reserved}")

    def test_a_finished_decision_starts_a_fresh_id_next_time(self) -> None:
        self.life.brain.model = ScriptedModel(json.dumps({"choice": "continue", "intent": "在家"}, ensure_ascii=False))
        self.life.consider(self.owner.pet_id, self.clock.now)
        self.assertIsNone(self.open_id(), "这一轮有结果了，编号要清掉")

        self.clock.advance(hours=1)
        self.life.brain.model = ScriptedModel(self.stroll_reply())
        self.life.consider(self.owner.pet_id, self.clock.now)

        self.assertEqual(len(self.reserved), 2)
        self.assertNotEqual(self.reserved[0], self.reserved[1], "真正的新一轮才用新编号")

    def test_time_alone_never_rotates_an_unresolved_decision(self) -> None:
        """**口径已收紧（2026-09-23 06:20，Q-C13 / Q-C19）**：这一条原本断言"卡住太久就换新编号"，
        现在反过来——时间经过、预占过期都**不能单独**成为换编号重发的依据。
        崩在调用里的那一次可能已经发出、已经计费；等多久都不能换个新编号再发一遍。
        解开要靠**账本给出明确结局**（查实没发出 → 整笔退回），不是靠计时器，见下一条。"""
        self.life.brain.model = ScriptedModel(SystemExit("挂了"))
        with self.assertRaises(SystemExit):
            self.life.consider(self.owner.pet_id, self.clock.now)
        stuck = self.open_id()

        self.clock.advance(minutes=30)  # 早就超过预占有效期，也超过原来那个"寿命"
        self.life.brain.model = ScriptedModel(self.stroll_reply())
        self.life.consider(self.owner.pet_id, self.clock.now)

        self.assertEqual(self.reserved[-1], stuck, "结果仍未明：过了多久都只能沿用同一个编号，不许另起一笔预占")
        self.assertEqual(self.open_id(), stuck, "编号也不能被清掉")

    def test_a_decision_proven_unsent_is_released_and_can_start_over(self) -> None:
        """对照：账本查实那一次**确定没发出**之后，这只宠物就不再卡着，能接着想。
        （范围仅限"确定未发送之后的重试"；正常做完一次决策同样会开启新的一次，见 test_web_brain_decision_recovery。）"""
        from app.web_platform.budget import BudgetLedger

        self.life.brain.model = ScriptedModel(SystemExit("挂了"))
        with self.assertRaises(SystemExit):
            self.life.consider(self.owner.pet_id, self.clock.now)
        stuck = self.open_id()
        ledger = BudgetLedger(self.web.journeys.storage)
        ledger.settle(ledger.get(stuck), "not_sent")  # 查实：这一次根本没离开本机

        self.life.brain.model = ScriptedModel(self.stroll_reply())
        outcome = self.life.consider(self.owner.pet_id, self.clock.now)

        self.assertEqual(outcome.status, "departed", f"确定没发出之后应该能接着想：{outcome}")
        self.assertIsNone(self.open_id(), "有了明确结果就把编号清掉，下一次才是新的一次")

    def test_the_id_survives_a_new_service_instance(self) -> None:
        """换进程恢复：重新构造一个 BrainLife（共用同一个库），编号仍然认得出来。"""
        from app.web_agent.brain_life import BrainLife

        self.life.brain.model = ScriptedModel(SystemExit("挂了"))
        with self.assertRaises(SystemExit):
            self.life.consider(self.owner.pet_id, self.clock.now)
        first = self.open_id()

        restarted = BrainLife(brain=self.life.brain, journeys=self.web.journeys, households=self.web.households, residents=self.web.residents,
                              homes=self.web.homes, projector=self.web.projector, mode="live")
        restarted.model_consent = self.life.model_consent
        seen: list[str] = []
        restarted.reserve = lambda operation_id, purpose, pet_id: seen.append(operation_id)
        restarted.brain.model = ScriptedModel(self.stroll_reply())
        self.clock.advance(seconds=30)
        restarted.consider(self.owner.pet_id, self.clock.now)

        self.assertEqual(seen, [first], f"新进程要接着用同一个编号：{seen} vs {first}")


if __name__ == "__main__":
    unittest.main()
