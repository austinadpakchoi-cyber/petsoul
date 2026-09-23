"""1200：回忆与收藏（纪念品绑定宠物不可交易；稀有种子可种植/后续可交换；共同听看回忆私有）。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_collection_items (
            item_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            pet_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            item_key TEXT,
            title TEXT NOT NULL,
            tradable INTEGER NOT NULL,
            bound_to_pet INTEGER NOT NULL,
            source_event_id TEXT NOT NULL,
            obtained_at TEXT NOT NULL,
            consumed_at TEXT,
            UNIQUE (pet_id, source_event_id, kind)
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="1200_collection",
    module="collection",
    description="souvenirs, rare seeds and shared memories (bound vs tradable)",
    apply=_apply,
)
