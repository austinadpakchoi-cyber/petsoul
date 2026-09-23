"""0300：接待草稿（私有、24 小时可恢复）、入住叮嘱 CareNote、逐项用途授权 MemoryGrant、确认记录。

与旧 memories 表完全分开；旧记录不会因本迁移获得新用途授权。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_reception_sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            pet_id TEXT NOT NULL,
            branch TEXT NOT NULL,
            mode TEXT NOT NULL,
            status TEXT NOT NULL,
            draft_revision INTEGER NOT NULL DEFAULT 1,
            turns_json TEXT NOT NULL,
            candidates_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_reception_user_pet ON web_reception_sessions (user_id, pet_id, status)")
    conn.execute(
        """
        CREATE TABLE web_care_notes (
            note_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            pet_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            subject TEXT NOT NULL,
            text TEXT NOT NULL,
            target TEXT NOT NULL CHECK (target IN ('give_to_pet', 'keep_here')),
            purposes_json TEXT NOT NULL,
            slot TEXT,
            slot_value TEXT,
            version INTEGER NOT NULL,
            confirmed_at TEXT NOT NULL,
            supersedes_note_id TEXT,
            revoked_at TEXT,
            confirmation_id TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_care_notes_user_pet ON web_care_notes (user_id, pet_id)")
    conn.execute(
        """
        CREATE TABLE web_memory_grants (
            grant_id TEXT PRIMARY KEY,
            note_id TEXT NOT NULL REFERENCES web_care_notes(note_id) ON DELETE CASCADE,
            note_version INTEGER NOT NULL,
            purpose TEXT NOT NULL,
            user_id TEXT NOT NULL,
            pet_id TEXT NOT NULL,
            granted_at TEXT NOT NULL,
            revoked_at TEXT,
            UNIQUE (note_id, note_version, purpose)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE web_intake_confirmations (
            confirmation_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            draft_revision INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (session_id, draft_revision)
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="0300_reception",
    module="reception",
    description="private reception drafts, care notes, per-purpose memory grants, confirmations",
    apply=_apply,
)
