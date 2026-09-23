"""共同的家的数据对象：家（按家庭）与“某位成员此刻要照顾的一只宠物和它的家”。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..web_household import PetAccess


@dataclass(frozen=True)
class HomeRow:
    home_id: str
    household_id: str | None
    user_id: str  # 建立这个家的成员（旧字段，只作记录，不是权限依据）
    pet_id: str  # 第一只宠物（旧字段）
    activated_at: datetime | None
    public_posts: bool
    version: int


@dataclass(frozen=True)
class PetHome:
    """某位成员此刻要照顾的一只宠物，以及它所在家庭的家。路由里用 pet_id / home_id；权限在 access。"""

    access: PetAccess
    home: HomeRow

    @property
    def user_id(self) -> str:
        return self.access.user_id

    @property
    def pet_id(self) -> str:
        return self.access.pet_id

    @property
    def household_id(self) -> str:
        return self.access.household_id

    @property
    def home_id(self) -> str:
        return self.home.home_id

    @property
    def activated_at(self) -> datetime | None:
        return self.home.activated_at

    @property
    def public_posts(self) -> bool:
        return self.home.public_posts
