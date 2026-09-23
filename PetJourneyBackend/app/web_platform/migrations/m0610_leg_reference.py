"""0610：每段交通记下它的时间从哪来（参考班次、路线估算的供应商与抓取时间/有效期、世界规则），页面据此如实标注。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE web_journey_legs ADD COLUMN reference_json TEXT")


MIGRATION = WebMigration(
    migration_id="0610_leg_reference",
    module="journey",
    description="per-leg source of timing (reference sailing, routed estimate provider/fetched/expiry, or world rule)",
    apply=_apply,
)
