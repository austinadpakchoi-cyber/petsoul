"""1520：批量游戏补偿（提交 → 审批 → 执行，三步各自留痕）。

批次本身只是"要发什么"的清单与审批状态；**钱的真相仍然只有一本账**——
每一条执行都走 `economy_transactions`（幂等键 `admin:batch:<batch_id>:<pet_id>`），
这里不保存余额、不保存第二份账。

为什么要三张状态而不是一个布尔：提交人与审批人必须是两个人（双人原则），
执行结果还要**逐条**记成功/跳过/失败——"批次已提交"不能显示成"钱已经发出去了"。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE admin_grant_batches (
            batch_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            reason TEXT NOT NULL,
            amount_per_pet INTEGER NOT NULL,
            recipient_count INTEGER NOT NULL,
            total_amount INTEGER NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending_approval', 'approved', 'rejected', 'executed', 'failed')),
            version INTEGER NOT NULL DEFAULT 1,
            submitted_by TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            decided_by TEXT,
            decided_at TEXT,
            decision_note TEXT,
            executed_by TEXT,
            executed_at TEXT,
            applied_count INTEGER,
            skipped_count INTEGER,
            applied_amount INTEGER,
            operation_id TEXT NOT NULL UNIQUE
        )
        """
    )
    conn.execute("CREATE INDEX idx_admin_grant_batches_status ON admin_grant_batches (status, submitted_at DESC)")
    conn.execute(
        """
        CREATE TABLE admin_grant_batch_items (
            batch_id TEXT NOT NULL REFERENCES admin_grant_batches(batch_id) ON DELETE CASCADE,
            pet_id TEXT NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'applied', 'skipped', 'failed')),
            outcome TEXT,
            ledger_key TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (batch_id, pet_id)
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="1520_admin_grant_batches",
    module="web_admin",
    description="batched game compensation with two-person approval and per-recipient outcomes",
    apply=_apply,
)
