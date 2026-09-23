"""照片导演：控制流与租约失效必须中止，结算故障不能盖掉它们。

全程禁网，用注入替身，不是真实供应商。
"""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "photo_director"))

import builders  # noqa: E402
from harness import FakeBudget, FakeChat, ModelPortCase, VALID_CAFE  # noqa: E402

from app.web_photo_director import PhotoDirector  # noqa: E402


class LeaseLost(Exception):
    """替身：真正的 LeaseLost 在 app/web_platform/lease.py，本包不跨包 import。"""


class BrokenBudget(FakeBudget):
    def settle(self, **kwargs):
        raise RuntimeError("账本写不进去")


class ControlFlowTests(ModelPortCase):
    def assert_propagates(self, exc: BaseException):
        chat, budget = FakeChat(raises=exc), FakeBudget()
        with self.assertRaises(type(exc)):
            self.direct(chat, budget)
        # 仍然如实结算成结果不明：请求可能已经发出去了
        self.assertEqual([outcome for _, outcome in budget.settled], ["sent_unknown"])

    def test_cancellation_is_not_swallowed_into_a_rule_photo(self):
        """取消不是"供应商没回话"。吞掉它会让本该停下的进程继续出一张规则图。"""
        self.assert_propagates(asyncio.CancelledError())

    def test_keyboard_interrupt_propagates(self):
        self.assert_propagates(KeyboardInterrupt())

    def test_system_exit_propagates(self):
        self.assert_propagates(SystemExit(1))

    def test_lease_loss_aborts_instead_of_degrading_to_a_rule_photo(self):
        """租约失效＝这份活已经不归这个进程了。继续出一张规则图等于越权产出。"""
        self.assert_propagates(LeaseLost("lease gone"))

    def test_lease_loss_can_also_be_declared_explicitly(self):
        """按类名兜底之外，调用方可以传精确的类；两条路都必须中止。"""
        class WorkerPreempted(Exception):
            pass

        context = builders.build_context("cafe")
        access = builders.build_access(context, text_director=True)
        director = PhotoDirector(
            chat=FakeChat(raises=WorkerPreempted("taken over")),
            budget=FakeBudget(), abort_on=(WorkerPreempted,),
        )
        with self.assertRaises(WorkerPreempted):
            director.direct(context, access)

    def test_ordinary_failure_still_falls_back(self):
        chat, budget = FakeChat(raises=TimeoutError("no response")), FakeBudget()
        photo = self.direct(chat, budget)
        self.assertEqual(photo.text_call.outcome, "sent_unknown")
        self.assertEqual(photo.directed_by, "rule")


class LedgerFailureTests(ModelPortCase):
    """账本写不进去是要对账的事，不是"这次调用失败了"。"""

    def _context(self):
        context = builders.build_context("cafe")
        return context, builders.build_access(context, text_director=True)

    def test_a_broken_ledger_does_not_mask_the_lease_loss(self):
        """让结算异常原样抛出，调用方看到的会是 RuntimeError，
        而真正要紧的"租约已失效、这份活不归你了"就被埋掉了。"""
        seen = []
        context, access = self._context()
        director = PhotoDirector(
            chat=FakeChat(raises=LeaseLost("lease gone")), budget=BrokenBudget(),
            on_settlement_failure=lambda *args: seen.append(args),
        )
        with self.assertRaises(LeaseLost):
            director.direct(context, access)
        self.assertEqual(len(seen), 1, "结算故障要单独通知，供对账")

    def test_a_broken_ledger_does_not_mask_cancellation_either(self):
        context, access = self._context()
        director = PhotoDirector(
            chat=FakeChat(raises=asyncio.CancelledError()), budget=BrokenBudget())
        with self.assertRaises(asyncio.CancelledError):
            director.direct(context, access)

    def test_the_unsettled_call_is_attached_for_reconciliation(self):
        context, access = self._context()
        try:
            PhotoDirector(chat=FakeChat(raises=LeaseLost("x")), budget=BrokenBudget()).direct(
                context, access)
        except LeaseLost as exc:
            unsettled = getattr(exc, "photo_director_unsettled", None)
            self.assertIsNotNone(unsettled, "没记上账的这一笔要挂在异常上")
            self.assertEqual(unsettled["outcome"], "sent_unknown")
            self.assertIn("RuntimeError", unsettled["settlement_error"])
        else:
            self.fail("应当抛出 LeaseLost")

    def test_a_broken_ledger_on_an_ordinary_failure_is_flagged_not_swallowed(self):
        """普通失败下账本坏了：仍然降级出图，但原因里标出这一笔没记上。"""
        context, access = self._context()
        photo = PhotoDirector(
            chat=FakeChat(raises=TimeoutError("no response")), budget=BrokenBudget()
        ).direct(context, access)
        self.assertEqual(photo.text_call.outcome, "sent_unknown")
        self.assertIn("settlement_unrecorded", photo.text_call.reason or "")

    def test_an_abort_raised_by_settlement_itself_must_propagate(self):
        """模型正常返回、结算这一步才发现被取消或租约没了：这是**首次出现**的中止信号。

        吞掉它会返回一条出图指令，而这个进程其实已经没有资格继续了。
        """
        for error in (asyncio.CancelledError(), LeaseLost("gone at settle")):
            with self.subTest(error=type(error).__name__):
                class AbortingBudget(FakeBudget):
                    def settle(self, **kwargs):
                        raise error

                context, access = self._context()
                with self.assertRaises(type(error)):
                    PhotoDirector(chat=FakeChat(text=VALID_CAFE),
                                  budget=AbortingBudget()).direct(context, access)

    def test_that_abort_also_carries_the_unsettled_record(self):
        class AbortingBudget(FakeBudget):
            def settle(self, **kwargs):
                raise LeaseLost("gone at settle")

        context, access = self._context()
        try:
            PhotoDirector(chat=FakeChat(text=VALID_CAFE), budget=AbortingBudget()).direct(
                context, access)
        except LeaseLost as exc:
            self.assertIsNotNone(getattr(exc, "photo_director_unsettled", None))
        else:
            self.fail("应当抛出 LeaseLost")

    def test_a_later_settle_abort_never_replaces_an_earlier_one(self):
        """外层已经在上抛租约失效时，结算里再冒出来的中止信号不能把它换掉。"""
        class AlsoAborting(FakeBudget):
            def settle(self, **kwargs):
                raise asyncio.CancelledError()

        context, access = self._context()
        with self.assertRaises(LeaseLost):
            PhotoDirector(chat=FakeChat(raises=LeaseLost("original")),
                          budget=AlsoAborting()).direct(context, access)

    def test_a_broken_ledger_on_success_is_flagged_but_the_shot_still_stands(self):
        context, access = self._context()
        photo = PhotoDirector(chat=FakeChat(text=VALID_CAFE), budget=BrokenBudget()).direct(
            context, access)
        self.assertEqual(photo.directed_by, "model")
        self.assertIn("settlement_unrecorded", photo.text_call.reason or "")


if __name__ == "__main__":
    unittest.main()
