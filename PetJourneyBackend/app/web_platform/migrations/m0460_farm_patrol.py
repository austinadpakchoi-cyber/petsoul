"""0460：主人巡院（宠物外出时主人可以短时守护菜园；有冷却，不能长期无敌）。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_farm_patrols (
            home_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            until TEXT NOT NULL
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="0460_farm_patrol",
    module="farm",
    description="owner patrol window guarding the garden while the pet travels",
    apply=_apply,
)
