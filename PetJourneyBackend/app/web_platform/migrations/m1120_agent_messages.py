"""1120：星球通讯器的自主回应——按 TA 的状态排队的回复（睡着等到醒来、飞行等到落地）、主动消息的话题与等待说明。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_pending_replies (
            owner_message_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            pet_id TEXT NOT NULL,
            due_at TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL,
            delivered_message_id TEXT
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_pending_due ON web_pending_replies (delivered_message_id, due_at)")
    conn.execute("ALTER TABLE web_messages ADD COLUMN topic TEXT")
    conn.execute("ALTER TABLE web_messages ADD COLUMN status_note TEXT")
    conn.execute("ALTER TABLE web_messages ADD COLUMN expected_at TEXT")


MIGRATION = WebMigration(
    migration_id="1120_agent_messages",
    module="communicator",
    description="state-queued pet replies, proactive message topics, waiting notes",
    apply=_apply,
)
