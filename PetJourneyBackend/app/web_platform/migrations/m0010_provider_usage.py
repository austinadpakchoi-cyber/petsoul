"""0010：真实供应商调用计量与缓存（平台共享）。只记次数、失败与最近错误摘要（已脱敏），不记请求正文或密钥。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_provider_usage (
            day TEXT NOT NULL,
            provider TEXT NOT NULL,
            calls INTEGER NOT NULL DEFAULT 0,
            failures INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (day, provider)
        )
        """
    )
    # 地点/路线结果缓存：同一请求一天内复用，降低费用与延迟（不缓存模型与生图结果）
    conn.execute(
        """
        CREATE TABLE web_geo_cache (
            cache_key TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="0010_provider_usage",
    module="platform",
    description="provider call metering (daily caps) and geo result cache",
    apply=_apply,
)
