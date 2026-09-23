"""保守计入之后的**回正**：unknown / expired 先按预占全额记账，查清之后要按差额补回来。

原设计意图是"先保守计入，查清后再更正"。但那条更正路径只处理了 `not_sent`（整笔退回），
"预占 2、查清只用了 1"这种**部分**情况一分钱都回不来——`used` 永久停在 2。
方向上只多记不少记（不会超支，只会让每日上限提前触顶），但它是永久的，不是暂时的。

本批只改 `budget.py` 的回正逻辑：
  - **保持** unknown 当场 `actual_units=NULL` 与保守记账的旧语义，**不把"发出次数"与"确认计量"混成一个字段**；
  - 回正只按**已记账数与查清数的差额**来，用**原 scope、原记账窗口**，不碰当天别的操作；
  - **不重复扣 inflight**——在途在转 unknown/expired 那一步已经释放过了。

一次性临时库；不联网、0 次付费调用。
"""

from __future__ import annotations

import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.web_platform.budget import BudgetLedger, BudgetLimit
from task_budget_helpers import open_storage

NOW = datetime(2026, 9, 23, 2, 0, tzinfo=timezone.utc)
DAILY, PET = "provider:image:daily", "pet:p1:illustration"


class BudgetReconcileTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ledger = BudgetLedger(open_storage(str(Path(tmp.name) / "budget.sqlite3")))

    # ---- 辅助 ----
    def reserve(self, operation_id: str = "op-1", units: int = 2, now: datetime = NOW):
        return self.ledger.reserve(operation_id, provider="image", purpose="illustration", subject_scope="pet:p1",
                                   units=units, limits=[BudgetLimit(DAILY, 50), BudgetLimit(PET, 50)], now=now)

    def used(self, scope_key: str = DAILY) -> int:
        return self.ledger.usage(scope_key, now=NOW)["used"]

    def inflight(self, scope_key: str = DAILY) -> int:
        return self.ledger.usage(scope_key, now=NOW)["inflight"]

    def row(self, operation_id: str = "op-1"):
        with self.ledger.storage.connect() as conn:
            return conn.execute("SELECT status, outcome, reserved_units, actual_units FROM web_budget_reservations "
                                "WHERE operation_id = ?", (operation_id,)).fetchone()

    # ---- 对照：正常预占→结算，本来就该对 ----
    def test_a_plain_reservation_and_settlement_is_unchanged(self) -> None:
        permit = self.reserve()
        self.assertEqual((self.used(), self.inflight()), (0, 2), "预占之后：在途 2、已用 0")

        self.ledger.settle(permit, "succeeded", actual_units=2, now=NOW)

        self.assertEqual((self.used(), self.inflight()), (2, 0), "两次都用上了：已用 2、在途归零")
        self.assertEqual(self.used(PET), 2, "每一层作用域都要跟着对")

    # ---- 缺陷本体：unknown 先保守记 2，查清只用了 1，却回不来 ----
    def test_a_clarified_partial_use_after_unknown_is_corrected(self) -> None:
        permit = self.reserve()
        self.ledger.settle(permit, "unknown", actual_units=1, now=NOW)
        self.assertEqual((self.used(), self.inflight()), (2, 0), "保守计入：先按预占全额记，在途已释放")

        # 之后查清：这次确实只用了 1 个单位
        self.ledger.settle(permit, "succeeded", actual_units=1, now=NOW + timedelta(minutes=10))

        self.assertEqual(self.used(), 1, "查清之后要按差额回正，不能永久停在 2")
        self.assertEqual(self.used(PET), 1, "每一层作用域都要回正")
        self.assertEqual(self.inflight(), 0, "**不能重复扣在途**——转 unknown 那一步已经释放过了")
        row = self.row()
        self.assertEqual((row["status"], row["outcome"], row["actual_units"]), ("settled", "succeeded", 1))

    def test_a_clarified_partial_use_after_expiry_is_corrected(self) -> None:
        """过期那一档同理：到期没结算先保守计入，之后查清也要回正。"""
        permit = self.reserve()
        self.ledger.expire_stale(now=NOW + timedelta(hours=2))
        self.assertEqual((self.used(), self.inflight()), (2, 0), "过期：保守计入、释放在途")
        self.assertEqual(self.row()["status"], "expired")

        self.ledger.settle(permit, "succeeded", actual_units=1, now=NOW + timedelta(hours=3))

        self.assertEqual(self.used(), 1)
        self.assertEqual(self.inflight(), 0, "不重复扣在途")

    def test_a_clarified_failure_with_known_units_is_corrected_too(self) -> None:
        """明确失败但已知发出几次：同样按差额回正（失败不等于没发出，费用照记）。"""
        permit = self.reserve()
        self.ledger.settle(permit, "unknown", actual_units=1, now=NOW)

        self.ledger.settle(permit, "failed", actual_units=1, now=NOW + timedelta(minutes=5))

        self.assertEqual(self.used(), 1, "确定失败但确实发出过 1 次：记 1，不是 2、也不是 0")

    def test_a_clarified_not_sent_returns_the_whole_reservation(self) -> None:
        """查清一次都没发出：整笔退回（这一条原来就对，作为不回归的对照）。"""
        permit = self.reserve()
        self.ledger.settle(permit, "unknown", actual_units=1, now=NOW)

        self.ledger.settle(permit, "not_sent", now=NOW + timedelta(minutes=5))

        self.assertEqual(self.used(), 0, "一次都没发出：归零")
        self.assertEqual(self.inflight(), 0)

    def test_an_unclarified_late_settlement_keeps_the_conservative_amount(self) -> None:
        """查清时仍然说不出用了几个单位：保持保守计入，不要因为"回正"反而少记。"""
        permit = self.reserve()
        self.ledger.settle(permit, "unknown", actual_units=1, now=NOW)

        self.ledger.settle(permit, "succeeded", now=NOW + timedelta(minutes=5))  # 没给 actual_units

        self.assertEqual(self.used(), 2, "不知道就维持保守的 2，不能擅自往下调")

    # ---- 只调一次：重复结算与并发重复 ----
    def test_repeating_the_same_clarification_adjusts_only_once(self) -> None:
        permit = self.reserve()
        self.ledger.settle(permit, "unknown", actual_units=1, now=NOW)
        self.ledger.settle(permit, "succeeded", actual_units=1, now=NOW + timedelta(minutes=5))
        self.assertEqual(self.used(), 1)

        self.ledger.settle(permit, "succeeded", actual_units=1, now=NOW + timedelta(minutes=6))

        self.assertEqual(self.used(), 1, "重复报告同一个结论不能再扣一次")

    def test_concurrent_clarifications_adjust_only_once(self) -> None:
        permit = self.reserve()
        self.ledger.settle(permit, "unknown", actual_units=1, now=NOW)
        start = threading.Barrier(2)

        def clarify() -> None:
            start.wait(timeout=10)
            self.ledger.settle(permit, "succeeded", actual_units=1, now=NOW + timedelta(minutes=5))

        threads = [threading.Thread(target=clarify) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            self.assertFalse(thread.is_alive(), "不该卡住")

        self.assertEqual(self.used(), 1, "两个查清同时到，也只调一次")

    # ---- 不碰当天别的操作 ----
    def test_the_correction_does_not_touch_other_operations(self) -> None:
        other = self.reserve("op-other", units=3)
        self.ledger.settle(other, "succeeded", actual_units=3, now=NOW)
        permit = self.reserve("op-1", units=2)
        self.ledger.settle(permit, "unknown", actual_units=1, now=NOW)
        self.assertEqual(self.used(), 5, "3 ＋ 保守的 2")

        self.ledger.settle(permit, "succeeded", actual_units=1, now=NOW + timedelta(minutes=5))

        self.assertEqual(self.used(), 4, "只回正这一笔的 1 个单位，别人的 3 一动不动")

    # ---- 本批**不改**的语义，钉住免得被顺手改掉 ----
    def test_unknown_still_records_null_actual_units(self) -> None:
        """unknown 当场仍然留空：这一列的含义是"确认计量"，而 unknown 的确认计量确实未知。

        "发出了几次"是另一回事，不要为了省事把两者混进同一个字段（本批明确不做）。
        """
        permit = self.reserve()
        self.ledger.settle(permit, "unknown", actual_units=1, now=NOW)

        row = self.row()
        self.assertEqual((row["status"], row["outcome"]), ("unknown", "unknown"))
        self.assertIsNone(row["actual_units"], "unknown 当场不落确认计量")
        self.assertEqual(self.used(), 2, "当场仍然保守计入预占全额（剩余项另列，不在本批改）")


if __name__ == "__main__":
    unittest.main()
