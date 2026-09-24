"""旅行研究的恢复与并发（TRV-03；方案 §11.2；T06／T07）。真实迁移建库与任务队列、**假**研究端口、0 次付费调用。

判据按**真实发送边界**：`FakeResearchPort.calls` 记每一次 `research()`，不只看 attempts（Q 的判据）。
  - T06：可能已发出（超时、发出后进程被杀、恢复接手、预占 TTL 到期）→ 发送次数不增加；只有账本确定释放才开新的一代（正向对照）；
    慢请求途中另一执行者接手同一轮也不再发，晚到的响应照样落盘（费用事实不丢）；
  - T07：响应已存、发布失败 → 合法执行者复用那条回执；结算抛错与租约丢失同时发生时，抛出的仍是租约丢失，回执与待对账都在。
"""

from __future__ import annotations

import unittest
from datetime import timedelta
from unittest import mock

from travel_wish_fakes import TravelResearchTestBase

from app.schemas.runtime_internal.reliability import StaleClaim
from app.utils import utcnow
from app.web_travel.model import RESEARCH_UNKNOWN
from app.web_travel.ports import ResearchNotSent, ResearchUnknown
from app.web_travel.service import RESEARCH_KIND

PAST = "2000-01-01T00:00:00+00:00"


class Killed(BaseException):
    """模拟进程在请求发出以后被杀：不是 Exception，执行循环兜不住。"""


class TravelRecoveryBase(TravelResearchTestBase):
    def expire_leases(self) -> None:
        with self.storage.connect() as conn:
            conn.execute("UPDATE web_tasks SET locked_until = ? WHERE kind = ? AND status = 'running'", (PAST, RESEARCH_KIND))

    def make_due(self) -> None:
        with self.storage.connect() as conn:
            conn.execute("UPDATE web_tasks SET run_after = ? WHERE kind = ? AND status = 'queued'", (PAST, RESEARCH_KIND))

    def kill_after_sending(self) -> None:
        def die(request):
            raise Killed()
        self.port.on_call = die
        self.propose()
        with self.assertRaises(Killed):
            self.research.run_pending()
        self.port.on_call = None
        self.assertEqual([r["status"] for r in self.receipts()], ["intent"], "前提：意图落下了、结果没有")


class TravelMaybeSentTests(TravelRecoveryBase):
    def test_a_send_that_may_have_gone_out_is_never_resent(self) -> None:
        self.port.raises = ResearchUnknown("timeout")
        self.propose()
        self.research.run_pending()
        # 这一层自己的可观察量：当场就落定为不重试、挂未确认。只看最后的发送次数分不出来——
        # 改成「可重试」时，下一次领取会被回执那一层（intent／unknown 不重发）拦住，次数照样是 1
        self.assertEqual((self.task()["status"], self.wishes.read("pet-1").research_state), ("failed", "unknown"))
        self.make_due()
        self.research.run_pending()

        self.assertEqual(len(self.port.calls), 1)
        self.assertEqual([r["status"] for r in self.receipts()], ["unknown"])
        self.assertEqual([r["status"] for r in self.reservations()], ["unknown"], "费用事实按未确认记，不写成没花")
        view = self.wishes.read("pet-1")
        self.assertEqual((view.research_state, view.waiting_reasons, self.task()["status"]), ("unknown", (RESEARCH_UNKNOWN,), "failed"))

    def test_killed_after_sending_and_recovered_does_not_send_again(self) -> None:
        self.kill_after_sending()
        self.expire_leases()
        self.research.run_pending()

        self.assertEqual(len(self.port.calls), 1)
        self.assertEqual([r["status"] for r in self.receipts()], ["intent"])
        self.assertEqual((self.wishes.read("pet-1").research_state, self.task()["status"]), ("unknown", "failed"))

    def test_an_expired_reservation_is_not_proof_that_nothing_was_sent(self) -> None:
        self.kill_after_sending()
        self.assertEqual(self.ledger.expire_stale(now=utcnow() + timedelta(hours=1)), 1)
        self.assertEqual([r["status"] for r in self.reservations()], ["expired"])
        self.expire_leases()
        self.research.run_pending()
        self.assertEqual(len(self.port.calls), 1, "TTL 到期不算证明没发")

    def test_only_a_released_reservation_reopens_the_round(self) -> None:
        """正向对照（端口当场确定没发出）：回执直接记 not_sent、预占释放，队列重试时开新的一代——第二次真的发了，计划指向第二次的回执。
        这条路上回执已经不是 intent／unknown，**不经过**「查账本是否 released」那一步；那一步的正向对照是下一条。"""
        self.port.raises = ResearchNotSent("refused before connecting")
        self.propose()
        self.research.run_pending()
        self.assertEqual(([r["status"] for r in self.receipts()], [r["status"] for r in self.reservations()]), (["not_sent"], ["released"]))
        self.port.raises = None
        self.make_due()
        self.research.run_pending()

        self.assertEqual(len(self.port.calls), 2)
        first, second = self.receipts()
        self.assertEqual((first["status"], second["status"]), ("not_sent", "published"))
        self.assertEqual(self.plans()[0]["operation_id"], second["operation_id"])

    def test_a_crash_reconciled_as_not_sent_reopens_the_round(self) -> None:
        """「查账本是否 released」这一步自己的正向对照：发出后进程被杀（回执停在 intent），运营向服务商查实没收到、
        把预占结成 not_sent（released）——恢复接手时这才当没发，旧回执改记 not_sent，开新的一代真的发一次。
        不对账就不发：见 `test_killed_after_sending_and_recovered_does_not_send_again`。"""
        self.kill_after_sending()
        (reservation,) = self.reservations()
        self.ledger.settle(reservation["reservation_id"], "not_sent")  # 运营对账：确定没发出
        self.expire_leases()
        self.research.run_pending()

        self.assertEqual(len(self.port.calls), 2)
        first, second = self.receipts()
        self.assertEqual((first["status"], second["status"]), ("not_sent", "published"))
        self.assertEqual(self.plans()[0]["operation_id"], second["operation_id"])

    def test_a_second_executor_during_a_slow_send_sends_nothing(self) -> None:
        """同号并发：第一个还在等响应，租约过期被另一执行者接手——它看到意图就不发；晚到的响应照样落盘。"""
        def meanwhile(request):
            if len(self.port.calls) == 1:
                self.expire_leases()
                self.research.run_pending()  # 另一个进程接手这一轮
        self.port.on_call = meanwhile
        self.propose()
        self.research.run_pending()

        self.assertEqual(len(self.port.calls), 1)
        self.assertEqual([r["status"] for r in self.receipts()], ["answered"], "晚到的响应落盘了：费用事实不丢，留待复用")
        self.assertEqual(self.plans(), [], "丢了租约的一方不发布")
        self.assertEqual(self.wishes.read("pet-1").research_state, "unknown")


class TravelStoredAnswerTests(TravelRecoveryBase):
    def test_a_stored_answer_is_reused_when_publishing_failed(self) -> None:
        real, count = self.research._publish_in, []

        def flaky(conn, task, operation_id, result, now):
            count.append(1)
            if len(count) == 1:
                raise RuntimeError("发布写入失败（测试注入）")
            return real(conn, task, operation_id, result, now)

        with mock.patch.object(self.research, "_publish_in", flaky):
            self.propose()
            self.research.run_pending()
            self.assertEqual(([r["status"] for r in self.receipts()], self.plans()), (["answered"], []), "回执在围栏外，发布回滚它不跟着没")
            self.make_due()
            self.research.run_pending()

        self.assertEqual((len(self.port.calls), len(count)), (1, 2))
        (receipt,) = self.receipts()
        self.assertEqual(receipt["status"], "published")
        self.assertEqual(self.plans()[0]["operation_id"], receipt["operation_id"], "认领成功＝计划指向那条 answered 回执")

    def test_a_lost_lease_is_not_masked_by_a_failing_settlement(self) -> None:
        self.propose()
        claim = self.tasks.claim_next("worker-a", [RESEARCH_KIND])
        task = self.tasks.get(claim.task_id)
        self.port.on_call = lambda request: self.expire_leases()  # 发送途中租约被接管
        with mock.patch.object(self.ledger, "settle", side_effect=RuntimeError("账本写不进去")):
            with self.assertRaises(StaleClaim):  # 主信号是租约丢失，不是结算错误
                self.research.run_claimed(task, claim, self.tasks)
        (receipt,) = self.receipts()
        self.assertEqual((receipt["status"], receipt["settle_state"]), ("answered", "pending_reconcile"))
        self.assertEqual(self.plans(), [])

        self.port.on_call = None
        self.research.run_pending()  # 合法执行者接手
        self.assertEqual(len(self.port.calls), 1)
        self.assertEqual((self.receipts()[0]["status"], self.plans()[0]["operation_id"]), ("published", receipt["operation_id"]))


if __name__ == "__main__":
    unittest.main()
