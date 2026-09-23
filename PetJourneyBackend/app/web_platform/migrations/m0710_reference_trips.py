"""0710：现实参考班次（按服务日期落地的已核验船期），动物世界承运编号可以追溯到这里。

一条参考班次＝某份已核验时刻表在某个服务日期的一次开航（当地出发时间 → UTC 起止）；记下来源网址、抓取时间与原始页面摘要。
同一班船上的所有宠物共用同一个动物世界编号（web_world_services.reference_id 指向这里）。这是现实参考资料，不是订票。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_transport_reference_trips (
            reference_id TEXT PRIMARY KEY,
            timetable_id TEXT NOT NULL,
            direction TEXT NOT NULL,
            service_date TEXT NOT NULL,
            departure_local TEXT NOT NULL,
            timezone TEXT NOT NULL,
            departure_utc TEXT NOT NULL,
            arrival_utc TEXT NOT NULL,
            origin_hub TEXT NOT NULL,
            destination_hub TEXT NOT NULL,
            operator TEXT NOT NULL,
            duration_basis TEXT NOT NULL,
            source_url TEXT NOT NULL,
            source_fetched_at TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_reference_trips_date ON web_transport_reference_trips (timetable_id, direction, service_date)")


MIGRATION = WebMigration(
    migration_id="0710_reference_trips",
    module="transport",
    description="verified timetable sailings materialized per service date; world services trace back to them",
    apply=_apply,
)
