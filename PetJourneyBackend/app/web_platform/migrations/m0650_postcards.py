"""0650：店内合影的原创插画明信片（私有存储；附到公开动态后才对其他登录用户可见）。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_postcards (
            photo_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            pet_id TEXT NOT NULL,
            visit_id TEXT NOT NULL UNIQUE,
            rel_path TEXT NOT NULL,
            is_public INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="0650_postcards",
    module="journey",
    description="original illustrated postcards from venue photo activity (private by default)",
    apply=_apply,
)
