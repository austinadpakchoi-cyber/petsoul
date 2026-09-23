"""访客（不登录）可看的公开世界（0.4.0）。

只放公开内容：还在星球上生活的待领养居民（它们的生活本来就公开）、公开的宠物主页与公开动态。
不含任何家庭成员、私聊、叮嘱、钱包、家的位置或非公开的内容；读取不推进世界、不调用模型或生图。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from .common import DataOrigin, WebModel
from .pets import PetOrigin, PetPresence, PetPublicProfile, PetSpecies
from .social import Post


class EntryRoute(str, Enum):
    browse = "browse"  # 先逛逛（不登录）
    own_pet = "own_pet"  # 带我的宠物来
    adopt = "adopt"  # 认识一位新伙伴
    invite = "invite"  # 家人发来的邀请


class PublicEntry(WebModel):
    route: EntryRoute
    label: str
    needs_login: bool
    note: str | None = None


class PublicResident(WebModel):
    """一位还在星球上生活、可以领养的居民。住处是星球居民驿站（世界规则提供食宿，不是某位真实用户的家）。"""

    pet_id: str
    candidate_id: str
    name: str
    species: PetSpecies
    personality: str
    dream: str
    origin: PetOrigin
    source_note: str | None = Field(default=None, description="来源说明；未知为 null，不编造")
    residence: str = Field(description="住在哪个驿站，例如“星球居民驿站·中环”")
    city: str
    living_since: datetime
    presence: PetPresence = Field(description="此刻在哪（按已发生的行程推算，访客读取不会推进世界）")
    doing: str = Field(description="此刻在做什么，例如“在驿站休息”“在去码头的路上”")
    place_name: str | None = Field(default=None, description="正在到访的真实地点名（来自地图供应商的公开地点）；在驿站或路上时为空")
    recent_posts: list[Post] = Field(default_factory=list, description="最近的公开动态（最多 3 条）")


class PublicPetView(WebModel):
    profile: PetPublicProfile
    resident: PublicResident | None = Field(default=None, description="仍在驿站生活、可以领养时才有")
    adoptable: bool = False
    posts: list[Post] = Field(default_factory=list)


class PublicWorld(WebModel):
    server_time: datetime
    entries: list[PublicEntry]
    residents: list[PublicResident]
    recent_posts: list[Post] = Field(default_factory=list, description="全星球最近的公开动态")
    living_residents: int
    cache_seconds: int = Field(description="这份内容最多缓存多久（访客页刷新不会每次都重算）")
    data_origin: DataOrigin


__all__ = ["EntryRoute", "PublicEntry", "PublicResident", "PublicPetView", "PublicWorld"]
