"""任务领取令牌与额度预占（契约 §2.4、§2.5）。只用标准库。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .core import Versions

LostReason = Literal["expired", "taken_over", "superseded", "finished", "missing"]
ReservationStatus = Literal["reserved", "settled", "released", "unknown", "expired"]
SettleOutcome = Literal["succeeded", "failed", "not_sent", "unknown"]


@dataclass(frozen=True, slots=True)
class TaskClaim:
    """一次领取的令牌。续租、失败、完成与业务写入都要带 task_id + worker_id + claim_generation。"""

    task_id: str
    kind: str
    aggregate_id: str | None
    payload_ref: str | None
    worker_id: str
    claim_generation: int  # 每次领取（包括过期接管）递增；旧代数不能再写结果或改任务状态
    lease_until: datetime
    attempts: int
    max_attempts: int
    deadline_at: datetime | None = None
    source_versions: Versions | None = None  # 登记任务时依据的语义版本；旧任务类型可为 None


@dataclass(frozen=True, slots=True)
class LostClaim:
    """领取已失效。renew 直接返回它；assert_current_claim 与失败更新用 StaleClaim 异常携带它。"""

    task_id: str
    claim_generation: int
    reason: LostReason
    current_status: str | None = None
    current_generation: int | None = None


class StaleClaim(Exception):
    """在调用者事务里发现领取失效：调用者回滚整个业务事务，不写领域结果、回执或消息。"""

    def __init__(self, lost: LostClaim) -> None:
        super().__init__(f"{lost.task_id} 第 {lost.claim_generation} 代领取已失效：{lost.reason}")
        self.lost = lost


@dataclass(frozen=True, slots=True)
class BudgetReservation:
    """外部调用前的额度预占。同一 operation_id 重放不重复预占，多个进程看到的一致。"""

    reservation_id: str
    operation_id: str
    provider: str
    purpose: str
    subject_scope: str  # 最细的计费主体，例如 "pet:<id>"、"household:<id>"、"global"
    accounting_window: str  # 固定按 UTC 的记账窗口，例如 "2026-09-22"；不随宠物所在时区变化
    reserved_units: int
    expires_at: datetime
    status: ReservationStatus


@dataclass(frozen=True, slots=True)
class BudgetDenied:
    """预占被拒：没拿到预算的调用不访问外部服务。"""

    operation_id: str
    scope: str  # 哪一层额度不够
    reason: str  # 例如 "limit_reached"、"provider_disabled"、"concurrency"
    retry_after: datetime | None = None
