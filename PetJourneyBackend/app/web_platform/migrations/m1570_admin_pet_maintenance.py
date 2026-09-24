"""1570：暂停一只宠物的自主运行——谁、为什么、第几版（居民需求 §6「世界运行：开启 / 暂停新决定」）。

生效的开关是运行表 `web_entity_runtime.maintenance`（迁移 0060 就有，心跳与各条运行线都认它）；
这张表只记**后台这一侧的依据**：当前是不是暂停、原因、谁改的、什么时候、版本号（并发改同一只时按版本拒绝后到的）。
两者在同一个事务里写。改了几次、每次谁改的，全部进审计（admin_audit，仅追加）。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE admin_pet_maintenance (
            pet_id TEXT PRIMARY KEY,
            paused INTEGER NOT NULL CHECK (paused IN (0, 1)),
            reason TEXT NOT NULL,
            changed_by TEXT NOT NULL,
            changed_at TEXT NOT NULL,
            version INTEGER NOT NULL
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="1570_admin_pet_maintenance",
    module="web_admin",
    description="why a pet's autonomous runtime is paused: reason, who, when, version (the switch itself is web_entity_runtime.maintenance)",
    apply=_apply,
)
