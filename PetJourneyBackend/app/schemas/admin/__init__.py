"""管理端 DTO（`/api/v1/admin`）。

范围说明（如实写，不含糊）：**请求体**一律是严格模型（`extra="forbid"` + 长度/取值约束），
因为它们是安全面——多一个字段、少一处长度限制都可能变成问题。**响应**由领域服务的
dataclass 直接序列化，路由层组装成对象返回；本批没有为每一个响应再写一份镜像模型。
管理端不进 `docs/contracts/generated` 的玩家契约比对，玩家契约版本不因本包变化。
"""

from .requests import (
    AccountFreezeRequest,
    AdminLoginRequest,
    AssetRetireRequest,
    BatchDecisionRequest,
    BatchExecuteRequest,
    BatchPreviewRequest,
    BatchSubmitRequest,
    ContentDraftRequest,
    ContentPublishRequest,
    ContentRollbackRequest,
    ContentSaveRequest,
    ContentWithdrawRequest,
    GrantRequest,
    MfaActivateRequest,
    ModerationRequest,
    PetPauseRequest,
    PriceAddRequest,
    ReasonRequest,
    RelayImportRequest,
    ReportClaimRequest,
    ResidentListingRequest,
    ReversalRequest,
    StaffCreateRequest,
    StaffRolesRequest,
    StaffStatusRequest,
    SwitchRequest,
)

__all__ = [
    "AccountFreezeRequest",
    "AdminLoginRequest",
    "AssetRetireRequest",
    "BatchDecisionRequest",
    "BatchExecuteRequest",
    "BatchPreviewRequest",
    "BatchSubmitRequest",
    "ContentDraftRequest",
    "ContentPublishRequest",
    "ContentRollbackRequest",
    "ContentSaveRequest",
    "ContentWithdrawRequest",
    "GrantRequest",
    "MfaActivateRequest",
    "ModerationRequest",
    "PetPauseRequest",
    "PriceAddRequest",
    "RelayImportRequest",
    "ReasonRequest",
    "ReportClaimRequest",
    "ResidentListingRequest",
    "ReversalRequest",
    "StaffCreateRequest",
    "StaffRolesRequest",
    "StaffStatusRequest",
    "SwitchRequest",
]
