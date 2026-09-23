"""0230：共同 DNA 的来源与版本。

同一只宠物的 DNA 是全家共用的一份，但每次修改都要留下是谁改的、改成了什么；带着旧版本号提交的修改会被拒绝（409），
不再无声覆盖别人的改动。主人个人的称呼与私人偏好放在关系层（web_pet_relationships）与各自的接待记录里，不写进共同 DNA。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE web_pet_dna ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
    conn.execute("ALTER TABLE web_pet_dna ADD COLUMN updated_by TEXT")
    conn.execute("UPDATE web_pet_dna SET updated_by = user_id WHERE updated_by IS NULL")
    conn.execute(
        """
        CREATE TABLE web_pet_dna_history (
            pet_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            updated_by TEXT,
            dna_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (pet_id, version)
        )
        """
    )
    conn.execute(
        "INSERT INTO web_pet_dna_history (pet_id, version, updated_by, dna_json, created_at) SELECT pet_id, version, user_id, dna_json, updated_at FROM web_pet_dna"
    )


MIGRATION = WebMigration(
    migration_id="0230_dna_versions",
    module="pets",
    description="shared pet DNA keeps editor and version history; stale writes are rejected instead of silently overwriting",
    apply=_apply,
)
