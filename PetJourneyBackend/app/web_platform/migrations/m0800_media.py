"""0800：同行影音会话覆盖（共同暂停/恢复/拖动、控制租约、到站保存）与主人实际参与记录。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_media_sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            pet_id TEXT NOT NULL,
            leg_id TEXT NOT NULL,
            activity_index INTEGER NOT NULL,
            state TEXT NOT NULL,
            anchor_position_ms INTEGER NOT NULL,
            anchor_server_time TEXT NOT NULL,
            playback_rate REAL NOT NULL DEFAULT 1.0,
            revision INTEGER NOT NULL,
            lease_device TEXT,
            lease_expires_at TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE web_media_participation (
            session_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            since TEXT NOT NULL,
            last_heartbeat_at TEXT,
            counted_ms INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (session_id, device_id)
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_media_participation_user ON web_media_participation (user_id, session_id)")


MIGRATION = WebMigration(
    migration_id="0800_media",
    module="companion_media",
    description="companion media session overrides + owner participation",
    apply=_apply,
)
