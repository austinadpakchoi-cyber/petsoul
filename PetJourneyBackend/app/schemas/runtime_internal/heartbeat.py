"""每宠运行状态、唤醒事件与心跳结果（契约 §2.2、§2.3）。只用标准库。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum
from typing import Literal

from .core import ActivityRef, Versions

CognitionStatus = Literal["quiet", "queued", "running", "waiting", "backoff", "disabled"]
BrainPurpose = Literal["life_plan", "private_reply", "expression"]


@dataclass(frozen=True, slots=True)
class RuntimeState:
    """每只宠物一份运行投影：不按家人数量成倍建立，不复制钱包或库存。由集成者从真实库生成。"""

    pet_id: str
    realm_id: str  # 正式 / 测试 / 演示的运行边界（首版对应部署环境）
    versions: Versions
    as_of: datetime  # 投影读取时刻（UTC）
    household_id: str | None  # 待领养居民没有家庭；有家庭时共享资源按家庭
    timezone: str | None  # 当前生活时区（IANA）。未知为 None：策略给出明确的不可用结果，不能默认某个城市
    region_id: str | None
    scene_ref: str | None  # 家园、驿站、店铺、交通段等，复用 home_id / visit_id / leg_id
    primary_activity: ActivityRef | None  # 契约里的 primary_activity_ref 与 activity_ends_at 都在这里
    sleep_window: tuple[time, time] | None  # DNA 作息（当地钟点：入睡，起床）；未知为 None
    next_check_at: datetime | None = None
    silence_reason: str | None = None
    pending_commitment_deadline: datetime | None = None
    cognition_status: CognitionStatus = "quiet"


class WakeKind(str, Enum):
    """可以提前唤醒心跳的事实类别。只传事实与时间，不传私聊正文。"""

    activity_due = "activity_due"  # 活动、交通段、打工或到访到了结束边界
    commitment_due = "commitment_due"  # 对家人的回复承诺或已约定事项到期
    message_received = "message_received"  # 家人发来新消息（正文不在事件里）
    suggestion_received = "suggestion_received"  # 家人留了出行或生活建议
    versions_changed = "versions_changed"  # DNA 更正、撤权、成员变化、改签
    dependency_recovered = "dependency_recovered"  # 模型、地图等依赖恢复
    budget_restored = "budget_restored"  # 新记账窗口或额度释放
    clock_unhealthy = "clock_unhealthy"  # 宿主机时间回拨或跳跃
    task_expired = "task_expired"  # 任务租约过期，需要恢复


@dataclass(frozen=True, slots=True)
class WakeEvent:
    """已授权的唤醒事实。sequence 在同一只宠物内单调递增，用于去重和排序。"""

    event_id: str
    pet_id: str
    kind: WakeKind
    effective_at: datetime  # 事实原本应发生的时间
    source_ref: str  # 来源记录（消息编号、旅程段、任务编号……），不含正文
    sequence: int


class HeartbeatAction(str, Enum):
    CONTINUE = "continue"
    APPLY_RULE = "apply_rule"
    REQUEST_BRAIN = "request_brain"
    DEFER = "defer"
    RECOVER = "recover"


@dataclass(frozen=True, slots=True)
class TaskIntent:
    """心跳建议登记的后续任务。只是意图：集成事务成功后才真正入队（按 dedupe_key 去重）。"""

    kind: str  # 例如 "settle_due"（到期结算）、"brain_decide"、"retry_dependency"、"recover_task"
    aggregate_id: str  # 宠物、旅程等领域主体
    run_at: datetime
    dedupe_key: str
    source_ref: str | None = None
    deadline_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class HeartbeatDecision:
    """evaluate(state, authorized_events, policy, now) 的结果。纯函数产物，不代表已经执行。

    约定：
      - 除非明确等待某类事件（wait_event_kinds），next_check_at 必须有值；
      - 过去的时刻交给到期队列，不能反复返回“立刻再查”造成零延迟空转；
      - consumed_event_ids 只是建议，集成事务成功后才确认消费。
    """

    action: HeartbeatAction
    reason_codes: tuple[str, ...]
    next_check_at: datetime | None = None
    wait_event_kinds: tuple[WakeKind, ...] = ()
    task_intents: tuple[TaskIntent, ...] = ()
    brain_purpose: BrainPurpose | None = None
    consumed_event_ids: tuple[str, ...] = ()
    silence_reason: str | None = None  # 0.1.1：安静的原因（B 的取值表）；运维看“正常安静”还是“故障安静”
