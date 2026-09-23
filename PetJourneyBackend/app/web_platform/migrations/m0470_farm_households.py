"""0470：串门偷菜按“家庭”计次。

同一个家庭的几位成员去同一块别人的菜地，摘到的菜都进同一个家庭仓库；为防止多人分别操作刷收益，每一茬菜每个家庭只能摘一次
（原来按人计次：web_farm_steals 主键仍是 (cycle_id, thief_user_id)，这里再加一道按家庭的唯一约束）。自家成员不能“偷”自家的菜。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE web_farm_steals ADD COLUMN thief_household_id TEXT")
    conn.execute(
        "UPDATE web_farm_steals SET thief_household_id = (SELECT h.household_id FROM web_homes h WHERE h.user_id = web_farm_steals.thief_user_id)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX idx_web_farm_steals_household ON web_farm_steals (cycle_id, thief_household_id) WHERE thief_household_id IS NOT NULL"
    )


MIGRATION = WebMigration(
    migration_id="0470_farm_households",
    module="farm",
    description="one steal per crop cycle per thief household (members of one household share the pantry)",
    apply=_apply,
)
