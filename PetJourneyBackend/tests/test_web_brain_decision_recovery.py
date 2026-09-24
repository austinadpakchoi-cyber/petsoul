"""一次逻辑决策的恢复：没结清之前，不能换个新编号把可能已经发出的调用再发一遍（CR-Q14 / Q-C13）。

一次思考有一个**逻辑操作编号**，存在运行记录里。它的作用是让重试、跨分钟、对象重建都落回同一次操作，
从而复用同一笔额度预占——包 A 的重放保护据此挡住第二次调用。

所以什么时候可以清掉这个编号，是一条硬规则：**只有这次操作有了明确结局才能清**。
  - 同编号仍在途（`in_flight` / `reserved`）：恰恰说明这次操作还没结束；
  - 预占到期（`expired`）：只说明过了保留时限没人来结清，**不等于那次请求没发出去**；
  - 结果未明（`unknown`）：有一次可能已被受理。
以上三种都不算明确结局，**过多久都不算**：时间经过、预占过期都不能单独成为换编号重发的依据
（Q-C13 / Q-C19 2026-09-23 06:20 收紧的口径）。清早了的后果是真金白银：认知线 30 秒一轮，
一次可能已经计费的调用会被反复重发，每重发一次还再占一个每宠每日额度。

反过来，**有明确结局就必须放行**，否则就把问题修成了永久卡住。两条正向对照，范围不同、不要混起来：
  - `not_sent / released`（确定没离开本机）：**确定未发送之后的重试可以继续**。这一条只说重试，
    不是说"新决策只能由这两种状态开启"；
  - `succeeded / failed`（这次调用正常收场）：一次决策正常做完之后，**下一次本来就是真正的新一次决策**，
    照常换新编号、照常允许再调用。这是常态路径，不因为上面那条收紧而被挡住。

用真实的 BrainLife ＋ 真实的额度账本，**只**把远端模型换成替身；不联网、不产生付费调用。
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from app.schemas.runtime_internal import BudgetDenied
from app.web_agent.decision.testing import ScriptedModel
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class SimulatedCrash(BaseException):
    """模拟进程在模型调用中途被杀：BaseException 不会被业务代码的 except Exception 接住。"""


class CrashingModel:
    """远端模型替身：请求“已经发出去”之后进程就没了。只换这一层，Brain 与额度账本都是真的。"""

    available = True
    provider_label = "scripted"
    max_call_seconds = 5.0

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages, *, max_tokens: int):  # noqa: ARG002 - 与 ModelAdapter.complete 同签名
        self.calls += 1
        raise SimulatedCrash("killed while the model call was in flight")


class DecisionRecoveryTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("recovery-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.owner.patch("/settings", {"model_replies": True})
        self.life = self.web.brain_life
        self.life.mode = "live"
        self.web.projector.model_available = lambda: True
        self.model = CrashingModel()
        self.life.brain.model = self.model
        self.round = dict(self.web.cognition.jobs)["brain_life"]

    # ---- 读取 ----
    def operation_id(self) -> str | None:
        return (self.web.projector.runtime.row(self.owner.pet_id) or {}).get("decision_operation_id")

    def reservations(self) -> list[dict]:
        with self.web.journeys.storage.connect() as conn:
            rows = conn.execute("SELECT operation_id, status, outcome FROM web_budget_reservations "
                                "WHERE subject_scope = ? AND purpose = 'life_plan' ORDER BY rowid",
                                (f"pet:{self.owner.pet_id}",)).fetchall()
        return [dict(row) for row in rows]

    def usage(self, scope: str) -> dict:
        from app.web_platform.budget import BudgetLedger

        return BudgetLedger(self.web.journeys.storage).usage(scope)

    def crash_once(self) -> str:
        """第一次思考崩在模型调用里：编号落库、预占停在 reserved。返回那个编号。"""
        with self.assertRaises(SimulatedCrash):
            self.life.consider(self.owner.pet_id, self.clock.now)
        first = self.operation_id()
        self.assertTrue(first, "崩在调用里也要把编号留在库里，否则根本无从恢复")
        self.assertEqual([(r["operation_id"], r["status"]) for r in self.reservations()], [(first, "reserved")],
                         "这一笔预占停在在途：没人来结清，但调用可能已经发出去了")
        self.assertEqual(self.model.calls, 1)
        return first

    def retry(self):
        return self.life.consider(self.owner.pet_id, self.clock.now)

    def assert_still_the_same_attempt(self, first: str, outcome, *, calls: int = 1) -> None:
        self.assertEqual([outcome.status, outcome.reason], ["failed", "budget_denied"], f"在途要被判成额度未放行：{outcome}")
        self.assertEqual(outcome.operation_id, first, "这一次用的必须还是同一个编号")
        self.assertEqual(self.operation_id(), first, "在途没结清之前不能把编号清掉（清掉下一轮就换新编号重发了）")
        self.assertEqual(self.model.calls, calls, "可能已经发出的那一次不能被盲目重发")
        self.assertEqual(len(self.reservations()), 1, "重试期间不能开第二笔预占")

    # ---- 连续重试、跨分钟 ----
    def test_a_retry_in_the_same_minute_reuses_the_operation_and_sends_nothing(self) -> None:
        first = self.crash_once()

        self.assert_still_the_same_attempt(first, self.retry())

    def test_crossing_a_minute_boundary_still_reuses_the_same_operation(self) -> None:
        first = self.crash_once()
        self.clock.advance(seconds=61)  # 编号是按分钟拼的：跨过整分钟仍然必须沿用同一个

        self.assert_still_the_same_attempt(first, self.retry())

    def test_consecutive_retries_never_open_a_second_reservation(self) -> None:
        """认知线 30 秒一轮：连着重试很多轮，也只能有那一笔预占、那一次调用。"""
        first = self.crash_once()

        for _ in range(8):  # 8 轮 × 30 秒 = 4 分钟，仍在预占有效期内
            self.clock.advance(seconds=30)
            self.assert_still_the_same_attempt(first, self.retry())

        self.assertEqual(self.usage(f"pet:{self.owner.pet_id}:life_plan"), {"used": 0, "inflight": 1},
                         "全程只有那一笔在途，没有被重复计量")

    def test_an_object_rebuild_still_reuses_the_operation(self) -> None:
        """编号存在库里、不在内存里：重建对象之后仍然落回同一次操作。
        （**只是重建对象**，不是进程重启验证——真正的重启要另开进程，这里没有做。）"""
        from app.web_agent.brain_life import BrainLife
        from app.web_agent.runtime_view import RuntimeStore

        first = self.crash_once()
        rebuilt = BrainLife(brain=self.life.brain, journeys=self.life.journeys, households=self.life.households,
                            residents=self.life.residents, homes=self.life.homes, projector=self.life.projector, mode="live")
        rebuilt.reserve, rebuilt.settle, rebuilt.model_consent = self.life.reserve, self.life.settle, self.life.model_consent
        rebuilt.projector.runtime = RuntimeStore(self.app.state.storage)

        self.assert_still_the_same_attempt(first, rebuilt.consider(self.owner.pet_id, self.clock.now))

    def test_an_exception_in_the_round_does_not_clear_the_operation(self) -> None:
        """整轮的异常兜底（brain_wiring._stall）也不能清编号：出了异常不代表那次调用没发出去。"""
        first = self.crash_once()

        def boom(pet_id, now=None):
            raise RuntimeError("这一轮在别处炸了")

        self.life.consider = boom
        self.round(self.clock.now, limit=5)

        self.assertEqual(self.operation_id(), first, "异常兜底只该写退避，不该动编号")
        self.assertEqual(self.model.calls, 1)
        self.assertEqual(len(self.reservations()), 1)

    # ---- 恢复之后 ----
    def test_even_long_after_the_reservation_expired_nothing_is_re_sent(self) -> None:
        """**过了多久都不换编号**：预占到期只说明没人来结清，不说明对方没收到（2026-09-23 06:20 收紧的口径）。"""
        first = self.crash_once()
        self.life.brain.model = ScriptedModel(*['{"choice": "continue", "intent": "今天在家"}'] * 4)

        for minutes in (10, 20, 60, 24 * 60):  # 远远超过预占有效期，也超过任何"保留时限"
            self.clock.advance(minutes=minutes)
            outcome = self.retry()
            self.assertEqual(outcome.operation_id, first, f"过了 {minutes} 分钟仍然必须是同一次操作：{outcome}")
            self.assertEqual(self.operation_id(), first, "结果仍未明：编号不能清、更不能换")
            self.assertEqual(self.model.calls, 1, f"过了 {minutes} 分钟也不许重发")
            self.assertEqual(len(self.reservations()), 1, "不许另起一笔预占")
        self.assertEqual([row["status"] for row in self.reservations()], ["expired"],
                         "那一笔只能停在 expired，不能被退回成 released")

    def test_an_expired_reservation_is_never_refunded_as_not_sent(self) -> None:
        """预占到期 ≠ 请求没发出：那一笔必须仍然保守计入已用，不能被后一轮的"我没发出去"退回来。"""
        first = self.crash_once()
        self.clock.advance(minutes=10)  # 超过预占有效期（300 秒），但还没到编号的作废时长

        outcome = self.retry()

        self.assertEqual(outcome.operation_id, first, "还在作废时长内：仍然是同一次操作")
        self.assertEqual(self.model.calls, 1, "到期不等于没发出，不能因此重发")
        rows = self.reservations()
        self.assertEqual([row["status"] for row in rows], ["expired"], f"到期那笔只能是 expired，不能被退回成 released：{rows}")
        self.assertEqual(self.usage(f"pet:{self.owner.pet_id}:life_plan")["used"], 1, "到期的那一次仍然保守计入已用")
        self.assertEqual(self.operation_id(), first, "结果仍未明：编号继续留着")

    def test_a_confirmed_not_sent_lets_the_next_round_start_over(self) -> None:
        """正向对照（**范围只到这里**）：查实那一次**确定没离开本机**（整笔退回成 released / not_sent）之后，
        这次重试必须能接着走——不能把"别重发"修成"永久卡住"。
        这一条只证明"确定未发送之后的重试可以继续"，**不代表新决策只能由这两种状态开启**；
        正常做完之后的新决策见 test_a_normally_finished_decision_still_opens_a_brand_new_one_next_time。"""
        from app.web_platform.budget import BudgetLedger

        first = self.crash_once()
        ledger = BudgetLedger(self.web.journeys.storage)
        ledger.settle(ledger.get(first), "not_sent")  # 账本那边查清了：这一次根本没发出去
        self.assertEqual([r["status"] for r in self.reservations()], ["released"], "前提：整笔已退回")
        model = ScriptedModel(*['{"choice": "continue", "intent": "今天在家"}'] * 2)
        self.life.brain.model = model

        resumed = self.retry()

        self.assertEqual(resumed.status, "stayed", f"确定没发出之后应该能正常再想一次：{resumed}")
        self.assertEqual(len(model.calls), 1, "确定没发出之后允许再进一次调用（不能修成永久卡住）")
        self.assertEqual(resumed.operation_id, first, "退回的那笔可以按同一个编号重新占用（账本明确允许）")
        self.assertIsNone(self.operation_id(), "这一次有了明确结果：编号清掉")

        self.clock.advance(minutes=20)
        following = self.retry()  # 结清之后的下一次，才是真正的新一次决策

        self.assertNotEqual(following.operation_id, first, "结清之后的下一次要换新编号")
        rows = {row["operation_id"]: row["status"] for row in self.reservations()}
        self.assertEqual(rows, {first: "settled", following.operation_id: "settled"},
                         f"两笔都有明确结局，没有谁停在半路：{rows}")

    def test_a_normally_finished_decision_still_opens_a_brand_new_one_next_time(self) -> None:
        """常态路径的正向对照：一次决策**正常做完**（settled/succeeded）之后，下一次就是真正的新一次决策——
        换新编号、照常再调用一次。"收紧重发"不能把正常的下一次决策也挡住。"""
        model = ScriptedModel(*['{"choice": "continue", "intent": "今天在家"}'] * 2)
        self.life.brain.model = model

        first = self.retry()
        self.assertEqual(first.status, "stayed", f"第一次正常做完：{first}")
        self.assertIsNone(self.operation_id(), "正常做完就把编号清掉")
        self.clock.advance(minutes=20)

        second = self.retry()

        self.assertEqual(second.status, "stayed", f"下一次照常能想：{second}")
        self.assertNotEqual(second.operation_id, first.operation_id, "真正的新一次决策要换新编号")
        self.assertEqual(len(model.calls), 2, "正常做完之后不该被“别重发”挡住")
        rows = {row["operation_id"]: row["status"] for row in self.reservations()}
        self.assertEqual(rows, {first.operation_id: "settled", second.operation_id: "settled"}, f"两笔各自结清：{rows}")

    def test_a_definite_no_send_does_clear_the_operation(self) -> None:
        """对照组：确定什么都没发出去（额度上限挡在预占之前）时，编号照常清掉，下一轮是真正的新一次。"""
        self.life.brain.model = ScriptedModel('{"choice": "continue", "intent": "在家"}')
        self.life.reserve = lambda operation_id, purpose, pet_id: BudgetDenied(operation_id, "pet", "limit_reached",
                                                                               retry_after=self.clock.now + timedelta(hours=2))

        outcome = self.retry()

        self.assertEqual([outcome.status, outcome.reason], ["failed", "budget_denied"], f"{outcome}")
        self.assertIsNone(self.operation_id(), "根本没占上就什么都没发出：这一次操作有明确结局，编号该清")
        self.assertEqual(self.model.calls, 0)


if __name__ == "__main__":
    unittest.main()
