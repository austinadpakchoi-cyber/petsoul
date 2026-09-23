"""0400：共同的家。首发一个账号一个家、一只主宠物；入住激活与接待是否跳过分开记录。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_homes (
            home_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
            pet_id TEXT NOT NULL UNIQUE REFERENCES pets(pet_id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            activated_at TEXT,
            reception_session_id TEXT,
            reception_skipped INTEGER NOT NULL DEFAULT 0,
            public_posts INTEGER NOT NULL DEFAULT 0,
            version INTEGER NOT NULL DEFAULT 1
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="0400_homes",
    module="home",
    description="one home per account bound to one exclusive pet; activation separate from reception",
    apply=_apply,
)
