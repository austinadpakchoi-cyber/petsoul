"""0040：世界事件 outbox（平台共享）。

世界事件在结算事务里登记——与工资入账、行程完成在同一个写事务——并为每个下游消费者各写一行：
家庭频道来信、公开动态、收藏与明信片、证件、朋友相遇、攻略……提交之后各自投递、各自退避重试。
一个下游失败不撤销已经成立的到站或工资，也不挡其他下游；这一行本身就是该下游的消费回执（delivered）。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_outbox (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            consumer TEXT NOT NULL,
            aggregate_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            effective_at TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TEXT NOT NULL,
            claimed_by TEXT,
            claimed_until TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL,
            delivered_at TEXT,
            UNIQUE (event_id, consumer)
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_outbox_due ON web_outbox (status, next_attempt_at)")
    conn.execute("CREATE INDEX idx_web_outbox_aggregate ON web_outbox (aggregate_id, consumer, seq)")


MIGRATION = WebMigration(
    migration_id="0040_outbox",
    module="platform",
    description="world-event outbox: one row per downstream consumer, written in the settlement transaction and delivered after commit",
    apply=_apply,
)
