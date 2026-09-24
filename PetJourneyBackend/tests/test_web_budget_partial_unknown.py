"""`unknown` **当场**少发多记：预占 2、实际只发出 1，当场却按 2 记。

与已修好的"事后能不能回正"是两个问题：那条管**查清之后补不补**，这条管**当场记多少**。
方向上只多记不少记（不会超支，只会让每日上限提前触顶），但它是当场就发生的，而且——
按当前接线**没有人会来查清**（见 `test_web_budget_reconcile.ReconcileHasNoCallerTests`），
所以多记的那一份实际上永远留在账上。

断言方式采用 Q 在 C30 用的两条更强做法：
  - **一律按同一 scope 的前后差额断言**，不看绝对值（全局层所有档共用一个计数器，绝对值会把别档算进来）；
  - 覆盖**跨 UTC 日**：预占与查清分属两个记账窗口时，补在**原窗口**。

一次性临时库；不联网、0 次付费调用。
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.web_platform.budget import BudgetLedger, BudgetLimit
from task_budget_helpers import open_storage

NOW = datetime(2026, 9, 23, 2, 0, tzinfo=timezone.utc)
DAILY, PET = "provider:image:daily", "pet:p1:illustration"


class PartialUnknownAccountingTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ledger = BudgetLedger(open_storage(str(Path(tmp.name) / "budget.sqlite3")))

    # ---- 辅助：一律按差额断言 ----
    def reserve(self, operation_id: str = "op-1", units: int = 2, now: datetime = NOW, ttl_seconds: float = 900.0):
        return self.ledger.reserve(operation_id, provider="image", purpose="illustration", subject_scope="pet:p1",
                                   units=units, limits=[BudgetLimit(DAILY, 50), BudgetLimit(PET, 50)],
                                   now=now, ttl_seconds=ttl_seconds)

    def snapshot(self, now: datetime = NOW) -> dict[str, int]:
        return {scope: self.ledger.usage(scope, now=now)["used"] for scope in (DAILY, PET)}

    def delta(self, before: dict[str, int], now: datetime = NOW) -> dict[str, int]:
        after = self.snapshot(now)
        return {scope: after[scope] - before[scope] for scope in before}

    def row(self, operation_id: str = "op-1"):
        with self.ledger.storage.connect() as conn:
            return conn.execute("SELECT status, outcome, reserved_units, actual_units FROM web_budget_reservations "
                                "WHERE operation_id = ?", (operation_id,)).fetchone()

    # ---- 缺陷本体：当场就多记 ----
    def test_an_unknown_with_a_known_sent_count_charges_only_what_went_out(self) -> None:
        """预占 2、证件照超时、场景图**根本没发**：当场就该记 1，不是 2。

        场景图那次不存在"可能被受理"——它压根没出去。把它算进来不是保守，是记错了。
        """
        before = self.snapshot()
        permit = self.reserve()

        self.ledger.settle(permit, "unknown", actual_units=1, now=NOW)

        self.assertEqual(self.delta(before), {DAILY: 1, PET: 1}, "只发出去 1 次，两层都只该记 1")
        self.assertEqual(self.ledger.usage(DAILY, now=NOW)["inflight"], 0, "在途照常释放")

    def test_an_unknown_without_a_sent_count_stays_conservative(self) -> None:
        """调用方说不出发了几次：维持按预占全额保守计入——**不知道**不能当成**没发生**。"""
        before = self.snapshot()
        permit = self.reserve()

        self.ledger.settle(permit, "unknown", now=NOW)  # 不给 actual_units

        self.assertEqual(self.delta(before), {DAILY: 2, PET: 2}, "说不清就按预占全额记")

    def test_an_unknown_that_sent_everything_charges_the_whole_reservation(self) -> None:
        """两次都发出去了：记满 2，和保守值一致（这条是防"回正改过头"的对照）。"""
        before = self.snapshot()
        permit = self.reserve()

        self.ledger.settle(permit, "unknown", actual_units=2, now=NOW)

        self.assertEqual(self.delta(before), {DAILY: 2, PET: 2})

    # ---- 与"事后回正"的差额一致性：两段加起来必须等于最终确认值 ----
    def test_the_two_stages_add_up_to_the_final_confirmed_units(self) -> None:
        """当场记 1、之后查清确实是 1：**不能再动**（已经对了，别又扣一次）。"""
        before = self.snapshot()
        permit = self.reserve()
        self.ledger.settle(permit, "unknown", actual_units=1, now=NOW)
        self.assertEqual(self.delta(before), {DAILY: 1, PET: 1})

        self.ledger.settle(permit, "succeeded", actual_units=1, now=NOW + timedelta(minutes=10))

        self.assertEqual(self.delta(before), {DAILY: 1, PET: 1}, "累计增量 == 最终确认的 actual_units")

    def test_a_clarification_larger_than_what_was_charged_tops_it_up(self) -> None:
        """当场按 1 记，后来查清其实发出了 2：要**补上**差额，不能只会往下调。"""
        before = self.snapshot()
        permit = self.reserve()
        self.ledger.settle(permit, "unknown", actual_units=1, now=NOW)

        self.ledger.settle(permit, "succeeded", actual_units=2, now=NOW + timedelta(minutes=10))

        self.assertEqual(self.delta(before), {DAILY: 2, PET: 2}, "累计增量要跟上最终确认值")

    def test_a_clarified_not_sent_after_a_partial_charge_returns_exactly_what_was_charged(self) -> None:
        """当场记了 1，后来查清一次都没发出：只退这 1，不能按预占退 2（那会把账退成负的）。"""
        before = self.snapshot()
        permit = self.reserve()
        self.ledger.settle(permit, "unknown", actual_units=1, now=NOW)

        self.ledger.settle(permit, "not_sent", now=NOW + timedelta(minutes=10))

        self.assertEqual(self.delta(before), {DAILY: 0, PET: 0}, "回到零，不能多退")

    def test_repeating_the_clarification_does_not_charge_twice(self) -> None:
        before = self.snapshot()
        permit = self.reserve()
        self.ledger.settle(permit, "unknown", actual_units=1, now=NOW)
        self.ledger.settle(permit, "succeeded", actual_units=2, now=NOW + timedelta(minutes=10))

        self.ledger.settle(permit, "succeeded", actual_units=2, now=NOW + timedelta(minutes=11))

        self.assertEqual(self.delta(before), {DAILY: 2, PET: 2}, "重复报告同一结论不得再动计数")

    # ---- 跨 UTC 日：补在原记账窗口 ----
    def test_a_correction_lands_in_the_original_accounting_window(self) -> None:
        late = datetime(2026, 9, 22, 23, 50, tzinfo=timezone.utc)
        next_day = datetime(2026, 9, 23, 0, 10, tzinfo=timezone.utc)
        before_old_day = self.snapshot(now=late)
        before_new_day = self.snapshot(now=next_day)
        permit = self.reserve("op-late", now=late)
        self.ledger.settle(permit, "unknown", actual_units=1, now=late)

        self.ledger.settle(permit, "succeeded", actual_units=2, now=next_day)  # 跨到第二天才查清

        self.assertEqual(self.delta(before_old_day, now=late), {DAILY: 2, PET: 2}, "补在**预占那一天**的窗口")
        self.assertEqual(self.delta(before_new_day, now=next_day), {DAILY: 0, PET: 0}, "新的一天不该被记上")

    # ---- 过期那一档同样按已知发出次数 ----
    def test_an_expired_reservation_still_charges_the_whole_reservation(self) -> None:
        """过期是"没人来结算"，调用方**什么都没说**——只能按预占全额保守计入。

        与 unknown 的区别：unknown 是调用方**报告**了"发出去但结果不明"，可能带着发出次数；
        expired 连报告都没有，所以没有更好的依据。
        """
        before = self.snapshot()
        self.reserve("op-stale", ttl_seconds=0.001)

        self.ledger.expire_stale(now=NOW + timedelta(hours=2))

        self.assertEqual(self.delta(before), {DAILY: 2, PET: 2})
        self.assertEqual(self.row("op-stale")["status"], "expired")

    # ---- 旧数据：actual_units 为空的历史行，行为不变 ----
    def test_historic_rows_without_a_charged_amount_keep_the_old_behaviour(self) -> None:
        """迁移前落下的 unknown 行没有"已记账数"可依。查清时按预占全额回正，与旧行为一致。"""
        before = self.snapshot()
        permit = self.reserve()
        self.ledger.settle(permit, "unknown", now=NOW)  # 没给发出次数 → 按 2 记
        self.assertEqual(self.delta(before), {DAILY: 2, PET: 2})

        self.ledger.settle(permit, "succeeded", actual_units=1, now=NOW + timedelta(minutes=10))

        self.assertEqual(self.delta(before), {DAILY: 1, PET: 1}, "从保守的 2 回正到 1")


    # ---- 报得比预占还多：封顶，但要留痕 ----
    def test_reporting_more_than_reserved_is_capped_and_logged(self) -> None:
        """调用方报的次数超过它申请到的预占：按预占量封顶（那部分从来没被授权过），
        但**不静默吞掉**——发一条 warning，免得"报 3 实占 2"在库里完全看不出来（Q 指出）。"""
        before = self.snapshot()
        permit = self.reserve(units=2)

        with self.assertLogs("petsoul.web.budget", level="WARNING") as captured:
            self.ledger.settle(permit, "unknown", actual_units=3, now=NOW)

        self.assertEqual(self.delta(before), {DAILY: 2, PET: 2}, "封顶在预占量")
        self.assertEqual(self.row()["actual_units"], 2, "落库的也是封顶后的数")
        self.assertIn("reports more than reserved", "".join(captured.output), "要留下可查的痕迹")


if __name__ == "__main__":
    unittest.main()
