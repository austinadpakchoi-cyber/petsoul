"""额度账本的表不在时，必须明确报错、不能假装通过——不然付费调用会在没有上限的情况下发出去。

包 A 有一条同样用意的反例（`test_web_budget_reservation.BudgetWithoutMigrationTests`），但它的前提是"建库时不建这两张表"，
迁移 0050 落地之后已经造不出那种库。这里从集成侧反过来验：**真实迁移建好之后再把表删掉**，行为仍然要是"明确不可用"。
两条互为补充；A 那条按 CHANGE_REQUEST 由 A 调整，本窗口不动 A 的文件。
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.storage import JourneyStorage
from app.web_platform.budget import BudgetDenied, BudgetLedger, BudgetLimit
from app.web_platform.migrations import apply_web_migrations
from app.web_providers.meter import ProviderMeter

T0 = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
BUDGET_TABLES = ("web_budget_counters", "web_budget_reservations")


class LedgerMissingTablesTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.storage = JourneyStorage(Path(tmp.name) / "ledger.sqlite3")
        apply_web_migrations(self.storage)

    def drop_budget_tables(self) -> list[str]:
        with self.storage.connect() as conn:
            names = [r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('web_budget_reservations', 'web_budget_counters')")]
            for name in names:
                conn.execute(f"DROP TABLE {name}")
            conn.commit()
        return names

    def test_reserve_is_denied_instead_of_silently_allowing_the_paid_call(self) -> None:
        now = T0
        limits = [BudgetLimit("purpose:brain", 1)]
        self.assertFalse(isinstance(BudgetLedger(self.storage).reserve("op-ok", provider="llm", purpose="brain", limits=limits, now=now), BudgetDenied),
                         "前提：迁移建好表之后是能预占的")
        self.assertEqual(sorted(self.drop_budget_tables()), list(BUDGET_TABLES), "迁移确实建了这两张表")

        denied = BudgetLedger(self.storage).reserve("op-1", provider="llm", purpose="brain", limits=limits, now=now)

        self.assertEqual((type(denied), denied.reason), (BudgetDenied, "ledger_unavailable"), "表没了就明确拒绝，不放行付费调用")
        self.assertEqual(BudgetLedger(self.storage).expire_stale(now=now), 0, "清理过期预占也不报成功")

    def test_provider_cap_stays_atomic_without_the_ledger(self) -> None:
        self.drop_budget_tables()
        meter = ProviderMeter(self.storage, {"llm": 1})
        self.assertEqual([meter.allow("llm"), meter.allow("llm")], [True, False], "供应商自己的每日上限不依赖额度账本")


if __name__ == "__main__":
    unittest.main()
