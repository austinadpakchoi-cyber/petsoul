"""管理端请求体：一律 `extra="forbid"`，长度与取值在这里就卡死。

写操作都带 `reason`（会进审计）；能并发的写操作都带 `expected_version`（提交时复核）。
口令与验证码只出现在请求体里，不进审计、不进日志、不回显（422 处理器已经剥掉 input）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AdminRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AdminLoginRequest(AdminRequest):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    mfa_code: str | None = Field(default=None, max_length=12)


class MfaActivateRequest(AdminRequest):
    code: str = Field(min_length=6, max_length=6)


class ReasonRequest(AdminRequest):
    reason: str = Field(min_length=4, max_length=500)


class AccountFreezeRequest(ReasonRequest):
    frozen: bool
    expected_version: int | None = Field(default=None, ge=0)


class RelayImportRequest(AdminRequest):
    """离线导入中转的逐次回执（临时桥接）；每条的字段在 web_admin/relay_receipts.py 里逐条校验，不合规的整条拒收并写明原因。"""

    records: list[dict[str, Any]] = Field(min_length=1, max_length=5000)
    source_note: str = Field(min_length=4, max_length=500)
    file_name: str | None = Field(default=None, max_length=200)


class ResidentListingRequest(ReasonRequest):
    """撤下（listed=false）/ 放回（listed=true）一位待领养居民；按后台记录的版本做并发检查（还没记录过是 0）。"""

    listed: bool
    expected_version: int | None = Field(default=None, ge=0)


class PetPauseRequest(ReasonRequest):
    """暂停 / 恢复一只宠物的自主运行（写运行表的维护列）；按后台记录的版本做并发检查。"""

    paused: bool
    expected_version: int | None = Field(default=None, ge=0)


class ModerationRequest(ReasonRequest):
    report_id: str | None = Field(default=None, max_length=64)
    target_kind: Literal["post", "comment"]
    target_id: str = Field(min_length=1, max_length=64)
    decision: Literal["takedown", "restore", "dismiss"]


class ReportClaimRequest(AdminRequest):
    target_kind: Literal["post", "comment"]
    target_id: str = Field(min_length=1, max_length=64)


class SwitchRequest(ReasonRequest):
    state: Literal["active", "paused"]
    expected_version: int | None = Field(default=None, ge=0)


class GrantRequest(ReasonRequest):
    pet_id: str = Field(min_length=1, max_length=64)
    amount: int = Field(ge=1, le=200)
    # 玩家在星球银行卡上看到的那句说明（空着就用默认「运营补偿」）；reason 是内部原因，只进审计
    player_note: str | None = Field(default=None, max_length=60)


class BatchPreviewRequest(AdminRequest):
    pet_ids: list[str] = Field(min_length=1, max_length=500)
    amount_per_pet: int = Field(ge=1)
    player_note: str | None = Field(default=None, max_length=60)


class BatchSubmitRequest(ReasonRequest):
    title: str = Field(min_length=1, max_length=80)
    pet_ids: list[str] = Field(min_length=1, max_length=500)
    amount_per_pet: int = Field(ge=1)
    player_note: str | None = Field(default=None, max_length=60)  # 同上：玩家看到的说明，审批人也会看到


class ReversalRequest(ReasonRequest):
    tx_id: str = Field(min_length=1, max_length=64)
    player_note: str | None = Field(default=None, max_length=60)  # 玩家看到的说明；reason 只进审计


class BatchDecisionRequest(AdminRequest):
    approve: bool
    note: str = Field(min_length=4, max_length=500)
    expected_version: int = Field(ge=1)


class BatchExecuteRequest(AdminRequest):
    expected_version: int = Field(ge=1)
    # 执行人自己的说明（可选）。批次的业务原因是提交时写的那一条，不会被它替换。
    note: str | None = Field(default=None, max_length=500)


class AssetRetireRequest(ReasonRequest):
    expected_version: int = Field(ge=1)


class PriceAddRequest(AdminRequest):
    """录一条供应商价格（只追加）。单价用**字符串**传，避免浮点把 0.28 变成 0.27999…；具体格式由服务层校验。"""
    provider: str = Field(min_length=1, max_length=40)
    purpose: str = Field(min_length=1, max_length=40)
    currency: Literal["CNY", "USD"]
    unit_price: str = Field(min_length=1, max_length=20)
    effective_from: datetime
    source_note: str = Field(min_length=1, max_length=300)
    model_note: str | None = Field(default=None, max_length=120)


class ContentDraftRequest(AdminRequest):
    content_type: Literal["announcement", "adventure", "crop", "job", "resident", "destination"]
    slug: str = Field(min_length=2, max_length=49)
    title: str = Field(min_length=1, max_length=120)
    body: dict[str, Any]
    note: str | None = Field(default=None, max_length=200)


class ContentSaveRequest(AdminRequest):
    body: dict[str, Any]
    expected_version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=200)


class ContentPublishRequest(ReasonRequest):
    revision: int = Field(ge=1)
    expected_version: int = Field(ge=1)
    effective_at: datetime | None = None
    expires_at: datetime | None = None


class ContentWithdrawRequest(ReasonRequest):
    expected_version: int = Field(ge=1)


class ContentRollbackRequest(ReasonRequest):
    to_revision: int = Field(ge=1)
    expected_version: int = Field(ge=1)


class StaffCreateRequest(AdminRequest):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=12, max_length=256)
    display_name: str = Field(min_length=1, max_length=40)
    roles: list[str] = Field(min_length=1, max_length=8)


class StaffRolesRequest(AdminRequest):
    roles: list[str] = Field(min_length=1, max_length=8)
    expected_version: int = Field(ge=1)


class StaffStatusRequest(ReasonRequest):
    status: Literal["active", "disabled"]
    expected_version: int = Field(ge=1)
