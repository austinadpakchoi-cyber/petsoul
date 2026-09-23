"""包 B 的输入事实与推导函数（不定义与 app.schemas.runtime_internal 同名的类）。

共享的 RuntimeState（runtime-internal 0.1.0）描述每只宠物的运行投影：版本、时区、主活动、作息、最早承诺截止、认知状态。
心跳还需要几样共享类型里没有的细节，由集成层在同一次读取里一并给出（HeartbeatFacts）：
- 到期事项 DueItem：到点就该由确定性规则处理的事，例如旅程事件与工钱、待回复承诺；每项带稳定引用和重试信息；
- 认知可用性 CognitionFacts：大脑是否允许、供应商与额度状态、进行中的认知操作及其依据的版本；
- 自主复查 AutonomyFacts：出门时段、今天出去了几次、下次复查时刻、上次决定时刻、最新建议时刻；
- 上次心跳评估时刻、维护开关。
这些都是一次读取的只读快照：不持有钱包、库存或位置事实，也不按家人复制，私聊承诺按会话引用区分。
如果集成窗口决定把其中某些类型并入 runtime_internal，这里改为从那里导入即可（见 fed3 日志的 CHANGE_REQUEST）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum

from ..schemas.runtime_internal import BrainPurpose, CognitionStatus, RuntimeState, Versions

# 与 web_agent.life 的默认出门时段一致（默认作息 07:30 起、23:30 睡）；集成层按 DNA 作息传入 life.decide_window 的结果。
DEFAULT_ACTIVE_WINDOW = (time(8, 30), time(17, 30))


class DueKind(str, Enum):
    JOURNEY = "journey"  # 旅程的到期事件（出发、到站、到店、离店、工钱、回家）：整段旅程按顺序补齐
    REPLY = "reply"  # 待回复承诺（按“家人＋宠物”的会话区分）
    COOLDOWN = "cooldown"  # 冷却或资格恢复（例如补考冷却结束）
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class DueItem:
    """一件到点就该由确定性规则处理的事。

    ref 稳定且不含正文，例如 journey:<旅程编号>、reply:<会话引用>。同一段旅程只给一项（due_at 取最早一个未生效的事件），
    由旅程服务按顺序补齐，工钱在其中只入账一次。
    """

    ref: str
    kind: DueKind
    due_at: datetime
    commitment: bool = False  # 对家人的承诺（待回复、工钱）：排在最前，不能被延期或丢弃
    deadline_at: datetime | None = None  # 承诺最晚应兑现的时刻；过了仍然兑现，只是记为逾期
    attempts: int = 0  # 已经失败的次数（集成层记录）
    retry_after: datetime | None = None  # 失败后最早再试的时刻
    itinerary_version: int | None = None  # 旅程事件依据的行程版本；与当前版本不一致时不执行，先对账
    input_high_watermark: int | None = None  # 回复承诺覆盖到会话里的第几条输入


class BrainAvailability(str, Enum):
    AVAILABLE = "available"
    DISABLED = "disabled"  # 没配置、没开启（产品开关或家庭设置）
    EXHAUSTED = "exhausted"  # 额度用完（记账窗口按 UTC）
    UNAVAILABLE = "unavailable"  # 依赖故障：超时、报错、限流


@dataclass(frozen=True, slots=True)
class InFlightBrain:
    """进行中的认知操作。同一只宠物同一时间最多一个。"""

    operation_id: str
    purpose: BrainPurpose
    source_versions: Versions
    requested_at: datetime
    deadline_at: datetime
    running: bool = False  # False：已登记、等待领取；True：已被 worker 领取


@dataclass(frozen=True, slots=True)
class CognitionFacts:
    enabled: bool = False  # 这只宠物允许用大脑做生活规划（产品开关与家庭设置）；居民另由策略参数决定
    availability: BrainAvailability = BrainAvailability.DISABLED
    retry_after: datetime | None = None  # 依赖故障或额度用完时，最早可以再试的时刻
    remaining_today: int | None = None  # 本记账窗口（UTC）还能发起几次生活规划；None 表示未知或不限
    window_resets_at: datetime | None = None
    operation: InFlightBrain | None = None
    last_requested_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AutonomyFacts:
    active_window: tuple[time, time] = DEFAULT_ACTIVE_WINDOW  # 当地出门时段
    outings_today: int = 0  # 今天（当地日期）已经出门几次
    outings_per_day: int = 2  # DNA 画像给出的每天出门次数
    next_review_at: datetime | None = None  # 上次决定写下的下次自主复查时刻；None 表示现在就该复查
    last_decision_at: datetime | None = None  # 上次生活决定（大脑或规则）提交的时刻
    latest_suggestion_at: datetime | None = None  # 家人最新一条还在考虑中的建议


@dataclass(frozen=True, slots=True)
class HeartbeatFacts:
    due_items: tuple[DueItem, ...] = ()
    cognition: CognitionFacts = field(default_factory=CognitionFacts)
    autonomy: AutonomyFacts = field(default_factory=AutonomyFacts)
    last_evaluated_at: datetime | None = None  # 上次心跳评估时刻（集成层持久化），用于识别时钟回拨与长时间补齐
    maintenance: bool = False  # 管理员暂停这只宠物的运行

    def __post_init__(self) -> None:
        cognition, autonomy = self.cognition, self.autonomy
        stamps = [("last_evaluated_at", self.last_evaluated_at), ("cognition.retry_after", cognition.retry_after),
                  ("cognition.window_resets_at", cognition.window_resets_at), ("cognition.last_requested_at", cognition.last_requested_at),
                  ("autonomy.next_review_at", autonomy.next_review_at), ("autonomy.last_decision_at", autonomy.last_decision_at),
                  ("autonomy.latest_suggestion_at", autonomy.latest_suggestion_at)]
        if cognition.operation is not None:
            stamps += [("operation.requested_at", cognition.operation.requested_at), ("operation.deadline_at", cognition.operation.deadline_at)]
        for item in self.due_items:
            stamps += [(f"{item.ref}.due_at", item.due_at), (f"{item.ref}.deadline_at", item.deadline_at),
                       (f"{item.ref}.retry_after", item.retry_after)]
            if item.attempts < 0:
                raise ValueError(f"{item.ref}.attempts 不能为负数")
        for name, value in stamps:
            _require_aware(name, value)
        if autonomy.outings_today < 0 or autonomy.outings_per_day < 0:
            raise ValueError("出门次数不能为负数")


def _require_aware(name: str, value: datetime | None) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{name} 必须带时区（UTC）")


def commitment_deadline(facts: HeartbeatFacts) -> datetime | None:
    """共享 RuntimeState.pending_commitment_deadline 的推导：最早一件承诺的到期时刻。集成层用它填投影，与心跳看到的一致。"""
    times = [item.due_at for item in facts.due_items if item.commitment]
    return min(times) if times else None


def cognition_status(facts: HeartbeatFacts, now: datetime) -> CognitionStatus:
    """共享 RuntimeState.cognition_status 的推导（方案 §6）。“waiting”（已发给供应商、等待回应）由认知 worker 自己标记，这里推不出来。"""
    cognition = facts.cognition
    if cognition.operation is not None:
        return "running" if cognition.operation.running else "queued"
    if not cognition.enabled or cognition.availability is BrainAvailability.DISABLED:
        return "disabled"
    if cognition.availability in (BrainAvailability.EXHAUSTED, BrainAvailability.UNAVAILABLE):
        if cognition.retry_after is None or cognition.retry_after > now:
            return "backoff"
    return "quiet"


def facts_from_state(state: RuntimeState) -> HeartbeatFacts:
    """集成层还没提供 HeartbeatFacts 时的最小事实（过渡用，能力有限）。

    - 最早承诺截止当作一件待兑现的承诺（ref 为 commitment:earliest）；
    - 不启用大脑：共享状态里没有开关与额度信息，按项目默认不新增远端调用，空闲时走 DNA 规则生活。
      认知状态只换算成可用性，供原因码参考：quiet 可用，disabled 不可用，其余（queued/running/waiting/backoff）当作暂不可用。
    正式接入请提供完整的 HeartbeatFacts，否则心跳看不到重试次数、进行中操作的截止与版本。
    """
    due = ()
    if state.pending_commitment_deadline is not None:
        due = (DueItem("commitment:earliest", DueKind.OTHER, state.pending_commitment_deadline, commitment=True),)
    status = state.cognition_status
    availability = {"quiet": BrainAvailability.AVAILABLE, "disabled": BrainAvailability.DISABLED}.get(status, BrainAvailability.UNAVAILABLE)
    return HeartbeatFacts(due_items=due, cognition=CognitionFacts(enabled=False, availability=availability))
