"""决策包自己的端口与参数（不进共享类型）：授权读取 ContextReader、模型 ModelAdapter、只读工具 ToolPort、调用限额与决策请求。

共享数据（Versions、AudienceScope、ContextFact、ActionOffer、DecisionContext、BrainProposal、DecisionFailure、BudgetReservation……）
一律来自 app.schemas.runtime_internal，这里不另定义同名类型。

ContextReader 由集成窗口实现：每个方法都必须先在存储层按 (宠物, 受众, 用途) 过滤权限，再返回最小资料；
不允许先取回全部家人私聊再指望这里或模型“忽略”。决策包还会按受众、用途与模型许可再核一遍，越权条目直接丢弃并只记 ref 与原因。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from ...schemas.runtime_internal import ActionOffer, ActivityRef, AudienceScope, BrainPurpose, DecisionFailureCode, FactSource, SettleOutcome, Versions


@dataclass(frozen=True)
class PetBrief:
    name: str
    species: str  # cat / dog / ……


@dataclass(frozen=True)
class DnaSnapshot:
    """全家共用的那一层 DNA（或还没保存时给全家的草稿）。个人层（称呼、小暗号）不在这里。"""

    fields: Mapping[str, tuple[str, ...]]  # 栏目 → 原话（单值栏目也用元组）
    confirmed: bool
    source: str = "owner"  # owner（家人保存）/ owner_bio / adoption_profile


@dataclass(frozen=True)
class Record:
    """读取端口返回的一条资料（尚未二次过滤）。scope 是它本身的可见范围：某位家人私有的用 private（带 user_id，
    最好也带 household_id）；purposes 是记忆授权用途（MemoryPurpose 取值）；model_ok＝私有资料的主人同意交给模型处理。"""

    ref: str
    source: FactSource
    text: str
    scope: AudienceScope
    kind: str = ""
    purposes: tuple[str, ...] = ()
    model_ok: bool = True
    observed_at: datetime | None = None
    deadline_at: datetime | None = None


class ContextReader(Protocol):
    def versions(self, pet_id: str) -> Versions: ...

    def audience_valid(self, pet_id: str, audience: AudienceScope) -> bool:
        """此刻受众仍然有效：宠物仍属于这个家庭（或仍是驿站居民）。"""
        ...

    def pet_brief(self, pet_id: str) -> PetBrief | None: ...

    def shared_dna(self, pet_id: str) -> DnaSnapshot | None: ...

    def memory_items(self, pet_id: str, audience: AudienceScope, purposes: Sequence[str], limit: int) -> Sequence[Record]:
        """MemoryPolicy 投影：只含按这些用途授权过的叮嘱，每条带归属、用途与 model_ok。"""
        ...

    def observations(self, pet_id: str, audience: AudienceScope, limit: int) -> Sequence[Record]:
        """最近真实发生的事（world_event）与现实参考（external_reference），新的在前。"""
        ...

    def commitments(self, pet_id: str, audience: AudienceScope, limit: int) -> Sequence[Record]:
        """家人的建议、“今天别出门”一类的信号（合并后不指明是谁、不带原话）、答应过的事、之前的打算（model_interpretation）。"""
        ...

    def activity(self, pet_id: str, now: datetime) -> ActivityRef | None: ...

    def local_time(self, pet_id: str, now: datetime) -> datetime | None:
        """宠物所在地的当地时间；时区未知返回 None（不默认某个城市）。"""
        ...

    def wallet_balance(self, pet_id: str) -> int | None: ...


@dataclass(frozen=True)
class ModelReply:
    text: str
    requested_model: str | None = None
    effective_model: str | None = None
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ModelCallError(Exception):
    """模型调用失败。outcome 与预算结算一致：not_sent（没发出去）/ failed（对方拒绝）/ unknown（可能已被受理，不能当作没花钱）。"""

    def __init__(self, code: DecisionFailureCode, outcome: SettleOutcome, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.outcome = outcome
        self.reason = reason


class ModelAdapter(Protocol):
    available: bool
    provider_label: str
    max_call_seconds: float  # 单次调用最长可能耗时；剩余时间不够就不发起

    def complete(self, messages: list[dict[str, str]], *, max_tokens: int) -> ModelReply: ...


@dataclass(frozen=True)
class ToolSpec:
    """集成窗口提供的只读查询（例如查看某项行动的具体行程）。arg：offer（行动编号）或 ref（资料编号）。"""

    name: str
    description: str
    arg: str = "offer"


class ToolPort(Protocol):
    """实现方自己负责授权与外部调用的预算；决策包只管次数、参数是否是给出的编号、截止时间。"""

    def call(self, name: str, arg: str, *, pet_id: str, audience: AudienceScope) -> str: ...


@dataclass(frozen=True)
class CallLimits:
    max_model_calls: int = 2  # 含一次格式修复，或一次工具查询后的续问
    max_tool_calls: int = 3
    max_output_tokens: int = 300
    min_review_minutes: int = 15
    max_review_minutes: int = 720


@dataclass(frozen=True)
class DecisionRequest:
    """集成窗口发起一次决策。offers 由规则适配器给出，只包含此刻真正可行的行动。"""

    operation_id: str
    pet_id: str
    purpose: BrainPurpose
    audience: AudienceScope
    as_of: datetime
    deadline_at: datetime
    offers: tuple[ActionOffer, ...] = ()
    reason_codes: tuple[str, ...] = ()
    conversation_id: str | None = None
    input_high_watermark: int | None = None
    limits: Mapping[str, int] = field(default_factory=dict)  # 资料条数上限的覆盖值（observations / memory_refs / ……）
    expected_versions: Versions | None = None  # 心跳登记这次思考时的版本（B 的 state.versions）；读到的已经变了就不开始思考
    model_consent: bool = False  # 家庭同意把共用资料交给模型（沿用家庭的“模型回信”开关）；默认 False：一次都不调用模型
