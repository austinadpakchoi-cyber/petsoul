"""集市服务：把仓库里的物资换成旅费。

- 杂货铺（NPC）按作物固定收购价收购；
- 居民订单：星球居民（公共 NPC，不是真实玩家）每天两张订单，出价比杂货铺高一半，每单只交一次；
- 物资扣减（WebInventory，source_key 去重）与旅费入账（WebEconomy，幂等键）都可安全重放；
- 玩家之间的挂牌交易未开放：不把 NPC 商店称为玩家市场。
- 0.4.0：仓库属于这个家（多宠家庭共用，WebInventory 按 home_id）；卖货与交单换来的旅费进“指定的那只宠物”的星球账户（pet_id 显式给出）。
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..schemas import EconomyTransactionType
from ..schemas.web.common import DataOrigin
from ..schemas.web.home import InventoryItem
from ..schemas.web.market import MarketResult, MarketView, ResidentOrder
from ..storage import JourneyStorage
from ..utils import iso, utcnow
from ..web_economy import WebEconomy, WebInventory
from ..web_farm import HomeRef
from ..web_farm.service import CROPS

ORDER_TZ = ZoneInfo("Asia/Hong_Kong")
ORDER_SLOTS = 2
ORDER_PREMIUM = 1.5
RESIDENTS = ("鹦鹉邮差", "松鼠面包师", "刺猬花匠", "水獭船长", "兔子裁缝")
COMMON_CROPS = ("sun_pea", "star_tomato", "moon_radish")
PLAYER_LISTING_NOTE = "玩家之间的挂牌交易还没开放（主线稳定后再评估一种物资的固定价挂牌）；这里是杂货铺和居民订单，都是星球居民。"


class MarketError(Exception):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


class WebMarket:
    def __init__(self, storage: JourneyStorage, economy: WebEconomy, inventory: WebInventory) -> None:
        self.storage = storage
        self.economy = economy
        self.inventory = inventory

    # ---- 读取 ----
    def pantry(self, home_id: str) -> list[InventoryItem]:
        return [InventoryItem(item_key=key, label=CROPS[key].label if key in CROPS else key, qty=qty, unit_price=CROPS[key].unit_value if key in CROPS else 0)
                for key, qty in self.inventory.quantities(home_id).items()]

    def _ensure_orders(self, home: HomeRef, now: datetime) -> str:
        day = now.astimezone(ORDER_TZ).date().isoformat()
        with self.storage.connect() as conn:
            for slot in range(ORDER_SLOTS):
                digest = int(hashlib.sha1(f"{home.home_id}:{day}:{slot}".encode()).hexdigest(), 16)
                item_key = COMMON_CROPS[(digest >> 8) % len(COMMON_CROPS)]
                qty = 2 + digest % 3
                reward = math.ceil(qty * CROPS[item_key].unit_value * ORDER_PREMIUM)
                conn.execute(
                    "INSERT OR IGNORE INTO web_resident_orders (order_id, home_id, day, slot, resident, item_key, qty, reward) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (f"ro-{home.home_id[-8:]}-{day.replace('-', '')}-{slot}", home.home_id, day, slot, RESIDENTS[(digest >> 16) % len(RESIDENTS)], item_key, qty, reward),
                )
        return day

    def orders(self, home: HomeRef, now: datetime | None = None) -> list[ResidentOrder]:
        now = now or utcnow()
        day = self._ensure_orders(home, now)
        have = self.inventory.quantities(home.home_id)
        local_midnight = datetime.fromisoformat(day).replace(tzinfo=ORDER_TZ) + timedelta(days=1)
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT * FROM web_resident_orders WHERE home_id = ? AND day = ? ORDER BY slot", (home.home_id, day)).fetchall()
        return [
            ResidentOrder(
                order_id=r["order_id"], resident=r["resident"], item_key=r["item_key"], item_label=CROPS[r["item_key"]].label, qty=r["qty"], reward=r["reward"],
                shop_value=r["qty"] * CROPS[r["item_key"]].unit_value, fulfilled=r["fulfilled_at"] is not None,
                can_fulfill=r["fulfilled_at"] is None and have.get(r["item_key"], 0) >= r["qty"], expires_at=local_midnight.astimezone(ZoneInfo("UTC")),
            )
            for r in rows
        ]

    def view(self, home: HomeRef, pet_id: str | None = None, now: datetime | None = None) -> MarketView:
        """pet_id：换来的旅费进哪只宠物的账户（钱包显示它的余额）；不给时是这个家的第一只。"""
        now = now or utcnow()
        return MarketView(pantry=self.pantry(home.home_id), wallet=self.economy.wallet(pet_id or home.pet_id), orders=self.orders(home, now),
                          player_listing_enabled=False, player_listing_note=PLAYER_LISTING_NOTE, data_origin=DataOrigin.live)

    # ---- 写入 ----
    def sell(self, home: HomeRef, item_key: str, qty: int, operation_key: str, now: datetime | None = None, pet_id: str | None = None) -> MarketResult:
        now = now or utcnow()
        target = pet_id or home.pet_id
        crop = CROPS.get(item_key)
        if crop is None:
            raise MarketError("unknown_item", "杂货铺不收这个。")
        if not self.inventory.remove(home.user_id, home.home_id, item_key, qty, "卖给杂货铺", f"sell:{home.home_id}:{operation_key}", now, pet_id=target):
            raise MarketError("not_enough", f"仓库里的{crop.label}不够 {qty} 个。")
        coins = qty * crop.unit_value
        wallet, _ = self.economy.apply(target, coins, EconomyTransactionType.web_farm_harvest, f"web:shop:{home.home_id}:{operation_key}",
                                       reason=f"把 {qty} 个{crop.label}卖给杂货铺", source="web.market.sell", now=now)
        return MarketResult(wallet=wallet, pantry=self.pantry(home.home_id), gained_coins=coins, message=f"杂货铺收下了 {qty} 个{crop.label}，+{coins} 旅费。")

    def fulfill(self, home: HomeRef, order_id: str, now: datetime | None = None, pet_id: str | None = None) -> MarketResult:
        now = now or utcnow()
        target = pet_id or home.pet_id
        self._ensure_orders(home, now)
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_resident_orders WHERE order_id = ? AND home_id = ?", (order_id, home.home_id)).fetchone()
        if row is None:
            raise MarketError("not_found", "没有这张订单。")
        local_day = now.astimezone(ORDER_TZ).date().isoformat()
        if row["fulfilled_at"] is None and row["day"] != local_day:
            raise MarketError("expired", "这张订单已经过期了。")
        crop = CROPS[row["item_key"]]
        # 物资扣减与旅费入账都以订单号去重：重复点击/重试不会重复扣或重复给。
        if not self.inventory.remove(home.user_id, home.home_id, row["item_key"], row["qty"], f"交给{row['resident']}的订单", f"order:{order_id}", now,
                                     pet_id=target):
            raise MarketError("not_enough", f"仓库里的{crop.label}不够 {row['qty']} 个。")
        with self.storage.connect() as conn:
            conn.execute("UPDATE web_resident_orders SET fulfilled_at = ? WHERE order_id = ? AND fulfilled_at IS NULL", (iso(now), order_id))
        wallet, _ = self.economy.apply(target, row["reward"], EconomyTransactionType.web_reward, f"web:order:{order_id}",
                                       reason=f"{row['resident']}的订单：{row['qty']} 个{crop.label}", source="web.market.order", now=now)
        return MarketResult(wallet=wallet, pantry=self.pantry(home.home_id), gained_coins=row["reward"],
                            message=f"{row['resident']}收到了 {row['qty']} 个{crop.label}，付了 {row['reward']} 旅费。")
