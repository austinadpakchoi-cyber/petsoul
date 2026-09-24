"""0415：把旧库里已经落在海面上的家挪回陆地（6c2b 2026-09-24 巡检：「香港·西贡的海边」的家落在海里，宠物在水里走）。

`web_home_places` 里每个家的坐标是 `assign()` 当时按「片区参考点周围随机偏移最多 900 米」写进去的。现在有陆地锚点的片区
（中环、西贡，见 `web_home.place.LAND_ANCHORS`）改成落在某个锚点 40 米内；这里按**同一个种子**（`home_id:habitat:chosen_at`，
与 `assign()` 写库时一致）重算一遍，所以挪过去的点与新家的算法完全相同，同一个家每次算出同一点。
没有锚点的片区不动；没选过环境的家本来就不在这张表里（读的时候现算，已经走新算法）。
"""

from __future__ import annotations

import sqlite3

from ...web_home.place import LAND_ANCHORS, land_point
from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    marks = ",".join("?" for _ in LAND_ANCHORS)
    rows = conn.execute(f"SELECT home_id, habitat, area_key, chosen_at FROM web_home_places WHERE area_key IN ({marks})",
                        tuple(LAND_ANCHORS)).fetchall()
    for row in rows:
        lat, lng = land_point(row["area_key"], f"{row['home_id']}:{row['habitat']}:{row['chosen_at']}")
        conn.execute("UPDATE web_home_places SET lat = ?, lng = ? WHERE home_id = ?", (lat, lng, row["home_id"]))


MIGRATION = WebMigration(
    migration_id="0415_home_places_on_land",
    module="home",
    description="move stored homes in coastal areas onto verified land anchors (same seed as assign)",
    apply=_apply,
)
