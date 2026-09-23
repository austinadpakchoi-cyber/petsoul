"""测试与影子对照用的替身（不联网、不读库）：按剧本回答的假模型、内存里的读取端口、手动拨动的时钟。

集成窗口与独立验收可以直接用它们在隔离库里证明“模型的选择改变了真实计划”，不产生任何付费调用。
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ...schemas.runtime_internal import ActivityRef, AudienceScope, BudgetReservation, DecisionFailureCode, Versions
from .ports import DnaSnapshot, ModelCallError, ModelReply, PetBrief, Record


def reservation_for(operation_id: str, *, now: datetime, units: int = 2, minutes: int = 5, status: str = "reserved") -> BudgetReservation:
    """A 包接好之前的预占替身：一次操作允许 units 次模型调用，minutes 分钟内有效。"""
    return BudgetReservation(reservation_id=f"res-{operation_id}", operation_id=operation_id, provider="llm", purpose="life_plan",
                             subject_scope="global", accounting_window=now.date().isoformat(), reserved_units=units,
                             expires_at=now + timedelta(minutes=minutes), status=status)


class ManualClock:
    """实现 runtime-internal 的 Clock：now_utc 只在 advance 时前进。"""

    def __init__(self, at: datetime) -> None:
        self.at = at

    def now_utc(self) -> datetime:
        return self.at

    def monotonic(self) -> float:
        return time.monotonic()

    def advance(self, **delta) -> None:
        self.at += timedelta(**delta)


class ScriptedModel:
    """按顺序回放预设回答。每个回答可以是字符串、异常（例如 ModelCallError），或 callable(messages) -> str。
    on_call(第几次调用) 在回答前执行，可用来模拟“思考期间世界变了”（撤权、DNA 更正、时间流逝）。"""

    provider_label = "scripted"

    def __init__(self, *replies, available: bool = True, max_call_seconds: float = 5.0, on_call: Callable[[int], None] | None = None) -> None:
        self.replies = list(replies)
        self.available = available
        self.max_call_seconds = max_call_seconds
        self.on_call = on_call
        self.calls: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]], *, max_tokens: int) -> ModelReply:
        self.calls.append([dict(m) for m in messages])
        if self.on_call is not None:
            self.on_call(len(self.calls))
        if not self.replies:
            raise ModelCallError(DecisionFailureCode.provider_error, "failed", "script exhausted")
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        text = reply(messages) if callable(reply) else reply
        return ModelReply(text=text, requested_model="scripted", effective_model="scripted-1", latency_ms=1)


@dataclass
class MemoryReader:
    """内存里的读取端口：原样返回预置资料（可以故意放入越权条目，验证决策包的二次过滤）。"""

    brief: PetBrief | None = field(default_factory=lambda: PetBrief("测试伙伴", "cat"))
    version_state: Versions = field(default_factory=lambda: Versions(runtime_epoch=1, activity_epoch=1, dna_version=1, privacy_epoch=1, membership_epoch=1))
    dna: DnaSnapshot | None = None
    memory_records: Sequence[Record] = ()
    observation_records: Sequence[Record] = ()
    commitment_records: Sequence[Record] = ()
    activity_ref: ActivityRef | None = field(default_factory=lambda: ActivityRef("at_home", None))
    local: datetime | None = None
    balance: int | None = 20
    valid: bool = True
    calls: list[str] = field(default_factory=list)

    def versions(self, pet_id: str) -> Versions:
        self.calls.append("versions")
        return self.version_state

    def audience_valid(self, pet_id: str, audience: AudienceScope) -> bool:
        self.calls.append("audience_valid")
        return self.valid

    def pet_brief(self, pet_id: str) -> PetBrief | None:
        return self.brief

    def shared_dna(self, pet_id: str) -> DnaSnapshot | None:
        return self.dna

    def memory_items(self, pet_id: str, audience: AudienceScope, purposes: Sequence[str], limit: int) -> Sequence[Record]:
        self.calls.append(f"memory_items:{audience.kind}:{','.join(purposes)}")
        return self.memory_records

    def observations(self, pet_id: str, audience: AudienceScope, limit: int) -> Sequence[Record]:
        return self.observation_records

    def commitments(self, pet_id: str, audience: AudienceScope, limit: int) -> Sequence[Record]:
        return self.commitment_records

    def activity(self, pet_id: str, now: datetime) -> ActivityRef | None:
        return self.activity_ref

    def local_time(self, pet_id: str, now: datetime) -> datetime | None:
        return self.local

    def wallet_balance(self, pet_id: str) -> int | None:
        return self.balance
