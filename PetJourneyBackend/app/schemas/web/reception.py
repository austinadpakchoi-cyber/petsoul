"""注册接待 / 入住叮嘱 / 受控记忆契约。

私有会话 → 原文有依据的候选 → 主人逐项确认内容与用途 → 有版本的 CareNote/MemoryGrant。
- IntakeCandidate 不含任何“已授权”字段：抽取器/模型无法自行提升权限。
- MemoryProjection 在检索/摘要/生成前由 MemoryPolicy 过滤（归属、已确认、未撤回、版本、用途）。
- 保存成功（persisted）才可以说“记好了”；应用到体验另有状态。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from .common import DataOrigin, WebModel
from .identity import OnboardingState


class ReceptionBranch(str, Enum):
    own_pet = "own_pet"
    adopted = "adopted"


class ReceptionMode(str, Enum):
    """guided_notes：模型不可用时的明确引导便笺；model_conversation：已接模型的自由对话。"""

    guided_notes = "guided_notes"
    model_conversation = "model_conversation"


class ReceptionStatus(str, Enum):
    active = "active"
    awaiting_confirmation = "awaiting_confirmation"
    skipped = "skipped"
    completed = "completed"
    expired = "expired"


class ReceptionHost(WebModel):
    """可配置的公共 NPC 接待角色；不是平台管理员，也不占专属领养池。"""

    host_id: str
    display_name: str
    role_label: str
    avatar_url: str | None = None
    is_ai: bool = True
    disclosure: str


class TurnSpeaker(str, Enum):
    host = "host"
    owner = "owner"


class ReceptionTurn(WebModel):
    turn_id: str
    seq: int
    speaker: TurnSpeaker
    text: str
    created_at: datetime
    composed_by: str | None = Field(default=None, description="接待员这句话的来源：guided（固定引导）/ model（对话模型）；主人的话为空", json_schema_extra={"x-additive": True})


class CandidateKind(str, Enum):
    habit = "habit"
    shared_story = "shared_story"
    wish = "wish"
    letter = "letter"
    owner_private = "owner_private"
    inference = "inference"


class CandidateSubject(str, Enum):
    pet = "pet"
    owner = "owner"
    relationship = "relationship"


class CandidateState(str, Enum):
    unconfirmed = "unconfirmed"
    edited = "edited"
    confirmed = "confirmed"
    discarded = "discarded"


class CareNoteSlot(str, Enum):
    """叮嘱落到哪个可兑现的体验槽位；由主人确认，模型只能建议。"""

    owner_title = "owner_title"
    favorite_object = "favorite_object"
    interaction_boundary = "interaction_boundary"
    travel_mood = "travel_mood"
    wish_place = "wish_place"
    other = "other"


class IntakeCandidate(WebModel):
    candidate_id: str
    kind: CandidateKind
    subject: CandidateSubject
    text: str
    source_turn_id: str
    source_excerpt: str = Field(description="原话依据片段，主人可展开核对")
    needs_clarification: bool = False
    suggested_slot: CareNoteSlot | None = None
    suggested_slot_value: str | None = None
    state: CandidateState


class ReceptionSession(WebModel):
    session_id: str
    pet_id: str
    branch: ReceptionBranch
    mode: ReceptionMode
    status: ReceptionStatus
    host: ReceptionHost
    turns: list[ReceptionTurn] = Field(default_factory=list)
    candidates: list[IntakeCandidate] = Field(default_factory=list)
    draft_revision: int
    draft_expires_at: datetime | None = None
    data_origin: DataOrigin


class ReceptionStartRequest(WebModel):
    """需 Idempotency-Key；同一宠物已有进行中的会话时返回该会话（继续草稿）。"""

    pet_id: str
    branch: ReceptionBranch
    use_model: bool = Field(default=False, description="主人选择让接待员用对话模型回应（会把本次接待中主人写的话发送给模型服务商）；不可用时退回引导便笺", json_schema_extra={"x-additive": True})


class ReceptionTurnRequest(WebModel):
    """需 Idempotency-Key；expected_revision 过期返回 409 VERSION_CONFLICT。"""

    text: str = Field(min_length=1, max_length=2000)
    expected_revision: int


class SaveTarget(str, Enum):
    """交给 TA / 只留在这里 / 不保存。"""

    give_to_pet = "give_to_pet"
    keep_here = "keep_here"
    do_not_save = "do_not_save"


class MemoryPurpose(str, Enum):
    private_chat = "private_chat"
    home_interaction = "home_interaction"
    travel_preference = "travel_preference"
    food_preference_pet = "food_preference_pet"
    public_story = "public_story"
    media_generation = "media_generation"


class CareNoteDecision(WebModel):
    candidate_id: str
    text: str = Field(min_length=1, max_length=500, description="主人编辑后的最终文字")
    target: SaveTarget
    purposes: list[MemoryPurpose] = Field(default_factory=list)
    slot: CareNoteSlot | None = None
    slot_value: str | None = Field(default=None, max_length=40)


class IntakeConfirmationRequest(WebModel):
    """需 Idempotency-Key；draft_revision 与服务端不一致返回 409 VERSION_CONFLICT。"""

    session_id: str
    draft_revision: int
    decisions: list[CareNoteDecision]


class CareNote(WebModel):
    note_id: str
    pet_id: str
    kind: CandidateKind
    subject: CandidateSubject
    text: str
    target: SaveTarget
    purposes: list[MemoryPurpose] = Field(default_factory=list)
    slot: CareNoteSlot | None = None
    slot_value: str | None = None
    version: int
    confirmed_at: datetime
    supersedes_note_id: str | None = None
    revoked_at: datetime | None = None


class MemoryGrant(WebModel):
    grant_id: str
    note_id: str
    note_version: int
    purpose: MemoryPurpose
    granted_at: datetime
    revoked_at: datetime | None = None


class PersistState(str, Enum):
    persisted = "persisted"
    failed = "failed"


class IntakeConfirmationResult(WebModel):
    confirmation_id: str
    session_id: str
    draft_revision: int
    persist_state: PersistState
    notes: list[CareNote] = Field(default_factory=list)
    grants: list[MemoryGrant] = Field(default_factory=list)
    onboarding: OnboardingState
    data_origin: DataOrigin


class ProjectedNote(WebModel):
    note_id: str
    note_version: int
    kind: CandidateKind
    text: str
    slot: CareNoteSlot | None = None
    slot_value: str | None = None


class MemoryProjection(WebModel):
    """按用途的最小投影；只读消费不扩大许可。"""

    pet_id: str
    purpose: MemoryPurpose
    items: list[ProjectedNote] = Field(default_factory=list)
    policy_version: str
    generated_at: datetime


class MemoryCorrectionAction(str, Enum):
    correct = "correct"
    revoke = "revoke"
    erase = "erase"


class MemoryCorrectionRequest(WebModel):
    """需 Idempotency-Key。先停止使用旧版本，再清理衍生物。"""

    action: MemoryCorrectionAction
    expected_version: int
    new_text: str | None = Field(default=None, max_length=500)
    new_slot_value: str | None = Field(default=None, max_length=40, description="槽位值（如称呼）；不填则按新文字重新建议，无法确定时清空而不沿用旧值")


class CleanupState(str, Enum):
    usage_stopped = "usage_stopped"
    cleanup_pending = "cleanup_pending"
    cleanup_done = "cleanup_done"


class MemoryCorrectionResult(WebModel):
    note_id: str
    new_note: CareNote | None = None
    cleanup: CleanupState
    affected_task_ids: list[str] = Field(default_factory=list)


__all__ = [
    "ReceptionBranch",
    "ReceptionMode",
    "ReceptionStatus",
    "ReceptionHost",
    "TurnSpeaker",
    "ReceptionTurn",
    "CandidateKind",
    "CandidateSubject",
    "CandidateState",
    "CareNoteSlot",
    "IntakeCandidate",
    "ReceptionSession",
    "ReceptionStartRequest",
    "ReceptionTurnRequest",
    "SaveTarget",
    "MemoryPurpose",
    "CareNoteDecision",
    "IntakeConfirmationRequest",
    "CareNote",
    "MemoryGrant",
    "PersistState",
    "IntakeConfirmationResult",
    "ProjectedNote",
    "MemoryProjection",
    "MemoryCorrectionAction",
    "MemoryCorrectionRequest",
    "CleanupState",
    "MemoryCorrectionResult",
]
