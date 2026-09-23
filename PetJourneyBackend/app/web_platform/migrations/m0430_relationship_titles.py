"""0430：TA 怎么称呼每位家人，统一放在家庭关系表（web_pet_relationships.owner_title）。

旧数据：原来写在共用 DNA 里的称呼，归给当初保存 DNA 的那位主人；关系表里已经有称呼的不覆盖。
称呼只是称呼，不带任何权限（权限只看 web_household_members.role）。
"""

from __future__ import annotations

import json
import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    for row in conn.execute("SELECT pet_id, user_id, dna_json, updated_at FROM web_pet_dna").fetchall():
        try:
            title = (json.loads(row["dna_json"]).get("owner_title") or "").strip()[:12]
        except ValueError:
            continue
        if not title:
            continue
        conn.execute(
            "INSERT INTO web_pet_relationships (pet_id, user_id, owner_title, relation_label, created_at, updated_at) VALUES (?, ?, ?, NULL, ?, ?) "
            "ON CONFLICT(pet_id, user_id) DO UPDATE SET owner_title = COALESCE(web_pet_relationships.owner_title, excluded.owner_title)",
            (row["pet_id"], row["user_id"], title, row["updated_at"], row["updated_at"]),
        )


MIGRATION = WebMigration(
    migration_id="0430_relationship_titles",
    module="home",
    description="how the pet addresses each member lives in web_pet_relationships; legacy DNA owner_title moves to the member who saved it",
    apply=_apply,
)
