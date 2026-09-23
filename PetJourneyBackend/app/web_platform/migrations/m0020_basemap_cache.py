"""0020：网页底图（高德静态地图）缓存索引（平台共享）。图片文件在私有媒体目录，这里只记参数、来源与有效期。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_basemap_cache (
            basemap_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            zoom INTEGER NOT NULL,
            center_lat REAL NOT NULL,
            center_lng REAL NOT NULL,
            width INTEGER NOT NULL,
            height INTEGER NOT NULL,
            content_type TEXT NOT NULL,
            requested_by TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX ix_web_basemap_requester ON web_basemap_cache (requested_by, fetched_at)")


MIGRATION = WebMigration(
    migration_id="0020_basemap_cache",
    module="platform",
    description="static basemap image cache index (amap), 24h",
    apply=_apply,
)
