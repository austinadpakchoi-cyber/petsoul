"""0050：付费调用的操作级额度预占（平台共享；DDL 由包 A 提出，见其 2026-09-23 00:43 交接）。

- web_budget_reservations：每个 operation_id 一条预占（重放不重复预占）；外部是否受理不明时记 unknown，保守计入已用，不盲目重发；
- web_budget_counters：按 UTC 记账日与额度层级累计已用 / 在途，跨进程原子检查所有层级。
星币账本与 API 费用是两本账，这里只管调用次数/单位。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_budget_reservations (
            reservation_id TEXT PRIMARY KEY,
            operation_id TEXT NOT NULL UNIQUE,
            provider TEXT NOT NULL,
            purpose TEXT NOT NULL,
            subject_scope TEXT NOT NULL,
            accounting_window TEXT NOT NULL,
            scope_pairs_json TEXT NOT NULL,
            reserved_units INTEGER NOT NULL CHECK (reserved_units > 0),
            actual_units INTEGER,
            status TEXT NOT NULL CHECK (status IN ('reserved', 'settled', 'released', 'unknown', 'expired')),
            outcome TEXT CHECK (outcome IS NULL OR outcome IN ('succeeded', 'failed', 'not_sent', 'unknown')),
            provider_request_id TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            settled_at TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_budget_reservations_open ON web_budget_reservations (status, expires_at)")
    conn.execute(
        """
        CREATE TABLE web_budget_counters (
            window_key TEXT NOT NULL,
            scope_key TEXT NOT NULL,
            used_units INTEGER NOT NULL DEFAULT 0 CHECK (used_units >= 0),
            inflight_units INTEGER NOT NULL DEFAULT 0 CHECK (inflight_units >= 0),
            updated_at TEXT NOT NULL,
            PRIMARY KEY (window_key, scope_key)
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="0050_budget",
    module="platform",
    description="operation-level budget reservations and per-window counters for paid provider calls (package A)",
    apply=_apply,
)
