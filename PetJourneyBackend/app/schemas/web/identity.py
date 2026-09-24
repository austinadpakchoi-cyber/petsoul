"""会话 / 身份 / 入住阶段契约。凭据哈希、原始口令永不出现在任何响应。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from .common import AuthMethod, WebModel
from .household import EntryIntentRequest, EntryIntentView, HouseholdBrief
from .pets import PetOrigin


class OnboardingStep(str, Enum):
    """注册/归属 → 可选接待与叮嘱确认 → 入住/生活激活。"""

    needs_companion = "needs_companion"
    reception_optional = "reception_optional"
    ready_to_move_in = "ready_to_move_in"
    active = "active"


class OnboardingState(WebModel):
    step: OnboardingStep
    pet_id: str | None = None
    home_id: str | None = None
    reception_session_id: str | None = None
    reception_skipped: bool = False
    home_activated_at: datetime | None = None
    pet_origin: PetOrigin | None = Field(default=None, description="伙伴来源；接待据此选择“自己的宠物/领养”分支")
    households: list[HouseholdBrief] = Field(default_factory=list, description="你所在的家庭与各家的宠物（0.4.0：一个账号可以在多个家庭里照顾多只宠物）",
                                             json_schema_extra={"x-additive": True})
    entry: EntryIntentView | None = Field(default=None, description="注册时带来的入口（选中的伙伴 / 家庭邀请），等你确认；不会自动领养或加入",
                                          json_schema_extra={"x-additive": True})


class SessionUser(WebModel):
    user_id: str
    display_name: str | None = None
    username: str | None = None
    auth_method: AuthMethod


class SessionState(WebModel):
    authenticated: bool
    user: SessionUser | None = None
    csrf_required: bool = False
    expires_at: datetime | None = None
    onboarding: OnboardingState | None = None


class RegisterRequest(WebModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_\.\-]+$")
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=40)
    entry: EntryIntentRequest | None = Field(default=None, description="从哪个入口来注册（0.4.0）", json_schema_extra={"x-additive": True})


class LoginRequest(WebModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class MoveInRequest(WebModel):
    """入住激活。public_posts：是否允许 TA 的旅行到访生成公开动态（默认不公开，由主人明确选择）。"""

    public_posts: bool = False
    habitat: str | None = Field(default=None, pattern="^(seaside|grassland|desert|forest|lakeside|mountain|city|countryside)$",
                                description="希望这个家在哪一类地方（只在家第一次入住时生效）；只能选当前开放的类型（见 /home/place）", json_schema_extra={"x-additive": True})
    pet_id: str | None = Field(default=None, description="住进来的是哪一只宠物（0.4.0；只照顾一只时可以省略）", json_schema_extra={"x-additive": True})


class SettingsView(WebModel):
    username: str | None = None
    display_name: str | None = None
    public_posts: bool
    profile_visibility: str
    bio: str | None = None
    intent_layer_mode: str
    model_replies: bool = Field(default=False, description="主人开启后，TA 的私信回复由对话模型按已确认的叮嘱撰写；默认关闭", json_schema_extra={"x-additive": True})
    model_replies_available: bool = Field(default=False, json_schema_extra={"x-additive": True})
    model_provider: str | None = Field(default=None, description="对话模型服务商（披露用），未配置为空", json_schema_extra={"x-additive": True})
    generated_photos: bool = Field(default=False, description="主人开启后，冒险事件会请生图服务画一张插画；默认关闭", json_schema_extra={"x-additive": True})
    generated_photos_available: bool = Field(default=False, json_schema_extra={"x-additive": True})
    image_provider: str | None = Field(default=None, json_schema_extra={"x-additive": True})
    pet_messages: bool = Field(default=True, description="是否接收 TA 主动发来的消息（早安、分享、晚安等；每天最多 4 条，夜间不打扰）", json_schema_extra={"x-additive": True})
    timezone: str = Field(default="Asia/Hong_Kong", description="主人所在时区（IANA 名称），安静时段按它计算", json_schema_extra={"x-additive": True})


class SettingsUpdate(WebModel):
    model_replies: bool | None = None
    generated_photos: bool | None = None
    pet_messages: bool | None = None
    timezone: str | None = Field(default=None, max_length=64, description="IANA 时区名，例如 Asia/Hong_Kong；前端可取浏览器时区")
    public_posts: bool | None = None
    profile_visibility: str | None = Field(default=None, pattern="^(public|followers|private)$")
    bio: str | None = Field(default=None, max_length=120)


__all__ = [
    "OnboardingStep",
    "OnboardingState",
    "SessionUser",
    "SessionState",
    "RegisterRequest",
    "LoginRequest",
    "MoveInRequest",
    "SettingsView",
    "SettingsUpdate",
]
