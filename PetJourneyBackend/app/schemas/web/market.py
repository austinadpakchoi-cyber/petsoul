"""集市：杂货铺收购（NPC 固定价）与居民订单。玩家之间的挂牌交易未开放（不把 NPC 商店称为玩家市场）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .common import DataOrigin, WebModel
from .home import InventoryItem, WalletSummary


class ResidentOrder(WebModel):
    """星球居民（公共 NPC，不是真实玩家）当天的收购订单；比杂货铺出价高，每单只能交一次。"""

    order_id: str
    resident: str
    item_key: str
    item_label: str
    qty: int
    reward: int
    shop_value: int = Field(description="同样数量卖给杂货铺能得到的旅费，方便对比")
    fulfilled: bool
    can_fulfill: bool
    expires_at: datetime


class MarketView(WebModel):
    pantry: list[InventoryItem] = Field(default_factory=list)
    wallet: WalletSummary
    orders: list[ResidentOrder] = Field(default_factory=list)
    player_listing_enabled: bool = False
    player_listing_note: str
    data_origin: DataOrigin


class SellRequest(WebModel):
    """需 Idempotency-Key。"""

    item_key: str
    qty: int = Field(ge=1, le=99)


class MarketResult(WebModel):
    wallet: WalletSummary
    pantry: list[InventoryItem] = Field(default_factory=list)
    gained_coins: int
    message: str


__all__ = ["ResidentOrder", "MarketView", "SellRequest", "MarketResult"]
