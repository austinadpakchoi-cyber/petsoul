"""提交结果与领域事件（契约 §2.8）。只用标准库。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .core import AudienceScope, Versions


class CommitStatus(str, Enum):
    committed = "committed"
    rejected = "rejected"
    pending = "pending"
    replayed = "replayed"


@dataclass(frozen=True, slots=True)
class CommitOutcome:
    """commit_proposal 或领域命令的结果。请求已受理、模型已返回，都不等于 committed。"""

    command_id: str
    status: CommitStatus
    reason_code: str | None = None
    state_version: int | None = None
    event_ids: tuple[str, ...] = ()
    receipt: Mapping[str, str] = field(default_factory=dict)  # 例如 {"journey_id": …, "ledger_key": …}


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """与领域状态同事务追加的事件；outbox 按它投递给通讯、动态、攻略等消费者。"""

    event_id: str
    aggregate_id: str
    aggregate_sequence: int
    kind: str
    effective_at: datetime  # 原本应发生的时间
    recorded_at: datetime  # 实际记账时间：晚恢复可以补结，但不伪造当时的剧情
    audience_scope: AudienceScope
    source_versions: Versions | None = None
    payload_ref: str | None = None
