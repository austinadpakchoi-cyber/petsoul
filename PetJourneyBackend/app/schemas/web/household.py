"""家庭共同照顾契约（0.4.0）：家庭、成员与权限角色、邀请、每只宠物的入住进度、成员与宠物之间的称呼，以及注册入口。

- 一只宠物只归属一个家庭；一个家庭可以有多位成员与多只宠物，共用一个家；
- 登录身份是各自的 user_id；所有宠物操作都要显式给出 pet_id（只照顾一只宠物时可以省略）；
- 称呼（妈妈、哥哥……）只是称呼，权限只看角色：admin（家庭管理员）/ caregiver（共同照顾者）。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from .common import WebModel
from .pets import PetOrigin, PetPresence, PetSpecies


class HouseholdRole(str, Enum):
    admin = "admin"
    caregiver = "caregiver"


class InviteStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    revoked = "revoked"
    expired = "expired"


class PetJoinStep(str, Enum):
    """一只宠物在这个家里的进度：可选接待 → 可以入住 → 已经住进来。"""

    reception_optional = "reception_optional"
    ready_to_move_in = "ready_to_move_in"
    moved_in = "moved_in"


class HouseholdPetBrief(WebModel):
    pet_id: str
    name: str
    species: PetSpecies
    photo_url: str | None = None
    origin: PetOrigin
    presence: PetPresence
    join_step: PetJoinStep
    joined_at: datetime
    added_by_you: bool = False


class HouseholdBrief(WebModel):
    household_id: str
    name: str | None = None
    home_id: str
    role: HouseholdRole = Field(description="你在这个家庭里的角色")
    home_activated: bool
    member_count: int
    pets: list[HouseholdPetBrief] = Field(default_factory=list)


class HouseholdMember(WebModel):
    user_id: str
    display_name: str
    role: HouseholdRole
    joined_at: datetime
    is_you: bool = False


class HouseholdSettings(WebModel):
    name: str | None = None
    caregivers_can_spend: bool = Field(description="共同照顾者能否使用宠物的星球账户（出发旅费等）")
    generated_photos: bool = Field(description="宠物自己的旅途照片是否生成写实照片（付费生图，由家庭管理员决定）")
    pet_messages: bool = Field(description="宠物是否主动把生活里发生的事发到家庭频道")
    public_posts: bool = Field(description="宠物的旅行到访是否生成公开动态")


class HouseholdDetail(WebModel):
    household: HouseholdBrief
    members: list[HouseholdMember]
    settings: HouseholdSettings
    your_permissions: list[str] = Field(description="view / care / spend / manage")
    version: int


class HouseholdSettingsRequest(WebModel):
    name: str | None = Field(default=None, max_length=24)
    caregivers_can_spend: bool | None = None
    generated_photos: bool | None = None
    pet_messages: bool | None = None
    public_posts: bool | None = None


class MemberRoleRequest(WebModel):
    role: HouseholdRole


class HouseholdInvite(WebModel):
    invite_id: str
    household_id: str
    role: HouseholdRole
    relation_hint: str | None = Field(default=None, description="邀请人写的称呼提示，例如“妈妈”；只是称呼，不带权限")
    status: InviteStatus
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None = None


class InviteCreateRequest(WebModel):
    role: HouseholdRole = HouseholdRole.caregiver
    relation_hint: str | None = Field(default=None, max_length=12)
    ttl_hours: int = Field(default=72, ge=1, le=336)


class InviteCreated(WebModel):
    invite: HouseholdInvite
    token: str = Field(description="邀请令牌：只在创建时返回一次，服务端只保存摘要")
    join_path: str = Field(description="前端的邀请直达路径，例如 /join?invite=<令牌>")


class InviteTokenRequest(WebModel):
    token: str = Field(min_length=16, max_length=128)


class InvitePreview(WebModel):
    """接受邀请前能看到的最少信息：家庭名、邀请人称呼、角色、宠物名字。不含私人资料。"""

    invite_id: str
    status: InviteStatus
    role: HouseholdRole
    relation_hint: str | None = None
    expires_at: datetime
    household_name: str | None = None
    inviter_name: str
    pet_names: list[str] = Field(default_factory=list)
    already_member: bool = False


class PetRelationship(WebModel):
    pet_id: str
    owner_title: str | None = Field(default=None, description="TA 怎么称呼你（只属于你和 TA 之间）")
    relation_label: str | None = Field(default=None, description="你和 TA 的关系称呼；不影响权限")
    updated_at: datetime | None = None


class PetRelationshipRequest(WebModel):
    owner_title: str | None = Field(default=None, max_length=12)
    relation_label: str | None = Field(default=None, max_length=12)


class EntryKind(str, Enum):
    browse = "browse"
    own_pet = "own_pet"
    adopt = "adopt"
    invite = "invite"


class EntryIntentRequest(WebModel):
    """注册时带上的入口：先逛逛 / 接我的宠物入住 / 认识新伙伴（注册前选中的伙伴）/ 家庭邀请直达。只记下来，登录后由用户确认。"""

    kind: EntryKind
    pet_id: str | None = Field(default=None, description="kind=adopt：注册前在访客页选中的待领养伙伴")
    invite_token: str | None = Field(default=None, min_length=16, max_length=128, description="kind=invite：邀请令牌（只用来找到邀请，不保存原文）")


class PendingAdoption(WebModel):
    pet_id: str
    name: str
    species: PetSpecies
    available: bool = Field(description="重新校验后的可领养状态；已被别的家庭领养时为 false")


class EntryIntentView(WebModel):
    kind: EntryKind
    pending_adoption: PendingAdoption | None = None
    pending_invite: InvitePreview | None = None
    created_at: datetime


class AddPetRequest(WebModel):
    """给已有家庭添一只宠物（家庭管理员）。上传用 multipart 的 /pets（带 household_id 查询参数），领养用 /adoption/adopt。"""

    household_id: str


__all__ = [
    "HouseholdRole",
    "InviteStatus",
    "PetJoinStep",
    "HouseholdPetBrief",
    "HouseholdBrief",
    "HouseholdMember",
    "HouseholdSettings",
    "HouseholdDetail",
    "HouseholdSettingsRequest",
    "MemberRoleRequest",
    "HouseholdInvite",
    "InviteCreateRequest",
    "InviteCreated",
    "InviteTokenRequest",
    "InvitePreview",
    "PetRelationship",
    "PetRelationshipRequest",
    "EntryKind",
    "EntryIntentRequest",
    "PendingAdoption",
    "EntryIntentView",
    "AddPetRequest",
]
