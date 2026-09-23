"""家庭共同照顾的领域对象：成员角色、动作权限、访问凭据与错误。

- 登录身份仍是各自的 user_id；“当前查看的宠物”只是查看对象，不是权限依据；
- 每个动作都显式落到一只宠物（pet_id）或一个家庭（household_id）上，由服务端检查有效成员关系与角色；
- 关系称呼（妈妈、哥哥……）与权限角色分开，称呼不会带来更高权限。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Role(str, Enum):
    admin = "admin"  # 家庭管理员：日常照顾 + 邀请/移除成员、管理权限与公开设置、给家里添宠物
    caregiver = "caregiver"  # 共同照顾者：查看共同生活、经营家园、陪练、提旅行建议，在授权范围内使用宠物账户


class Action(str, Enum):
    view = "view"  # 查看共同生活（家园、宠物、证件、余额、家庭频道……）
    care = "care"  # 日常照顾：收菜种菜、出售物资、陪练陪考、建议、聊天
    spend = "spend"  # 使用宠物的星球账户（出发旅费等）；共同照顾者受家庭设置约束
    manage = "manage"  # 成员管理、权限、公开设置、给家庭添宠物、改家庭资料


@dataclass(frozen=True)
class Membership:
    household_id: str
    user_id: str
    role: Role
    status: str
    joined_at: datetime


@dataclass(frozen=True)
class HouseholdAccess:
    user_id: str
    household_id: str
    home_id: str
    role: Role
    caregivers_can_spend: bool

    def allows(self, action: Action) -> bool:
        if self.role is Role.admin:
            return True
        if action is Action.manage:
            return False
        if action is Action.spend:
            return self.caregivers_can_spend
        return True


@dataclass(frozen=True)
class PetAccess(HouseholdAccess):
    pet_id: str = ""


@dataclass(eq=False)
class HouseholdError(Exception):
    """reason：机器可读原因；status：HTTP 状态（404 不暴露资源是否存在；403 角色不够；409 需要显式选择或状态冲突）。"""

    reason: str
    message: str
    status: int = 409
    details: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__init__(self.message)
