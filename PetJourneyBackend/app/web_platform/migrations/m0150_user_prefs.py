"""0150：账号级偏好（均默认关闭，由主人明确开启）：模型回信、生成冒险插画。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_user_prefs (
            user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
            model_replies INTEGER NOT NULL DEFAULT 0,
            generated_photos INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="0150_user_prefs",
    module="identity",
    description="per-account opt-ins: model-written replies, generated adventure illustrations",
    apply=_apply,
)
