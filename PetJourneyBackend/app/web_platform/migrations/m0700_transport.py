"""0700：动物世界承运身份注册表（唯一键 + 映射版本）与现实交通参考（核验数据导入位）。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_world_services (
            world_service_id TEXT PRIMARY KEY,
            service_key TEXT NOT NULL UNIQUE,
            carrier_name TEXT NOT NULL,
            service_code TEXT NOT NULL,
            mode TEXT NOT NULL,
            vehicle_style TEXT,
            reference_id TEXT,
            mapping_version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            UNIQUE (carrier_name, service_code, mapping_version)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE web_transport_references (
            reference_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            operating_instance_id TEXT NOT NULL,
            service_date TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            time_basis TEXT NOT NULL,
            freshness TEXT NOT NULL,
            verified_at TEXT,
            source_url TEXT,
            created_at TEXT NOT NULL,
            UNIQUE (provider, operating_instance_id, service_date)
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="0700_transport",
    module="transport",
    description="stable animal-world service registry + real transport reference import slot",
    apply=_apply,
)
