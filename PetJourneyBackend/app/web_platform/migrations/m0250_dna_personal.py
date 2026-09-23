"""0250：DNA 的个人层。

一只宠物的 DNA 分两层：全家共用的（性格、说话方式、口头禅、喜好、小习惯、害怕的东西、小名）与每位家人各自的。
个人层里：TA 怎么称呼这位家人放在家庭关系表（web_pet_relationships.owner_title，见 0430），
和这位家人之间的小暗号与趣事放在这里；个人层只在和这位家人的私信里使用，别的家人看不到，也不会被别人的保存覆盖。
旧数据：原来写在共用 DNA 里的小暗号，归给当初保存它的那位主人（web_pet_dna.user_id）。
"""

from __future__ import annotations

import json
import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_pet_dna_personal (
            pet_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            shared_memories_json TEXT NOT NULL DEFAULT '[]',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (pet_id, user_id)
        )
        """
    )
    for row in conn.execute("SELECT pet_id, user_id, dna_json, updated_at FROM web_pet_dna").fetchall():
        try:
            memories = json.loads(row["dna_json"]).get("shared_memories") or []
        except ValueError:
            continue
        if memories:
            conn.execute("INSERT OR IGNORE INTO web_pet_dna_personal (pet_id, user_id, shared_memories_json, updated_at) VALUES (?, ?, ?, ?)",
                         (row["pet_id"], row["user_id"], json.dumps(memories, ensure_ascii=False), row["updated_at"]))


MIGRATION = WebMigration(
    migration_id="0250_dna_personal",
    module="pets",
    description="per-member DNA layer (private shared memories with each member); legacy values go to the member who saved them",
    apply=_apply,
)
