from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import Field

from .base import (
    AcquisitionSource,
    EconomyTransactionType,
    ItemStatus,
    PetJourneyBaseModel,
    TradePolicy,
)


class CurrencyAmounts(PetJourneyBaseModel):
    travel_coin: int = 0
    star_dust: int = 0
    merit: int = 0


class Wallet(PetJourneyBaseModel):
    pet_id: str
    travel_coin: int = 0
    star_dust: int = 0
    merit: int = 0
    updated_at: datetime


class OwnerFund(PetJourneyBaseModel):
    pet_id: str
    star_dust: int = 0
    project_budget: int = 0
    cosmetic_budget: int = 0
    travel_opportunity_budget: int = 0
    daily_coin_limit: int = 300
    coin_inflow_today: int = 0
    coin_inflow_date: date
    updated_at: datetime


class EconomySnapshot(PetJourneyBaseModel):
    pet_id: str
    total_display_value: int = 0
    sellable_value: int = 0
    collection_value: int = 0
    honor_value: int = 0
    owned_item_count: int = 0
    sellable_item_count: int = 0
    archived_item_count: int = 0
    sold_item_count: int = 0
    updated_at: datetime


class EconomyTransaction(PetJourneyBaseModel):
    tx_id: str
    pet_id: str
    type: EconomyTransactionType
    idempotency_key: str
    amounts: CurrencyAmounts = Field(default_factory=CurrencyAmounts)
    item_ids: list[str] = Field(default_factory=list)
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    reason: str
    operator: str = "system"
    source: str
    status: str = "committed"
    created_at: datetime


class ItemValue(PetJourneyBaseModel):
    market_value: int = 0
    emotional_value: int = 0
    honor_value: int = 0
    value_breakdown: dict[str, Any] = Field(default_factory=dict)


class EconomyResponse(PetJourneyBaseModel):
    wallet: Wallet
    owner_fund: OwnerFund
    snapshot: EconomySnapshot
    recent_transactions: list[EconomyTransaction] = Field(default_factory=list)


class SellItemRequest(PetJourneyBaseModel):
    client_request_id: str = Field(min_length=1, max_length=120)
    expected_item_version: int = Field(ge=1)


class ArchiveItemRequest(PetJourneyBaseModel):
    client_request_id: str = Field(min_length=1, max_length=120)
    expected_item_version: int = Field(ge=1)


class OwnerFundGrantRequest(PetJourneyBaseModel):
    grant_id: str = Field(min_length=1, max_length=120)
    star_dust: int = Field(default=0, ge=0)
    project_budget: int = Field(default=0, ge=0)
    cosmetic_budget: int = Field(default=0, ge=0)
    travel_opportunity_budget: int = Field(default=0, ge=0)
    reason: str = Field(default="开发环境主人基金入账", max_length=240)


class SouvenirItemType(str, Enum):
    toy = "toy"
    cultural_creative = "cultural_creative"
    ticket_stub = "ticket_stub"
    charm = "charm"
    snack_pack = "snack_pack"
    photo_print = "photo_print"
    found_object = "found_object"


class SouvenirItem(PetJourneyBaseModel):
    id: str
    pet_id: str
    quest_id: str | None = None
    template_id: str | None = None
    item_type: SouvenirItemType
    title: str
    subtitle: str
    city: str
    place_name: str
    story: str
    pet_voice: str
    image_prompt: str
    image_url: str | None = None
    rarity: str = "common"
    obtained_at: datetime
    source: str
    memory_type: str = "souvenir"
    source_photo_mission_id: str | None = None
    bag_influence_tags: list[str] = Field(default_factory=list)
    status: ItemStatus = ItemStatus.owned
    version: int = 1
    trade_policy: TradePolicy = TradePolicy.tradable
    lock_until: datetime | None = None
    market_value: int = 0
    emotional_value: int = 0
    honor_value: int = 0
    value_breakdown: dict[str, Any] = Field(default_factory=dict)
    acquire_source: AcquisitionSource = AcquisitionSource.quest_reward
    origin_event_id: str | None = None
    origin_activity_id: str | None = None
    origin_activity_type: str | None = None
    origin_poi_name: str | None = None
    origin_city: str | None = None
    origin_weather: str | None = None
    origin_coords: list[float] = Field(default_factory=list)
    updated_at: datetime | None = None


class CollectSouvenirsResponse(PetJourneyBaseModel):
    items: list[SouvenirItem]
    transactions: list[EconomyTransaction]
    wallet: Wallet
    snapshot: EconomySnapshot


class InventoryResponse(PetJourneyBaseModel):
    items: list[SouvenirItem]
    snapshot: EconomySnapshot


class ItemMutationResponse(PetJourneyBaseModel):
    success: bool
    transaction: EconomyTransaction
    wallet: Wallet
    item: SouvenirItem
    snapshot: EconomySnapshot


__all__ = [
    "CurrencyAmounts",
    "Wallet",
    "OwnerFund",
    "EconomySnapshot",
    "EconomyTransaction",
    "ItemValue",
    "EconomyResponse",
    "SellItemRequest",
    "ArchiveItemRequest",
    "OwnerFundGrantRequest",
    "SouvenirItemType",
    "SouvenirItem",
    "CollectSouvenirsResponse",
    "InventoryResponse",
    "ItemMutationResponse",
]
