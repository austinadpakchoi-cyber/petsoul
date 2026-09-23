"""宠物心跳：纯函数 evaluate(state, authorized_events, policy, now) → HeartbeatDecision（包 B）。

输入是集成层从真实库读出的 RuntimeState 投影、同一次读取给出的 HeartbeatFacts，以及已授权的唤醒事件；输出共享类型 HeartbeatDecision。
函数本身不写库、不联网、不调模型、不预占额度、不读宿主机时区；同样的输入永远得到同样的结论。
每只宠物一份状态、一次评估：不按家人复制；待领养居民（household_id 为 None）照样评估。

判断顺序：
1. 管理员维护中：DEFER，什么都不做。
2. 时钟不可靠（ClockMonitor 报回拨或前跳、now 早于上次评估、投影时刻晚于 now、收到 clock_unhealthy 事件）：
   RECOVER。不结算、不请求大脑；除时钟事件外，其余事件都不确认消费。
3. 收集要做的事，有就在本次返回。有恢复类意图时动作为 RECOVER，否则为 APPLY_RULE：
   - 到期事项：承诺（待回复、工钱）排最前，其余按到期时间。睡着、大脑关闭、额度用完都不影响它们。
     连续失败的交给恢复，行程版本对不上的先对账。一次最多 max_intents 项，其余下一轮接着处理。
   - task_expired 事件：交给恢复。
   - 进行中的认知操作：超过截止交给恢复；依据的版本变了（运行归属、活动、DNA、用途授权、家庭成员、行程）就作废。
   - 主活动未知，或早该结束却没有到期事项：对账。有宽限期和退避，不会空转。
4. 还没入住：只等入住，不安排生活。
5. 活动进行中（在路上、在店里、打工、考试、在家等出门时间）：CONTINUE 到活动结束。期间不请求大脑，收到的建议先记着。
6. 在家（居民在驿站）空闲，按 TA 所在地的钟点判断：
   - 时区认不出：RECOVER（数据问题，不套用默认时区）；
   - 睡着、不在出门时段、今天出去够了、还没到复查时间、离上次决定太近：CONTINUE；
   - 该复查了：大脑可用就 REQUEST_BRAIN；不可用时按 brain_fallback，用 DNA 规则生活（APPLY_RULE rule_life_plan）或 DEFER。
下一次检查永远晚于 now（至少 min_delay），也不晚于 now + max_check_interval（看门狗）。过去的时刻交给到期事项处理，不会被当成“马上再查”。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Iterable, Mapping

from ..schemas.runtime_internal import HeartbeatAction, HeartbeatDecision, RuntimeState, TaskIntent, WakeEvent, WakeKind
from .clock_policy import ClockHealth, ClockHealthStatus, ensure_utc, in_local_window, local_wall, next_local_occurrence, resolve_zone
from .reasons import IntentKind, ReasonCode, SilenceReason, silence_code
from .state import BrainAvailability, DueItem, DueKind, HeartbeatFacts, InFlightBrain, facts_from_state
from .wake_events import MergedEvents, merge_events

POLICY_VERSION = "heartbeat-2026.1"
ONGOING = frozenset({"local_activity", "work", "travel", "visit", "exam"})
RECOVERY_INTENTS = frozenset({IntentKind.RECOVER_TASK.value, IntentKind.RECONCILE.value})
STUCK_CODES = frozenset({ReasonCode.DUE_ITEM_STUCK.value, ReasonCode.TASK_EXPIRED.value, ReasonCode.BRAIN_EXPIRED.value})

WAIT_AFTER_ACTION = (WakeKind.activity_due, WakeKind.commitment_due, WakeKind.versions_changed, WakeKind.task_expired, WakeKind.clock_unhealthy)
WAIT_ACTIVITY = WAIT_AFTER_ACTION + (WakeKind.message_received,)
WAIT_IDLE = WAIT_ACTIVITY + (WakeKind.suggestion_received, WakeKind.dependency_recovered, WakeKind.budget_restored)
WAIT_QUIET = (WakeKind.versions_changed, WakeKind.dependency_recovered, WakeKind.clock_unhealthy)  # 维护中、时区待修：等数据修好


@dataclass(frozen=True, slots=True)
class HeartbeatPolicy:
    """心跳参数。数值是首轮建议（世界运行方案 v0.2 §11），按实测调整；只会收紧已有预算，不扩大付费范围。"""

    min_delay: timedelta = timedelta(seconds=1)  # 下次检查至少晚这么久，防止零延迟空转
    max_check_interval: timedelta = timedelta(hours=6)  # 看门狗：任何状态最迟这么久再看一次
    idle_review_interval: timedelta = timedelta(minutes=15)  # 空闲时一次决定之后的默认复查间隔
    max_review_interval: timedelta = timedelta(hours=6)  # 大脑建议的复查间隔上限
    min_decision_interval: timedelta = timedelta(minutes=15)  # 两次生活决定（大脑或规则）之间至少隔多久
    brain_deadline: timedelta = timedelta(seconds=90)  # 一次认知操作从登记到提交的截止
    follow_up: timedelta = timedelta(seconds=60)  # 交出规则或恢复意图之后多久复查（集成层提交后也可以立刻再评估）
    dependency_recheck: timedelta = timedelta(minutes=5)  # 依赖不可用、数据待修时的复查间隔
    activity_grace: timedelta = timedelta(minutes=2)  # 活动过了结束时间还没有到期事项，宽限多久才算不一致
    clock_tolerance: timedelta = timedelta(seconds=30)  # 进程之间可以接受的时钟偏差
    catch_up_after: timedelta = timedelta(minutes=30)  # 距上次评估超过这么久，记为“补齐中”
    max_intents: int = 20  # 一次最多交出几项到期事项
    max_due_attempts: int = 5  # 到期事项失败这么多次后交给恢复
    brain_fallback: str = "rule"  # rule：大脑不可用时按 DNA 规则生活；wait：延期等大脑
    resident_brain: bool = False  # 待领养居民是否用大脑（默认不用：居民不触发模型，按规则生活）
    default_sleep_window: tuple[time, time] = (time(23, 30), time(7, 30))  # 没有作息信息时的产品默认作息
    version: str = POLICY_VERSION

    def __post_init__(self) -> None:
        if self.brain_fallback not in ("rule", "wait"):
            raise ValueError("brain_fallback 只能是 rule 或 wait")
        durations = (self.min_delay, self.max_check_interval, self.idle_review_interval, self.max_review_interval, self.min_decision_interval,
                     self.brain_deadline, self.follow_up, self.dependency_recheck, self.activity_grace, self.clock_tolerance, self.catch_up_after)
        if any(value <= timedelta(0) for value in durations) or self.min_delay >= self.max_check_interval:
            raise ValueError("时长参数必须为正，且 min_delay 要小于 max_check_interval")
        if self.max_intents < 1 or self.max_due_attempts < 1:
            raise ValueError("max_intents 与 max_due_attempts 至少为 1")


@dataclass
class _Draft:
    """一次评估的草稿：收集原因、意图和候选检查时刻，最后统一定出下一次检查。"""

    state: RuntimeState
    facts: HeartbeatFacts
    policy: HeartbeatPolicy
    now: datetime
    events: MergedEvents
    codes: list[str] = field(default_factory=list)
    intents: list[TaskIntent] = field(default_factory=list)
    times: list[datetime] = field(default_factory=list)

    def code(self, *codes: ReasonCode | str) -> None:
        for code in codes:
            text = code.value if isinstance(code, ReasonCode) else code
            if text not in self.codes:
                self.codes.append(text)

    def intent(self, kind: IntentKind, source_ref: str, dedupe_key: str, deadline_at: datetime | None = None) -> None:
        if all(item.dedupe_key != dedupe_key for item in self.intents):
            self.intents.append(TaskIntent(kind=kind.value, aggregate_id=self.state.pet_id, run_at=self.now, dedupe_key=dedupe_key,
                                           source_ref=source_ref, deadline_at=deadline_at))

    def at(self, *times: datetime | None) -> None:
        self.times.extend(value for value in times if value is not None)

    def done(self, action: HeartbeatAction, silence: SilenceReason | None, waits: Iterable[WakeKind], *,
             purpose: str | None = None, consumed: tuple[str, ...] | None = None) -> HeartbeatDecision:
        now, policy = self.now, self.policy
        watchdog = now + policy.max_check_interval
        upcoming = [value for value in self.times if now < value < watchdog]
        if not upcoming:
            self.code(ReasonCode.WATCHDOG)
        next_check = max(min(upcoming, default=watchdog), now + policy.min_delay)
        if silence is not None:
            self.code(silence_code(silence))  # 0.1.1 起同时写 silence_reason 字段；原因码保留一个版本，便于旧读取方
        return HeartbeatDecision(action=action, reason_codes=tuple(self.codes), next_check_at=next_check,
                                 wait_event_kinds=tuple(sorted(set(waits), key=lambda kind: kind.value)), task_intents=tuple(self.intents),
                                 brain_purpose=purpose, consumed_event_ids=self.events.consumed_ids if consumed is None else consumed,
                                 silence_reason=silence.value if silence is not None else None)


def evaluate(state: RuntimeState, authorized_events: Iterable[WakeEvent], policy: HeartbeatPolicy, now: datetime, *,
             facts: HeartbeatFacts | None = None, clock_health: ClockHealth | None = None) -> HeartbeatDecision:
    """对一只宠物做一次心跳评估。facts 缺省时只用共享 RuntimeState 推出最小事实（见 state.facts_from_state）。"""
    now = ensure_utc(now, "now")
    _validate(state)
    facts = facts_from_state(state) if facts is None else facts
    events = merge_events(state.pet_id, authorized_events, now, tolerance=policy.clock_tolerance)
    draft = _Draft(state, facts, policy, now, events)
    _note_events(draft)
    if facts.maintenance:  # 维护中连事件也不确认：task_expired 这类事实只在事件里，维护结束后还要处理
        draft.code(ReasonCode.MAINTENANCE)
        draft.at(now + policy.dependency_recheck)
        return draft.done(HeartbeatAction.DEFER, SilenceReason.MAINTENANCE, WAIT_QUIET, consumed=())
    problems = _clock_problems(draft, clock_health)
    if problems:
        draft.code(*problems)
        draft.at(now + policy.follow_up)
        clock_events = tuple(event.event_id for event in events.of_kind(WakeKind.clock_unhealthy))
        return draft.done(HeartbeatAction.RECOVER, SilenceReason.CLOCK_UNHEALTHY, (), consumed=clock_events)
    if facts.last_evaluated_at is not None and now - facts.last_evaluated_at > policy.catch_up_after:
        draft.code(ReasonCode.CATCHING_UP)
    past_due = _collect_due(draft)
    for event in events.of_kind(WakeKind.task_expired):
        draft.code(ReasonCode.TASK_EXPIRED)
        draft.intent(IntentKind.RECOVER_TASK, event.source_ref, f"recover:{state.pet_id}:task:{event.source_ref}:{event.sequence}")
    operation = _check_operation(draft)
    _check_activity(draft, past_due)
    if draft.intents:
        draft.at(now + policy.follow_up)
        if any(item.kind in RECOVERY_INTENTS for item in draft.intents):
            silence = SilenceReason.TASK_STUCK if STUCK_CODES & set(draft.codes) else SilenceReason.STATE_INCONSISTENT
            return draft.done(HeartbeatAction.RECOVER, silence, WAIT_AFTER_ACTION)
        return draft.done(HeartbeatAction.APPLY_RULE, None, WAIT_AFTER_ACTION)
    activity = state.primary_activity  # 走到这里一定已知（未知时上面已交出对账意图）
    if activity.kind == "not_activated":
        draft.code(ReasonCode.NOT_ACTIVATED)
        return draft.done(HeartbeatAction.CONTINUE, SilenceReason.NOT_ACTIVATED, WAIT_AFTER_ACTION)
    if activity.kind in ONGOING or activity.ends_at is not None:
        draft.code(ReasonCode.IN_ACTIVITY)
        if WakeKind.suggestion_received in events.kinds:
            draft.code(ReasonCode.SUGGESTION_NOTED)
        return draft.done(HeartbeatAction.CONTINUE, SilenceReason.LIVING, WAIT_ACTIVITY)
    return _idle(draft, operation)


def evaluate_all(states: Iterable[RuntimeState], events: Iterable[WakeEvent], policy: HeartbeatPolicy, now: datetime, *,
                 facts: Mapping[str, HeartbeatFacts] | None = None, clock_health: ClockHealth | None = None) -> dict[str, HeartbeatDecision]:
    """一轮评估多只宠物。一只宠物只能有一份状态：pet_id 重复直接报错，不要按家人把同一只宠物复制成几份。事件按 pet_id 分发。"""
    by_pet: dict[str, list[WakeEvent]] = {}
    for event in events:
        by_pet.setdefault(event.pet_id, []).append(event)
    decisions: dict[str, HeartbeatDecision] = {}
    for state in states:
        if state.pet_id in decisions:
            raise ValueError(f"宠物 {state.pet_id} 出现了多份运行状态：一只宠物只能有一份，不要按家人复制")
        decisions[state.pet_id] = evaluate(state, by_pet.get(state.pet_id, ()), policy, now, facts=(facts or {}).get(state.pet_id),
                                           clock_health=clock_health)
    return decisions


def next_review_at(decided_at: datetime, policy: HeartbeatPolicy, suggested_after_seconds: float | None = None) -> datetime:
    """一次生活决定（大脑或规则）提交后的下次自主复查时刻，集成层写进 AutonomyFacts.next_review_at。

    有大脑建议（BrainProposal.suggested_review_after_seconds）就用建议值，夹在 [min_decision_interval, max_review_interval]；
    没有建议就用 idle_review_interval。
    """
    decided_at = ensure_utc(decided_at, "decided_at")
    if suggested_after_seconds is None:
        return decided_at + policy.idle_review_interval
    delay = timedelta(seconds=suggested_after_seconds)
    return decided_at + min(max(delay, policy.min_decision_interval), policy.max_review_interval)


@dataclass(frozen=True, slots=True)
class RetryPlan:
    """一次没想成之后的两个时刻，用途不同，不能互相顶替。

    not_before：最早允许再发起一次**可能付费**的尝试。外部给的硬性恢复时刻（额度账本的 retry_after、供应商的 Retry-After）原样保留，
      不被复查上限截短——额度要等 20 小时就是 20 小时。
    check_at：下一次**只读复查**的时刻，不超过 max_review_interval。到点只重新读一遍事实：条件没变就继续安静，
      既不调用模型，也不把 not_before 提前。
    """

    not_before: datetime
    check_at: datetime

    def allows(self, now: datetime) -> bool:
        """此刻是否已经可以再尝试一次（只看硬性下限；真正是否调用还要看当时的额度与可用性事实）。"""
        return ensure_utc(now, "now") >= self.not_before


def retry_plan(now: datetime, policy: HeartbeatPolicy, *, dependency: bool = False, retry_after: datetime | None = None) -> RetryPlan:
    """这次没想成之后的重试安排（集成层把 check_at 写进 AutonomyFacts.next_review_at，把 not_before 记成禁调下限）。

    - 依赖故障（模型超时、报错、截止期限过了）按 dependency_recheck；其余（额度不足、没有可行机会、提案失效）按 min_decision_interval；
    - 额度账本或供应商给了恢复时刻就按它算 not_before，不再按固定间隔空转重试；
    - check_at 仍然受 max_review_interval 约束：到点看一眼状态即可。
    额度被调高、依赖提前恢复这类“事实变了”的情况，由复查时读到的最新事实决定（心跳的大脑可用性判断读的是投影出来的
    额度与可用性，不是这里的时刻）；not_before 只是下限，不是许可。
    退避只推迟“再想一次”，不推迟到期承诺与确定性结算——那两件由到期事项驱动，与这里无关。
    """
    now = ensure_utc(now, "now")
    not_before = now + (policy.dependency_recheck if dependency else policy.min_decision_interval)
    if retry_after is not None and ensure_utc(retry_after, "retry_after") > not_before:
        not_before = ensure_utc(retry_after, "retry_after")
    return RetryPlan(not_before=not_before, check_at=min(not_before, now + policy.max_review_interval))


def _validate(state: RuntimeState) -> None:
    if not state.pet_id:
        raise ValueError("RuntimeState.pet_id 不能为空")
    stamps = [("as_of", state.as_of), ("next_check_at", state.next_check_at), ("pending_commitment_deadline", state.pending_commitment_deadline)]
    if state.primary_activity is not None:
        stamps += [("primary_activity.started_at", state.primary_activity.started_at), ("primary_activity.ends_at", state.primary_activity.ends_at)]
    for name, value in stamps:
        if value is not None:
            ensure_utc(value, name)


def _note_events(draft: _Draft) -> None:
    events = draft.events
    if events.foreign:
        draft.code(ReasonCode.FOREIGN_EVENTS)
    if events.duplicates:
        draft.code(ReasonCode.DUPLICATE_EVENTS)
    if events.pending:
        draft.code(ReasonCode.FUTURE_EVENTS)
        draft.at(*(ensure_utc(event.effective_at) for event in events.pending))
    if WakeKind.message_received in events.kinds:
        draft.code(ReasonCode.MESSAGE_RECEIVED)
    if WakeKind.versions_changed in events.kinds:
        draft.code(ReasonCode.VERSIONS_CHANGED)


def _clock_problems(draft: _Draft, clock_health: ClockHealth | None) -> list[ReasonCode]:
    tolerance, now = draft.policy.clock_tolerance, draft.now
    problems: list[ReasonCode] = []
    if clock_health is not None and clock_health.status is not ClockHealthStatus.OK:
        problems.append(ReasonCode.CLOCK_JUMPED if clock_health.status is ClockHealthStatus.JUMPED else ReasonCode.CLOCK_REGRESSED)
    last = draft.facts.last_evaluated_at
    if (last is not None and now < last - tolerance) or draft.state.as_of > now + tolerance:
        problems.append(ReasonCode.CLOCK_REGRESSED)
    if WakeKind.clock_unhealthy in draft.events.kinds:
        problems.append(ReasonCode.CLOCK_EVENT)
    return problems


def _collect_due(draft: _Draft) -> bool:
    """到期事项 → 结算或兑现意图（承诺优先）；还没到的记为候选检查时刻。返回是否有事项已过到期时间（包括正在退避的）。"""
    state, policy, now = draft.state, draft.policy, draft.now
    current = state.versions.itinerary_version
    ready: list[DueItem] = []
    past_due = False
    for item in draft.facts.due_items:
        past_due = past_due or item.due_at <= now
        ready_at = item.due_at if item.retry_after is None else max(item.due_at, item.retry_after)
        if ready_at > now:
            draft.at(ready_at)
        elif item.itinerary_version is not None and current is not None and item.itinerary_version != current:
            draft.code(ReasonCode.STALE_DUE_ITEM)
            draft.intent(IntentKind.RECONCILE, item.ref, f"reconcile:{state.pet_id}:{item.ref}:itinerary:{item.itinerary_version}->{current}")
        elif item.attempts >= policy.max_due_attempts:
            draft.code(ReasonCode.DUE_ITEM_STUCK)
            draft.intent(IntentKind.RECOVER_TASK, item.ref, f"recover:{state.pet_id}:{item.ref}:{_stamp(item.due_at)}")
        else:
            ready.append(item)
    ready.sort(key=lambda item: (not item.commitment, ensure_utc(item.due_at), item.ref))
    for item in ready[:policy.max_intents]:
        kind = IntentKind.DELIVER_REPLY if item.kind == DueKind.REPLY else IntentKind.SETTLE_DUE
        draft.code(ReasonCode.DUE_COMMITMENT if item.commitment else ReasonCode.DUE_WORLD_EVENT)
        if item.commitment and item.deadline_at is not None and item.deadline_at < now:
            draft.code(ReasonCode.COMMITMENT_OVERDUE)
        key = f"{kind.value}:{state.pet_id}:{item.ref}:{_stamp(item.due_at)}"
        if item.input_high_watermark is not None:
            key += f":{item.input_high_watermark}"
        draft.intent(kind, item.ref, key, item.deadline_at)
    if len(ready) > policy.max_intents:
        draft.code(ReasonCode.MORE_DUE_ITEMS)  # 剩下的在集成层提交后下一轮接着交出（不安排零延迟复查）
    return past_due


def _stamp(value: datetime) -> str:
    return ensure_utc(value).strftime("%Y%m%dT%H%M%SZ")


def _check_operation(draft: _Draft) -> InFlightBrain | None:
    """进行中的认知操作：超过截止交给恢复；依据的版本变了就作废；仍有效则返回它，本次不再重复请求。"""
    operation = draft.facts.cognition.operation
    if operation is None:
        return None
    pet_id, ref = draft.state.pet_id, f"brain:{operation.operation_id}"
    if operation.deadline_at <= draft.now:
        draft.code(ReasonCode.BRAIN_EXPIRED)
        draft.intent(IntentKind.RECOVER_TASK, ref, f"recover:{pet_id}:{ref}")
        return None
    stale = operation.source_versions.stale_fields(draft.state.versions)
    if stale:
        draft.code(ReasonCode.BRAIN_STALE, *(f"{ReasonCode.BRAIN_STALE.value}:{name}" for name in stale))
        draft.intent(IntentKind.CANCEL_BRAIN, ref, f"cancel:{pet_id}:{ref}")
        return None
    draft.at(operation.deadline_at)
    return operation


def _check_activity(draft: _Draft, past_due: bool) -> None:
    """主活动未知，或早该结束却没有到期事项在处理：对账。还没结束的活动把结束时刻记为候选检查时刻。"""
    state, policy, now = draft.state, draft.policy, draft.now
    activity, epoch = state.primary_activity, state.versions.activity_epoch
    if activity is None or activity.kind == "unknown":
        draft.code(ReasonCode.ACTIVITY_UNKNOWN)
        draft.intent(IntentKind.RECONCILE, f"pet:{state.pet_id}", f"reconcile:{state.pet_id}:activity:{epoch}")
        return
    if activity.ends_at is None or activity.kind == "not_activated":
        return
    if activity.ends_at > now:
        draft.at(activity.ends_at)
    elif not past_due and now - activity.ends_at <= policy.activity_grace:
        draft.at(activity.ends_at + policy.activity_grace)
    elif not past_due:
        draft.code(ReasonCode.ACTIVITY_OVERDUE)
        draft.intent(IntentKind.RECONCILE, activity.ref or f"pet:{state.pet_id}", f"reconcile:{state.pet_id}:activity:{epoch}")


def _idle(draft: _Draft, operation: InFlightBrain | None) -> HeartbeatDecision:
    state, policy, now = draft.state, draft.policy, draft.now
    zone = resolve_zone(state.timezone)
    if zone is None:
        draft.code(ReasonCode.TIMEZONE_UNKNOWN)
        draft.at(now + policy.dependency_recheck)
        return draft.done(HeartbeatAction.RECOVER, SilenceReason.TIMEZONE_UNKNOWN, WAIT_QUIET)
    local = local_wall(now, zone).time()
    if state.sleep_window is None:
        draft.code(ReasonCode.DEFAULT_RHYTHM)
    sleep_start, wake = state.sleep_window or policy.default_sleep_window
    if in_local_window(local, sleep_start, wake):
        draft.code(ReasonCode.ASLEEP)
        draft.at(next_local_occurrence(now, zone, wake))
        return draft.done(HeartbeatAction.CONTINUE, SilenceReason.ASLEEP, WAIT_IDLE)
    if operation is not None:
        draft.code(ReasonCode.BRAIN_IN_FLIGHT)
        return draft.done(HeartbeatAction.CONTINUE, SilenceReason.THINKING, WAIT_IDLE)
    autonomy = draft.facts.autonomy
    start, end = autonomy.active_window
    if not in_local_window(local, start, end):
        draft.code(ReasonCode.OUTSIDE_ACTIVE_HOURS)
        draft.at(next_local_occurrence(now, zone, start))
        return draft.done(HeartbeatAction.CONTINUE, SilenceReason.OUTSIDE_ACTIVE_HOURS, WAIT_IDLE)
    if autonomy.outings_today >= autonomy.outings_per_day:
        draft.code(ReasonCode.ENOUGH_TODAY)
        draft.at(next_local_occurrence(now, zone, start))
        return draft.done(HeartbeatAction.CONTINUE, SilenceReason.ENOUGH_TODAY, WAIT_IDLE)
    triggers = _review_triggers(draft)
    if not triggers:
        draft.code(ReasonCode.REVIEW_NOT_DUE)
        draft.at(autonomy.next_review_at)
        return draft.done(HeartbeatAction.CONTINUE, SilenceReason.NO_NEW_DECISION, WAIT_IDLE)
    draft.code(*triggers)
    ready_at = _decision_ready_at(draft)
    if ready_at is not None and ready_at > now:
        draft.code(ReasonCode.DECISION_INTERVAL)
        draft.at(ready_at)
        return draft.done(HeartbeatAction.CONTINUE, SilenceReason.NO_NEW_DECISION, WAIT_IDLE)
    return _decide(draft)


def _review_triggers(draft: _Draft) -> list[ReasonCode]:
    autonomy, now, kinds = draft.facts.autonomy, draft.now, draft.events.kinds
    triggers: list[ReasonCode] = []
    if autonomy.next_review_at is None or autonomy.next_review_at <= now:
        triggers.append(ReasonCode.IDLE_REVIEW)
    suggested = autonomy.latest_suggestion_at
    new_suggestion = suggested is not None and (autonomy.last_decision_at is None or suggested > autonomy.last_decision_at)
    if new_suggestion or WakeKind.suggestion_received in kinds:
        triggers.append(ReasonCode.OWNER_SUGGESTION)
    if WakeKind.activity_due in kinds:
        triggers.append(ReasonCode.ACTIVITY_ENDED)
    return triggers


def _decision_ready_at(draft: _Draft) -> datetime | None:
    """离上一次生活决定（或上一次请求大脑）至少隔 min_decision_interval；多位家人的建议也不能把决定次数叠加上去。"""
    marks = [value for value in (draft.facts.autonomy.last_decision_at, draft.facts.cognition.last_requested_at) if value is not None]
    return max(marks) + draft.policy.min_decision_interval if marks else None


def _decide(draft: _Draft) -> HeartbeatDecision:
    """该做生活决定了：大脑可用就请求大脑；否则按策略用 DNA 规则生活，或者延期。"""
    state, policy, now = draft.state, draft.policy, draft.now
    blocked = _brain_blocked(draft)
    if blocked is None:
        deadline = now + policy.brain_deadline
        draft.intent(IntentKind.BRAIN_DECIDE, f"pet:{state.pet_id}", _slot_key("brain", draft), deadline)
        draft.at(deadline)
        return draft.done(HeartbeatAction.REQUEST_BRAIN, None, WAIT_IDLE, purpose="life_plan")
    code, silence, retry_at = blocked
    draft.code(code)
    if policy.brain_fallback == "rule" or code is ReasonCode.RESIDENT_RULE_LIFE:
        draft.code(ReasonCode.RULE_FALLBACK)
        draft.intent(IntentKind.RULE_LIFE_PLAN, f"pet:{state.pet_id}", _slot_key("rule_life", draft))
        draft.at(now + policy.follow_up)
        if silence is SilenceReason.DEPENDENCY_UNAVAILABLE:
            # **依赖坏了要说出来**：额度账本读不出、模型服务不可用时，退回规则生活之后，
            # 这只宠物看上去和健康的宠物一模一样，运维就分不清“正常安静”和“故障安静”了。
            # 同时允许被“依赖恢复 / 额度恢复”叫醒，不必干等到下一次固定复查。
            return draft.done(HeartbeatAction.APPLY_RULE, silence, WAIT_IDLE)
        return draft.done(HeartbeatAction.APPLY_RULE, None, WAIT_AFTER_ACTION)
    draft.at(retry_at if retry_at is not None and retry_at > now else now + policy.dependency_recheck)
    return draft.done(HeartbeatAction.DEFER, silence, WAIT_IDLE)


def _brain_blocked(draft: _Draft) -> tuple[ReasonCode, SilenceReason, datetime | None] | None:
    """大脑此刻不能用的原因：(原因码, 安静原因, 最早可再试的时刻)；可以用返回 None。"""
    state, cognition, policy, now = draft.state, draft.facts.cognition, draft.policy, draft.now
    if state.household_id is None and not policy.resident_brain:
        return ReasonCode.RESIDENT_RULE_LIFE, SilenceReason.NO_NEW_DECISION, None
    if not cognition.enabled or cognition.availability == BrainAvailability.DISABLED:
        return ReasonCode.BRAIN_DISABLED, SilenceReason.NO_NEW_DECISION, now + policy.idle_review_interval
    if cognition.availability == BrainAvailability.EXHAUSTED or (cognition.remaining_today is not None and cognition.remaining_today <= 0):
        resets = [value for value in (cognition.window_resets_at, cognition.retry_after) if value is not None]
        upcoming = [value for value in resets if value > now]
        if upcoming or not resets:  # 已知的重置时刻都过去了：投影可能过时，交给额度预占去判断
            return ReasonCode.BRAIN_EXHAUSTED, SilenceReason.BUDGET_DEFERRED, min(upcoming, default=None)
    if cognition.availability == BrainAvailability.UNAVAILABLE and (cognition.retry_after is None or cognition.retry_after > now):
        return ReasonCode.BRAIN_UNAVAILABLE, SilenceReason.DEPENDENCY_UNAVAILABLE, cognition.retry_after
    return None


def _slot_key(prefix: str, draft: _Draft) -> str:
    """同一只宠物、同一组语义版本、同一个决定时段只登记一次（集成层按 dedupe_key 去重）。"""
    versions = draft.state.versions
    slot = int(draft.now.timestamp() // draft.policy.min_decision_interval.total_seconds())
    return (f"{prefix}:{draft.state.pet_id}:{versions.runtime_epoch}.{versions.activity_epoch}.{versions.dna_version}."
            f"{versions.privacy_epoch}.{versions.membership_epoch}:{slot}")
