from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class PetJourneyBaseModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class PetType(str, Enum):
    dog = "dog"
    cat = "cat"
    parrot = "parrot"
    rabbit = "rabbit"
    hamster = "hamster"
    bird = "bird"
    other = "other"


class JourneyStatus(str, Enum):
    traveling = "traveling"
    flying = "flying"
    resting = "resting"
    staying = "staying"
    walking = "walking"


class TravelMode(str, Enum):
    stay = "stay"
    walk = "walk"
    drive = "drive"
    transit = "transit"
    train = "train"
    flight = "flight"
    ferry = "ferry"
    check_in = "check_in"


class TransportLegStatus(str, Enum):
    scheduled = "scheduled"
    waiting = "waiting"
    boarding = "boarding"
    in_transit = "in_transit"
    arrived = "arrived"
    delayed = "delayed"
    cancelled = "cancelled"


class TradePolicy(str, Enum):
    tradable = "tradable"
    soulbound = "soulbound"
    time_locked = "time_locked"
    quest_locked = "quest_locked"
    system_locked = "system_locked"
    dev_only = "dev_only"


class ItemStatus(str, Enum):
    owned = "owned"
    equipped = "equipped"
    stored = "stored"
    listed = "listed"
    sold = "sold"
    consumed = "consumed"
    archived = "archived"
    deleted = "deleted"


class AcquisitionSource(str, Enum):
    found = "found"
    shop_purchase = "shop_purchase"
    npc_gift = "npc_gift"
    quest_reward = "quest_reward"
    photo_mission = "photo_mission"
    event_reward = "event_reward"
    activity_reward = "activity_reward"
    dev_grant = "dev_grant"


class EconomyTransactionType(str, Enum):
    item_acquired = "item_acquired"
    item_sold = "item_sold"
    owner_fund_granted = "owner_fund_granted"
    fund_to_coin_converted = "fund_to_coin_converted"
    item_locked = "item_locked"
    item_unlocked = "item_unlocked"
    item_archived = "item_archived"


__all__ = [
    "PetJourneyBaseModel",
    "PetType",
    "JourneyStatus",
    "TravelMode",
    "TransportLegStatus",
    "TradePolicy",
    "ItemStatus",
    "AcquisitionSource",
    "EconomyTransactionType",
]
