"""1400：证件卡包——稳定唯一的证件编号、持久签发时间、同一事件只签发一次；护照纪念章。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_credentials (
            credential_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            pet_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            number TEXT NOT NULL UNIQUE,
            source_key TEXT NOT NULL,
            issued_at TEXT NOT NULL,
            title TEXT,
            data_json TEXT NOT NULL,
            links_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (pet_id, kind, source_key)
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_credentials_pet ON web_credentials (pet_id, kind)")
    conn.execute(
        """
        CREATE TABLE web_passport_stamps (
            pet_id TEXT NOT NULL,
            journey_id TEXT NOT NULL,
            city TEXT NOT NULL,
            title TEXT NOT NULL,
            stamped_at TEXT NOT NULL,
            PRIMARY KEY (pet_id, journey_id, city)
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="1400_credentials",
    module="credentials",
    description="credential wallet: stable numbers, persistent issue time, one issue per event; passport stamps",
    apply=_apply,
)
