"""网页契约 v0.1 公共底层：错误信封、能力开关、数据来源与分页。

只 import pydantic / 标准库（schemas 层规则）。旧 iOS 模型不在此处，
`app/schemas/__init__.py` 也不 re-export 本包，避免进入 iOS 契约比对。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

WEB_API_PREFIX = "/api/v1/web"
WEB_CONTRACT_VERSION = "0.4.5"


class WebModel(BaseModel):
    """所有网页 DTO 的基类：拒绝未知字段，防止各模块私自塞字段。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class DataOrigin(str, Enum):
    """响应数据的来源；fixture 只在显式 fixture 模式出现，live 不静默混入 fixture。"""

    fixture = "fixture"
    live = "live"


class WebErrorCode(str, Enum):
    auth_required = "AUTH_REQUIRED"
    session_expired = "SESSION_EXPIRED"
    csrf_failed = "CSRF_FAILED"
    forbidden = "FORBIDDEN"
    not_found = "NOT_FOUND"
    validation_failed = "VALIDATION_FAILED"
    conflict = "CONFLICT"
    version_conflict = "VERSION_CONFLICT"
    idempotency_key_required = "IDEMPOTENCY_KEY_REQUIRED"
    idempotency_key_reused = "IDEMPOTENCY_KEY_REUSED"
    idempotency_in_progress = "IDEMPOTENCY_IN_PROGRESS"
    capability_unavailable = "CAPABILITY_UNAVAILABLE"
    not_configured = "NOT_CONFIGURED"
    rate_limited = "RATE_LIMITED"
    upstream_unavailable = "UPSTREAM_UNAVAILABLE"
    internal_error = "INTERNAL_ERROR"
    # 领域错误（稳定 code，前端按 code 处理，不解析 message）
    username_taken = "USERNAME_TAKEN"
    invalid_credentials = "INVALID_CREDENTIALS"
    adoption_taken = "ADOPTION_TAKEN"
    pet_not_activated = "PET_NOT_ACTIVATED"
    driving_blocks_video = "DRIVING_BLOCKS_VIDEO"
    control_lease_held = "CONTROL_LEASE_HELD"
    itinerary_changed = "ITINERARY_CHANGED"
    draft_expired = "DRAFT_EXPIRED"
    insufficient_funds = "INSUFFICIENT_FUNDS"
    already_traveling = "ALREADY_TRAVELING"
    farm_guarded = "FARM_GUARDED"
    already_has_companion = "ALREADY_HAS_COMPANION"
    media_rejected = "MEDIA_REJECTED"


class WebError(WebModel):
    code: WebErrorCode
    message: str = Field(description="可读说明；不含堆栈、SQL 或密钥")
    request_id: str
    retryable: bool = False
    details: dict[str, Any] | None = None


class WebErrorEnvelope(WebModel):
    error: WebError


class CapabilityStatus(str, Enum):
    available = "available"
    not_implemented = "not_implemented"
    not_configured = "not_configured"
    disabled = "disabled"


class Capability(WebModel):
    key: str = Field(description="稳定能力键，例如 food.recommendations")
    status: CapabilityStatus
    module: str
    note: str | None = None


class AuthMethod(str, Enum):
    web_password = "web_password"
    apple_bearer = "apple_bearer"


class WebMeta(WebModel):
    api_prefix: str = WEB_API_PREFIX
    contract_version: str = WEB_CONTRACT_VERSION
    server_time: datetime
    backend_version: str
    data_origin: DataOrigin = DataOrigin.live
    auth_methods_available: list[AuthMethod] = Field(default_factory=list)
    capabilities: list[Capability] = Field(default_factory=list)
    applied_migrations: list[str] = Field(default_factory=list)


class MoneyAmount(WebModel):
    """整数金额；currency 区分游戏币 travel_coin 与现实币种（HKD/CNY 等），两者不混算。"""

    amount_minor: int
    currency: str


class LatLng(WebModel):
    lat: float
    lng: float


class CoordSystem(str, Enum):
    wgs84 = "wgs84"
    gcj02 = "gcj02"


__all__ = [
    "WEB_API_PREFIX",
    "WEB_CONTRACT_VERSION",
    "WebModel",
    "DataOrigin",
    "WebErrorCode",
    "WebError",
    "WebErrorEnvelope",
    "CapabilityStatus",
    "Capability",
    "AuthMethod",
    "WebMeta",
    "MoneyAmount",
    "LatLng",
    "CoordSystem",
]
