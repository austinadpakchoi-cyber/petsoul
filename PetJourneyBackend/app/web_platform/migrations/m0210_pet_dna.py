"""0210：宠物 DNA（主人确认、可随时修改的性格与习惯档案）。模型扮演宠物时读取它，让主人感到熟悉。

confirmed_at 为空表示系统按领养资料/简介/接待叮嘱整理的草稿，主人保存后才算确认。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_pet_dna (
            pet_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            dna_json TEXT NOT NULL,
            confirmed_at TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="0210_pet_dna",
    module="pets",
    description="owner-confirmed pet DNA (personality, voice, habits) used for role-play",
    apply=_apply,
)
