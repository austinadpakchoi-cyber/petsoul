"""0660：冒险插画（生图任务结果，私有）。只在主人开启“生成冒险插画”且生图供应商可用时产生。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_illustrations (
            illustration_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            pet_id TEXT NOT NULL,
            source_event_id TEXT NOT NULL UNIQUE,
            task_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('processing', 'ready', 'failed')),
            rel_path TEXT,
            content_type TEXT,
            provider TEXT,
            model TEXT,
            used_reference_photo INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="0660_illustrations",
    module="journey",
    description="opt-in adventure illustrations produced by the image provider (private files)",
    apply=_apply,
)
