"""0450：菜园地块与互偷记录。每批作物（cycle）有统一成熟时间与全体共享的可偷上限。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_farm_plots (
            plot_id TEXT PRIMARY KEY,
            home_id TEXT NOT NULL REFERENCES web_homes(home_id) ON DELETE CASCADE,
            slot INTEGER NOT NULL,
            cycle_id TEXT,
            crop_key TEXT,
            planted_at TEXT,
            ripe_at TEXT,
            stolen_units INTEGER NOT NULL DEFAULT 0,
            harvested_at TEXT,
            version INTEGER NOT NULL DEFAULT 1,
            UNIQUE (home_id, slot)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE web_farm_steals (
            cycle_id TEXT NOT NULL,
            thief_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            plot_id TEXT NOT NULL,
            victim_home_id TEXT NOT NULL,
            units INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (cycle_id, thief_user_id)
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_farm_steals_thief ON web_farm_steals (thief_user_id, created_at)")


MIGRATION = WebMigration(
    migration_id="0450_farm",
    module="farm",
    description="farm plots with shared steal cap + per-visitor steal records",
    apply=_apply,
)
