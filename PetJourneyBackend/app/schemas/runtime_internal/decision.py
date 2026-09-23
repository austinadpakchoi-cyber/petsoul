"""决策上下文、可行机会与大脑提案（契约 §2.6、§2.7）。只用标准库。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal

from .core import ActivityRef, AudienceScope, Versions
from .heartbeat import BrainPurpose

FactSource = Literal["owner_report", "world_event", "external_reference", "creative_fiction", "model_interpretation", "rule_interpretation"]
ComposedBy = Literal["model", "rule_fallback"]


@dataclass(frozen=True, slots=True)
class ContextFact:
    """进入决策上下文的一条最小事实（观察、记忆引用、承诺）。出现在这里之前已经按权限过滤。"""

    ref: str  # 来源引用（事件 ID、记忆 ID、消息编号、DNA 字段），最终提交时据此复核
    source: FactSource
    text: str  # 可放进提示词的最小文本，不含其他家人的私聊
    scope: AudienceScope  # 事实本身的可见范围；比上下文受众窄时只能影响决策，不能在表达里透露
    observed_at: datetime | None = None
    deadline_at: datetime | None = None  # 承诺类事实的截止时间


class ActionKind(str, Enum):
    """规则可以提供给大脑的动作类别。模型只能从 offer 里选，不能自己发明。"""

    stay_home = "stay_home"
    local_activity = "local_activity"
    work = "work"
    travel = "travel"


@dataclass(frozen=True, slots=True)
class ParamBound:
    """一个可选参数的允许范围：choices 非空时只能取其中之一，否则按 [minimum, maximum] 整数区间。"""

    choices: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None


@dataclass(frozen=True, slots=True)
class ActionOffer:
    """规则适配器给出的可行机会。已核验的目的地、班次、工作与工资只来自这里。"""

    offer_id: str
    action_kind: ActionKind
    summary: str  # 给模型看的事实描述（地点、时长、花费或收入），不含私密内容
    bounded_parameters: Mapping[str, ParamBound]
    source_ref: str  # 例如 "destination:local:stroll"、"job:<job_id>"、"sailing:<reference_id>"
    expected_versions: Versions
    valid_until: datetime
    cost_bounds: tuple[int, int] = (0, 0)  # 星币花费范围（含两端）；星币不是 API 费用
    income_bounds: tuple[int, int] = (0, 0)  # 星币收入范围：工资由规则决定，模型不能改
    duration_bounds: tuple[int, int] = (0, 0)  # 分钟


@dataclass(frozen=True, slots=True)
class DecisionContext:
    """一次有限决策的全部输入。由授权 ContextReader 先过滤再组装，不能先拿全部私聊再让模型过滤。"""

    operation_id: str
    purpose: BrainPurpose
    pet_id: str
    audience_scope: AudienceScope
    as_of: datetime
    deadline_at: datetime
    versions: Versions
    current_activity: ActivityRef | None
    permitted_dna: Mapping[str, str | tuple[str, ...]]  # 只含本用途获准的 DNA 字段
    memory_refs: tuple[ContextFact, ...] = ()
    observations: tuple[ContextFact, ...] = ()
    commitments: tuple[ContextFact, ...] = ()
    action_offers: tuple[ActionOffer, ...] = ()
    reason_codes: tuple[str, ...] = ()  # 心跳为什么需要思考
    conversation_id: str | None = None
    input_high_watermark: int | None = None  # 私聊回复覆盖到的最后一条输入序号；之后的新输入另行排队
    pet_name: str | None = None  # 0.1.1：宠物名字与物种单列，不再借用 permitted_dna 的键
    species: str | None = None


@dataclass(frozen=True, slots=True)
class BrainProposal:
    """模型（或明确标注的规则后备）给出的提案。不是已经执行，也不是已经发布。"""

    operation_id: str
    source_versions: Versions
    composed_by: ComposedBy  # 规则后备必须标 rule_fallback，不能冒充 model
    intent_summary: str  # 简短可审计的意图，不保存思维链
    selected_offer_id: str | None = None
    continue_current: bool = False
    parameters: Mapping[str, str | int] = field(default_factory=dict)
    suggested_review_after_seconds: int | None = None
    expression_request: str | None = None  # 只是提议；发不发、发给谁由表达层按权限决定
    memory_candidate_refs: tuple[str, ...] = ()  # 只是候选，不会自动变成永久记忆
    model_ref: str | None = None  # 例如 "deepseek:deepseek-chat"；rule_fallback 时为 None

    def __post_init__(self) -> None:
        if (self.selected_offer_id is not None) == self.continue_current:
            raise ValueError("提案必须二选一：选择一个 offer，或者继续当前活动")


class DecisionFailureCode(str, Enum):
    disabled = "disabled"  # 模型开关关闭或没有凭证：不偷偷调用
    budget_denied = "budget_denied"
    timeout = "timeout"
    provider_error = "provider_error"
    bad_output = "bad_output"  # 结构不合法（包括有限次格式修复后仍不合法）
    unknown_offer = "unknown_offer"
    out_of_bounds = "out_of_bounds"
    stale_context = "stale_context"  # 版本已变，或已过 offer 有效期
    revoked = "revoked"  # 权限撤回、成员移除
    deadline_passed = "deadline_passed"


@dataclass(frozen=True, slots=True)
class DecisionFailure:
    """决策失败或延期：只带原因，不虚构成功。集成者据此 DEFER，或走规则后备并标注 rule_fallback。"""

    operation_id: str
    code: DecisionFailureCode
    retryable: bool
    detail: str = ""  # 不含私密原文
    retry_after_seconds: int | None = None
