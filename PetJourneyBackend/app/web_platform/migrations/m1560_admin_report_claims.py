"""1560：举报认领（方案 §3「社区审核与客服：举报分派」）。

一条被举报的内容（按 target 记，因为下架 / 恢复 / 不处理都作用在内容上，一次处理掉这条内容的所有举报）
同一时刻最多由一位审核员认领。认领带过期时间，人走开了不会把这条永远锁住；过期之后别人可以接手。

这张表只存**当前**认领；谁在什么时候认领、放弃、接手，全部进审计（admin_audit，仅追加）。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE admin_report_claims (
            target_kind TEXT NOT NULL,
            target_id TEXT NOT NULL,
            staff_id TEXT NOT NULL,
            claimed_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            PRIMARY KEY (target_kind, target_id)
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="1560_admin_report_claims",
    module="web_admin",
    description="moderation claims: one reviewer per reported target at a time, with expiry",
    apply=_apply,
)
