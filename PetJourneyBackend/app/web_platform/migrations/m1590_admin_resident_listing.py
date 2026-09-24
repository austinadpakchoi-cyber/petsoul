"""1590：撤下 / 放回待领养居民——谁、为什么、第几版（用户 2026-09-25 把撤下交给运营后台）。

生效的开关在领养卡表上：`web_adoption_candidates.listed`（宠物区间的迁移 0260；玩家侧读名单的四处与领养入口都认它）。
这张表只记**后台这一侧的依据**：现在是否上架、原因、谁改的、什么时候、版本号（并发改同一位时按版本拒绝后到的）。
两者在同一个事务里写。改了几次、每次谁改的，全部进审计（admin_audit，仅追加：resident.delist / resident.relist）。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE admin_resident_listing (
            candidate_id TEXT PRIMARY KEY,
            listed INTEGER NOT NULL CHECK (listed IN (0, 1)),
            reason TEXT NOT NULL,
            changed_by TEXT NOT NULL,
            changed_at TEXT NOT NULL,
            version INTEGER NOT NULL
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="1590_admin_resident_listing",
    module="web_admin",
    description="why an adoption candidate is delisted or relisted: reason, who, when, version (the switch itself is web_adoption_candidates.listed)",
    apply=_apply,
)
