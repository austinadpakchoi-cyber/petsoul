"""家庭服务：成员关系与动作权限的唯一裁定点，外加建家庭、添宠物、邀请、角色、移除与关系称呼。

所有宠物/家园接口都经这里把“谁（user_id）对哪只宠物（pet_id）/ 哪个家庭做什么动作”落到有效成员关系上：
- 不是成员 → 404（不暴露资源是否存在）；角色不够 → 403；没有指明宠物而又不止一只 → 409 pet_required；
- 被移除或退出的成员，下一次请求就失去私有接口访问权（每次请求都查成员关系，不缓存在会话里）；
- 邀请令牌只保存 HMAC 摘要；接受在一个事务里完成，并发/重放不会重复建立成员关系；
- 家庭至少保留一位管理员：最后一位管理员不能退出、降级或被移除，要先把管理员交给别人。
"""

from __future__ import annotations

from ..storage import JourneyStorage
from .access import HouseholdAccessMixin, _not_found
from .invites import INVITE_TTL, MAX_INVITE_TTL, HouseholdInvitesMixin
from .members import HouseholdMembersMixin

__all__ = ["HouseholdService", "INVITE_TTL", "MAX_INVITE_TTL", "_not_found"]


class HouseholdService(HouseholdAccessMixin, HouseholdMembersMixin, HouseholdInvitesMixin):
    """成员关系与动作权限的唯一裁定点（查询与裁定见 access.py，建家与成员见 members.py，邀请见 invites.py）。"""

    def __init__(self, storage: JourneyStorage, secret: str) -> None:
        self.storage = storage
        self._secret = (secret or "petsoul-dev-household").encode("utf-8")
