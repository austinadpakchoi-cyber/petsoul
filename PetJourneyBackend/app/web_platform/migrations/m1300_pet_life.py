"""1300：TA 自己的生活——每半小时的“出不出门”决定（去重、可追溯）与主人的建议（只作参考，由 TA 决定）。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_pet_decisions (
            pet_id TEXT NOT NULL,
            slot_key TEXT NOT NULL,
            decision TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (pet_id, slot_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE web_owner_suggestions (
            suggestion_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            pet_id TEXT NOT NULL,
            destination_key TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'passed', 'replaced')),
            created_at TEXT NOT NULL,
            decided_at TEXT
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_suggestions_pet ON web_owner_suggestions (pet_id, status, created_at)")


MIGRATION = WebMigration(
    migration_id="1300_pet_life",
    module="agent",
    description="pet's own outing decisions per half-hour slot and owner suggestions (advisory only)",
    apply=_apply,
)
