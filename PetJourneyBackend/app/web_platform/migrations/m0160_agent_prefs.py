"""0160：宠物自主世界的账号偏好——主人所在时区（安静时段按它计算）、是否接收 TA 主动发来的消息、最近活跃时间。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE web_user_prefs ADD COLUMN timezone TEXT")
    conn.execute("ALTER TABLE web_user_prefs ADD COLUMN pet_messages INTEGER NOT NULL DEFAULT 1")
    conn.execute("ALTER TABLE web_user_prefs ADD COLUMN last_active_at TEXT")


MIGRATION = WebMigration(
    migration_id="0160_agent_prefs",
    module="identity",
    description="owner timezone for quiet hours, pet-initiated message opt-out, last activity",
    apply=_apply,
)
