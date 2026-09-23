"""0500：统一物资库存（收成、偷来的菜等可出售物资）与居民订单。游戏币仍只在 pet_wallets.travel_coin。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_inventory (
            pet_id TEXT NOT NULL,
            item_key TEXT NOT NULL,
            user_id TEXT NOT NULL,
            qty INTEGER NOT NULL CHECK (qty >= 0),
            updated_at TEXT NOT NULL,
            PRIMARY KEY (pet_id, item_key)
        )
        """
    )
    # 每一次库存变动一条记录；source_key 唯一 → 收获/偷取/出售/交单重放不重复生效。
    conn.execute(
        """
        CREATE TABLE web_inventory_moves (
            move_id TEXT PRIMARY KEY,
            pet_id TEXT NOT NULL,
            item_key TEXT NOT NULL,
            delta INTEGER NOT NULL,
            reason TEXT NOT NULL,
            source_key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE web_resident_orders (
            order_id TEXT PRIMARY KEY,
            home_id TEXT NOT NULL,
            day TEXT NOT NULL,
            slot INTEGER NOT NULL,
            resident TEXT NOT NULL,
            item_key TEXT NOT NULL,
            qty INTEGER NOT NULL,
            reward INTEGER NOT NULL,
            fulfilled_at TEXT,
            UNIQUE (home_id, day, slot)
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="0500_inventory",
    module="economy",
    description="produce inventory with idempotent moves + daily resident orders",
    apply=_apply,
)
