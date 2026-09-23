"""0060：每只宠物一行运行记录（平台共享；世界运行方案 v0.2 §10“每宠运行索引”）。

只放运行所需：语义版本代数、下次检查时刻、安静原因、上次评估与上次生活决定。钱包、库存、位置仍由原领域表持有。
版本代数的用处：思考开始时记下，提交时再比一次——中途改了 DNA、撤了授权、换了成员、活动变了，旧结论就不作数。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_entity_runtime (
            pet_id TEXT PRIMARY KEY,
            runtime_owner TEXT NOT NULL DEFAULT 'world',
            runtime_epoch INTEGER NOT NULL DEFAULT 0,
            activity_epoch INTEGER NOT NULL DEFAULT 0,
            privacy_epoch INTEGER NOT NULL DEFAULT 0,
            membership_epoch INTEGER NOT NULL DEFAULT 0,
            next_check_at TEXT,
            silence_reason TEXT,
            last_evaluated_at TEXT,
            next_review_at TEXT,
            last_decision_at TEXT,
            last_decision_by TEXT,
            maintenance INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_entity_runtime_due ON web_entity_runtime (next_check_at)")


MIGRATION = WebMigration(
    migration_id="0060_entity_runtime",
    module="platform",
    description="per-pet runtime row: semantic epochs, next check, silence reason, last evaluation and last life decision",
    apply=_apply,
)
