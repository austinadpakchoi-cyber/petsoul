"""0670：TA 的攻略手账——出门前写的一日小攻略（站点逐一用地图核对）与写实手账图（生图任务）。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_travel_guides (
            guide_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            pet_id TEXT NOT NULL,
            journey_id TEXT NOT NULL UNIQUE,
            city TEXT NOT NULL,
            destination_title TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT,
            stops_json TEXT NOT NULL,
            owner_tips_json TEXT NOT NULL,
            composed_by TEXT NOT NULL,
            image_status TEXT,
            image_url TEXT,
            image_task_id TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_guides_pet ON web_travel_guides (pet_id, created_at)")


MIGRATION = WebMigration(
    migration_id="0670_travel_guides",
    module="journey",
    description="pet-written travel guides with map-verified stops and a realistic journal page image",
    apply=_apply,
)
