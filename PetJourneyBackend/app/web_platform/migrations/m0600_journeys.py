"""0600：旅程、门到门分段、到访与世界事件（一次到访贯穿地图/店内/通讯/动态；事件幂等只执行一次）。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_journeys (
            journey_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            pet_id TEXT NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
            home_id TEXT NOT NULL,
            destination_key TEXT NOT NULL,
            title TEXT NOT NULL,
            city TEXT NOT NULL,
            lifecycle TEXT NOT NULL CHECK (lifecycle IN ('active', 'completed', 'cancelled')),
            itinerary_version INTEGER NOT NULL DEFAULT 1,
            fee INTEGER NOT NULL,
            departed_at TEXT NOT NULL,
            completes_at TEXT NOT NULL,
            completed_at TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    # 同一宠物同时最多一段进行中的旅程：宠物唯一位置。
    conn.execute("CREATE UNIQUE INDEX idx_web_journeys_one_active ON web_journeys (pet_id) WHERE lifecycle = 'active'")
    conn.execute(
        """
        CREATE TABLE web_journey_legs (
            leg_id TEXT PRIMARY KEY,
            journey_id TEXT NOT NULL REFERENCES web_journeys(journey_id) ON DELETE CASCADE,
            sequence INTEGER NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('outbound', 'return')),
            kind TEXT NOT NULL,
            mode TEXT NOT NULL,
            role TEXT NOT NULL,
            world_service_id TEXT,
            origin_json TEXT NOT NULL,
            destination_json TEXT NOT NULL,
            starts_at TEXT NOT NULL,
            ends_at TEXT NOT NULL,
            time_basis TEXT NOT NULL,
            freshness TEXT NOT NULL,
            position_basis TEXT NOT NULL,
            route_json TEXT NOT NULL,
            UNIQUE (journey_id, sequence)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE web_visits (
            visit_id TEXT PRIMARY KEY,
            journey_id TEXT NOT NULL UNIQUE REFERENCES web_journeys(journey_id) ON DELETE CASCADE,
            pet_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            place_json TEXT NOT NULL,
            template TEXT NOT NULL,
            starts_at TEXT NOT NULL,
            ends_at TEXT NOT NULL,
            recommendation_id TEXT,
            activities_json TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE web_world_events (
            journey_id TEXT NOT NULL REFERENCES web_journeys(journey_id) ON DELETE CASCADE,
            event_key TEXT NOT NULL,
            kind TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            PRIMARY KEY (journey_id, event_key)
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="0600_journeys",
    module="journey",
    description="journeys, door-to-door legs, visits, idempotent world events",
    apply=_apply,
)
