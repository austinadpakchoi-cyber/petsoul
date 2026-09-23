"""Reception 服务边界（R0 只定义接口；实现由用户分配的接待模块窗口完成）。

实现要求（验收口径见 RECEPTION-ONBOARDING-MEMORY.md §11）：
- 草稿与私人接待记录独立于旧 ``memories`` 表存储（迁移编号区间 0300–0399）；
- 未确认候选不得调用 ``agent_engine.memory.update_pet_dna`` 或写旧 memories；
- 确认使用 draft_revision + Idempotency-Key，旧 revision 返回 VERSION_CONFLICT；
- 更正/撤回先停止使用（grant.revoked_at），再经 ``WebTaskQueue.supersede_pending``
  使 ``reception:note:<note_id>:`` 前缀的待生成任务失效，最后清理衍生物；
- 模型不可用时 mode=guided_notes，明确是引导便笺，不伪装自由对话；
- 所有读取按 (user_id, pet_id) 过滤；接待角色没有跨账号权限。
"""

from __future__ import annotations

from typing import Protocol

from ..schemas.web.reception import (
    CareNote,
    IntakeConfirmationRequest,
    IntakeConfirmationResult,
    MemoryCorrectionRequest,
    MemoryCorrectionResult,
    MemoryProjection,
    MemoryPurpose,
    ReceptionBranch,
    ReceptionSession,
    ReceptionTurnRequest,
)


class ReceptionService(Protocol):
    def start_session(self, user_id: str, pet_id: str, branch: ReceptionBranch) -> ReceptionSession: ...

    def get_session(self, user_id: str, session_id: str) -> ReceptionSession: ...

    def add_turn(
        self, user_id: str, session_id: str, request: ReceptionTurnRequest, idempotency_key: str
    ) -> ReceptionSession: ...

    def skip(self, user_id: str, session_id: str) -> ReceptionSession: ...

    def confirm(
        self, user_id: str, request: IntakeConfirmationRequest, idempotency_key: str
    ) -> IntakeConfirmationResult: ...

    def list_notes(self, user_id: str, pet_id: str) -> list[CareNote]: ...

    def correct(
        self, user_id: str, note_id: str, request: MemoryCorrectionRequest, idempotency_key: str
    ) -> MemoryCorrectionResult: ...

    def projection(self, user_id: str, pet_id: str, purpose: MemoryPurpose) -> MemoryProjection:
        """唯一的记忆读取出口；内部必须调用 policy.project_memory。"""
        ...
