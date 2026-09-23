"""0510：家庭仓库。家园收成、串门摘来的菜先进“这个家”的仓库，而不是某一只宠物名下（多宠家庭共用一个家）。

- web_home_inventory：(home_id, item_key) → 数量；
- web_home_inventory_moves：每次变动一条，source_key 唯一（收获/偷取/出售/交单重放不重复生效），记录是哪位成员、为哪只宠物操作；
- 旧数据：web_inventory 按宠物记的物资原样搬到它所在的家（旧库一宠一家，一一对应），旧 source_key 一并迁移，重放仍然去重；
  旧表保留不删（只读历史），此后不再写入。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_home_inventory (
            home_id TEXT NOT NULL,
            item_key TEXT NOT NULL,
            qty INTEGER NOT NULL CHECK (qty >= 0),
            updated_at TEXT NOT NULL,
            PRIMARY KEY (home_id, item_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE web_home_inventory_moves (
            move_id TEXT PRIMARY KEY,
            home_id TEXT NOT NULL,
            item_key TEXT NOT NULL,
            delta INTEGER NOT NULL,
            reason TEXT NOT NULL,
            source_key TEXT NOT NULL UNIQUE,
            actor_user_id TEXT,
            pet_id TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_home_inventory_moves_home ON web_home_inventory_moves (home_id, created_at)")
    homes = {row["pet_id"]: row["home_id"] for row in conn.execute("SELECT home_id, pet_id FROM web_homes").fetchall()}
    for row in conn.execute("SELECT * FROM web_inventory").fetchall():
        home_id = homes.get(row["pet_id"])
        if home_id is None:
            continue
        conn.execute(
            "INSERT INTO web_home_inventory (home_id, item_key, qty, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(home_id, item_key) DO UPDATE SET qty = qty + excluded.qty",
            (home_id, row["item_key"], row["qty"], row["updated_at"]),
        )
    for row in conn.execute("SELECT * FROM web_inventory_moves").fetchall():
        home_id = homes.get(row["pet_id"])
        if home_id is None:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO web_home_inventory_moves (move_id, home_id, item_key, delta, reason, source_key, actor_user_id, pet_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)",
            (row["move_id"], home_id, row["item_key"], row["delta"], row["reason"], row["source_key"], row["pet_id"], row["created_at"]),
        )


MIGRATION = WebMigration(
    migration_id="0510_home_pantry",
    module="economy",
    description="household pantry keyed by home (shared by all pets of a household); legacy per-pet inventory moved with its source keys",
    apply=_apply,
)
