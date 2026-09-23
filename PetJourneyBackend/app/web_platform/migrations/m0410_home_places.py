"""0410：TA 的家在哪（一个概念）：主人选的类型（海边/草原/……）与随机到的片区；坐标已模糊处理，不对应门牌。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_home_places (
            home_id TEXT PRIMARY KEY,
            habitat TEXT NOT NULL,
            area_key TEXT NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            chosen_at TEXT NOT NULL
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="0410_home_places",
    module="home",
    description="home as a concept: habitat chosen by owner, random fuzzed area in a real city",
    apply=_apply,
)
