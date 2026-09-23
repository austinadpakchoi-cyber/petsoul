"""家庭仓库：家园收成、串门摘来的菜等可出售物资，属于“这个家”（多宠家庭共用），不属于某一只宠物。

- 每次变动以 source_key 去重（收获/偷取/出售/交单重放不重复生效），并记下是哪位成员操作、和哪只宠物有关；
- 数量检查与变动在同一个写事务里完成：两位家人同时出售同一批菜，不会卖出超过库存的数量；
- 游戏币不在这里：出售或交单换成旅费时，经 WebEconomy 写进目标宠物自己的星球账户。个人纪念品、照片与关系记忆不进仓库、不可交易。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from ..storage import JourneyStorage
from ..utils import iso, utcnow


class WebInventory:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage

    def _move(self, actor_user_id: str | None, home_id: str, item_key: str, delta: int, reason: str, source_key: str, now: datetime | None,
              pet_id: str | None = None) -> bool:
        """返回 True 表示变动已生效（含重放）；数量不足时返回 False 且不变动。"""
        now = now or utcnow()
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM web_home_inventory_moves WHERE source_key = ?", (source_key,)).fetchone():
                return True
            row = conn.execute("SELECT qty FROM web_home_inventory WHERE home_id = ? AND item_key = ?", (home_id, item_key)).fetchone()
            current = int(row["qty"]) if row else 0
            if current + delta < 0:
                conn.rollback()
                return False
            if row is None:
                conn.execute("INSERT INTO web_home_inventory (home_id, item_key, qty, updated_at) VALUES (?, ?, ?, ?)", (home_id, item_key, delta, iso(now)))
            else:
                conn.execute("UPDATE web_home_inventory SET qty = qty + ?, updated_at = ? WHERE home_id = ? AND item_key = ?", (delta, iso(now), home_id, item_key))
            conn.execute(
                "INSERT INTO web_home_inventory_moves (move_id, home_id, item_key, delta, reason, source_key, actor_user_id, pet_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"mv-{uuid.uuid4().hex[:12]}", home_id, item_key, delta, reason, source_key, actor_user_id, pet_id, iso(now)),
            )
        return True

    def add(self, actor_user_id: str | None, home_id: str, item_key: str, qty: int, reason: str, source_key: str, now: datetime | None = None,
            pet_id: str | None = None) -> bool:
        if qty <= 0:
            return True
        return self._move(actor_user_id, home_id, item_key, qty, reason, source_key, now, pet_id)

    def remove(self, actor_user_id: str | None, home_id: str, item_key: str, qty: int, reason: str, source_key: str, now: datetime | None = None,
               pet_id: str | None = None) -> bool:
        return self._move(actor_user_id, home_id, item_key, -abs(qty), reason, source_key, now, pet_id)

    def quantities(self, home_id: str) -> dict[str, int]:
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT item_key, qty FROM web_home_inventory WHERE home_id = ? AND qty > 0 ORDER BY item_key", (home_id,)).fetchall()
        return {r["item_key"]: int(r["qty"]) for r in rows}
