"""1020：TA 在外面遇到的朋友——真实宠物（同一时间同一地点才算遇到）与星球居民；关系随见面次数累积。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_pet_friends (
            pet_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            friend_id TEXT NOT NULL,
            friend_kind TEXT NOT NULL CHECK (friend_kind IN ('pet', 'resident')),
            friend_name TEXT NOT NULL,
            first_met_at TEXT NOT NULL,
            last_met_at TEXT NOT NULL,
            meet_count INTEGER NOT NULL DEFAULT 1,
            last_place TEXT,
            places_json TEXT,
            PRIMARY KEY (pet_id, friend_id)
        )
        """
    )
    conn.execute("CREATE TABLE web_pet_encounters (encounter_key TEXT PRIMARY KEY, created_at TEXT NOT NULL)")


MIGRATION = WebMigration(
    migration_id="1020_friends",
    module="social",
    description="pets' friendships from real co-presence and clearly-labelled planet residents",
    apply=_apply,
)
