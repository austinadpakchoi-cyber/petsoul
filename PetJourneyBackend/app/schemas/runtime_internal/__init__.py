"""Runtime 并行开发的内部接口（RUNTIME-PARALLEL-CONTRACT v0.1，集成窗口接受为 runtime-internal 0.1.0）。

只用标准库，不 import 任何引擎；不进入网页公开契约（scripts/gen_web_contract.py 只扫 app/schemas/web），
也不由 app/schemas/__init__.py 导出。各包一律从本包导入：``from app.schemas.runtime_internal import X``；
子模块划分只是为了控制文件规模，不是接口的一部分。

只由集成窗口修改。需要新字段或新取值时，在自己的窗口日志写 CHANGE_REQUEST，由集成窗口升版本号实施。

版本：0.1.0 接受 v0.1 契约；0.1.1（兼容追加）HeartbeatDecision.silence_reason、FactSource 增加 rule_interpretation、
DecisionContext.pet_name / species。
"""

from .commit import CommitOutcome, CommitStatus, DomainEvent
from .core import ActivityKind, ActivityRef, AudienceKind, AudienceScope, Clock, Versions
from .decision import (
    ActionKind,
    ActionOffer,
    BrainProposal,
    ComposedBy,
    ContextFact,
    DecisionContext,
    DecisionFailure,
    DecisionFailureCode,
    FactSource,
    ParamBound,
)
from .heartbeat import (
    BrainPurpose,
    CognitionStatus,
    HeartbeatAction,
    HeartbeatDecision,
    RuntimeState,
    TaskIntent,
    WakeEvent,
    WakeKind,
)
from .reliability import (
    BudgetDenied,
    BudgetReservation,
    LostClaim,
    LostReason,
    ReservationStatus,
    SettleOutcome,
    StaleClaim,
    TaskClaim,
)

RUNTIME_INTERNAL_VERSION = "0.1.1"

__all__ = [
    "RUNTIME_INTERNAL_VERSION",
    # 2.1 时钟
    "Clock",
    # 2.2 版本与每宠运行状态
    "Versions",
    "ActivityKind",
    "ActivityRef",
    "CognitionStatus",
    "RuntimeState",
    # 2.3 唤醒事件与心跳结果
    "WakeKind",
    "WakeEvent",
    "HeartbeatAction",
    "BrainPurpose",
    "TaskIntent",
    "HeartbeatDecision",
    # 2.4 任务领取
    "TaskClaim",
    "LostClaim",
    "LostReason",
    "StaleClaim",
    # 2.5 额度预占
    "BudgetReservation",
    "BudgetDenied",
    "ReservationStatus",
    "SettleOutcome",
    # 2.6 决策上下文与可行机会
    "AudienceKind",
    "AudienceScope",
    "FactSource",
    "ContextFact",
    "ActionKind",
    "ParamBound",
    "ActionOffer",
    "DecisionContext",
    # 2.7 大脑提案
    "ComposedBy",
    "BrainProposal",
    "DecisionFailureCode",
    "DecisionFailure",
    # 2.8 提交结果与领域事件
    "CommitStatus",
    "CommitOutcome",
    "DomainEvent",
]
