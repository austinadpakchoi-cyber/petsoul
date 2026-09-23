"""意图与判断层契约（总方案 v1.5 §5.8、INTENT-DECISION-LAYER.md）。

判断（IntentAssessment）与业务执行（ActionProposal / ActionOutcome）分开：
- 判断器只输出信号、片段依据、限制范围与 unknown/澄清；**不含任何“已授权/已执行”字段**；
- 提议由代码按权限与领域状态生成，是否需要确认由代码决定；
- 执行结果只能由业务事务产生（ActionOutcome），模型不能自填。
confidence 可空，不能解释为正确率或用户许可；原文不进入普通日志。
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from .common import WebModel


class IntentChannel(str, Enum):
    reception = "reception"
    communicator = "communicator"


class IntentLayerMode(str, Enum):
    off = "off"
    shadow = "shadow"
    assist = "assist"


class IntentProvider(str, Enum):
    rule = "rule"
    configured_llm = "configured_llm"
    jev = "jev"


class SignalKind(str, Enum):
    share = "share"
    ask = "ask"
    request = "request"
    correct = "correct"
    refuse = "refuse"
    revoke = "revoke"
    missing = "missing"
    constraint = "constraint"
    wish = "wish"
    privacy_limit = "privacy_limit"
    unclear = "unclear"


class SignalSubject(str, Enum):
    owner = "owner"
    pet = "pet"
    place = "place"
    journey = "journey"
    memory = "memory"
    photo = "photo"
    unknown = "unknown"


class TemporalScope(str, Enum):
    past = "past"
    ongoing = "ongoing"
    future_wish = "future_wish"
    hypothetical = "hypothetical"
    current_command = "current_command"
    unknown = "unknown"


class UsageLimit(str, Enum):
    do_not_record = "do_not_record"
    do_not_relay = "do_not_relay"
    do_not_publish = "do_not_publish"


class SpanRef(WebModel):
    """原文片段依据：start/end 为 Python 字符串（Unicode 码点）下标，必须能在对应消息原文中匹配。"""

    start: int
    end: int
    text: str
    offset_unit: str = "unicode_codepoint"


class IntentSignal(WebModel):
    kind: SignalKind
    subject: SignalSubject
    target: str | None = None
    temporal: TemporalScope
    negated: bool = False
    quoted: bool = False
    span: SpanRef
    usage_limits: list[UsageLimit] = Field(default_factory=list)
    source: str = Field(description="judge（判断器）/ parser（解析步骤）；来源必须可区分")


class DecisionEvidence(WebModel):
    provider: IntentProvider
    requested_model: str | None = None
    effective_model: str | None = Field(default=None, description="只有真实返回时才填写")
    rule_version: str
    question_version: str | None = None
    raw_probabilities: dict[str, float] | None = None
    confidence: float | None = Field(default=None, description="输出分布集中度，不是正确率，也不是用户许可")
    latency_ms: int
    usage_note: str | None = None
    error: str | None = None
    degraded_reason: str | None = None


class IntentContext(WebModel):
    """最小上下文：账号归属由服务端提供；不附全量私密记忆。"""

    request_id: str
    message_id: str
    channel: IntentChannel
    language: str = "zh-CN"
    recent_context: list[str] = Field(default_factory=list, max_length=4)
    candidate_targets: list[str] = Field(default_factory=list)
    state_version: str | None = None


class IntentAssessment(WebModel):
    assessment_id: str
    signals: list[IntentSignal] = Field(default_factory=list)
    unknown: bool = False
    needs_clarification: bool = False
    conflicts: list[str] = Field(default_factory=list)
    evidence: DecisionEvidence


class ActionProposalKind(str, Enum):
    none = "none"
    clarify = "clarify"
    offer_control = "offer_control"
    record_candidate = "record_candidate"
    adjust_reply = "adjust_reply"


class ActionProposal(WebModel):
    proposal_id: str
    kind: ActionProposalKind
    target: str | None = None
    expected_state_version: str | None = None
    requires_confirmation: bool = True
    domain_check: str | None = Field(default=None, description="领域校验结论（代码产生），例如 route_change_not_allowed_by_intent")
    note: str | None = None


class ActionOutcomeState(str, Enum):
    proposed = "proposed"
    needs_confirmation = "needs_confirmation"
    blocked = "blocked"
    executed = "executed"
    failed = "failed"


class ActionOutcome(WebModel):
    proposal_id: str
    state: ActionOutcomeState
    operation_id: str | None = None
    result_version: str | None = None
    message: str | None = None


__all__ = [
    "IntentChannel",
    "IntentLayerMode",
    "IntentProvider",
    "SignalKind",
    "SignalSubject",
    "TemporalScope",
    "UsageLimit",
    "SpanRef",
    "IntentSignal",
    "DecisionEvidence",
    "IntentContext",
    "IntentAssessment",
    "ActionProposalKind",
    "ActionProposal",
    "ActionOutcomeState",
    "ActionOutcome",
]
