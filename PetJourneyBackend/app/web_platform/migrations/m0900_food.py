"""0900：寻味偏好（宠物/主人分开，私人限制仅本人可见）、推荐快照（绑定行程版本）与主人实际用餐反馈。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_food_preferences (
            user_id TEXT NOT NULL,
            pet_id TEXT NOT NULL,
            subject TEXT NOT NULL CHECK (subject IN ('pet', 'owner')),
            preference_json TEXT NOT NULL,
            version INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, pet_id, subject)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE web_food_recommendations (
            recommendation_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            pet_id TEXT NOT NULL,
            batch_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            journey_id TEXT,
            itinerary_version INTEGER,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_food_recs_user ON web_food_recommendations (user_id, created_at)")
    conn.execute(
        """
        CREATE TABLE web_food_feedback (
            feedback_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            recommendation_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            verification TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="0900_food",
    module="food_discovery",
    description="pet/owner food preferences, recommendation snapshots bound to itinerary version, owner dining feedback",
    apply=_apply,
)
