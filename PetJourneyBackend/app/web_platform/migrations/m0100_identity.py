"""0100：网页账号（用户名+口令哈希）与可吊销会话。账号复用既有 users 表作为身份主键。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_accounts (
            user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
            username TEXT NOT NULL,
            username_key TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            password_updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE web_sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_sessions_user ON web_sessions (user_id, revoked_at)")


MIGRATION = WebMigration(
    migration_id="0100_identity",
    module="identity",
    description="web password accounts + revocable sessions",
    apply=_apply,
)
