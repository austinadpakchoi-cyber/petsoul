"""1100：主人与专属宠物的私密通讯（client_message_id 幂等；宠物回复按其真实状态延后可见）。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_messages (
            message_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            pet_id TEXT NOT NULL,
            sender TEXT NOT NULL CHECK (sender IN ('owner', 'pet')),
            client_message_id TEXT,
            source_event_id TEXT,
            reply_to TEXT,
            text TEXT NOT NULL,
            photo_url TEXT,
            created_at TEXT NOT NULL,
            available_at TEXT NOT NULL,
            UNIQUE (pet_id, client_message_id),
            UNIQUE (pet_id, source_event_id)
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_messages_pet ON web_messages (pet_id, available_at)")
    conn.execute("CREATE TABLE web_message_reads (user_id TEXT NOT NULL, pet_id TEXT NOT NULL, last_read_at TEXT NOT NULL, PRIMARY KEY (user_id, pet_id))")


MIGRATION = WebMigration(
    migration_id="1100_communicator",
    module="communicator",
    description="private owner-pet messages with idempotent client ids and state-timed replies",
    apply=_apply,
)
