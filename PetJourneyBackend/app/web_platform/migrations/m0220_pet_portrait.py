"""0220：没有照片的伙伴（领养的原创伙伴）第一次需要画它时，先生成一张写实“证件照”作为它的样子；之后所有照片都以它为参考。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE web_pet_profiles ADD COLUMN photo_generated INTEGER NOT NULL DEFAULT 0")


MIGRATION = WebMigration(
    migration_id="0220_pet_portrait",
    module="pets",
    description="mark AI-generated identity portraits for pets without an owner photo",
    apply=_apply,
)
