"""1210：邮局明信片——TA 在旅途中路过邮局写给主人的话、写实自拍（生图任务）与寄出的地点。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    for column in ("note", "image_url", "image_status", "image_task_id", "place", "city"):
        conn.execute(f"ALTER TABLE web_collection_items ADD COLUMN {column} TEXT")


MIGRATION = WebMigration(
    migration_id="1210_postcard_notes",
    module="collection",
    description="post-office postcards: pet's note, realistic selfie task/status, place and city",
    apply=_apply,
)
