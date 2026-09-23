"""心跳结论的词表：任务意图种类、原因码、安静原因（包 B）。

共享 HeartbeatDecision（runtime-internal 0.1.0）里 reason_codes 是字符串元组，TaskIntent.kind 是字符串。
这里固定取值，集成层、运维与独立验收都按这些常量判断，不解析自由文本。
- 安静原因写成 "silence:<原因>" 放进 reason_codes：共享类型里还没有单独字段，已在 fed3 日志提 CHANGE_REQUEST；
- 少数原因码带细节后缀，例如 "brain_stale:dna_version"，前缀仍是下面的常量。
"""

from __future__ import annotations

from enum import Enum

from ..schemas.runtime_internal import HeartbeatDecision

SILENCE_PREFIX = "silence:"


class IntentKind(str, Enum):
    """TaskIntent.kind 的取值。意图由集成层在同一事务里入队（按 dedupe_key 去重），心跳本身不执行。"""

    SETTLE_DUE = "settle_due"  # 到期事项按确定性规则结算（旅程事件与工钱、冷却结束……）；整段旅程按顺序补齐
    DELIVER_REPLY = "deliver_reply"  # 兑现待回复承诺：按会话，一次合并这段时间的全部消息
    BRAIN_DECIDE = "brain_decide"  # 登记一次认知操作：先经 A 的额度预占，再交给 C；deadline_at 为截止
    RULE_LIFE_PLAN = "rule_life_plan"  # 大脑不可用或不启用时，按 DNA 规则生活做一次决定（如实记为规则，不是模型决策）
    CANCEL_BRAIN = "cancel_brain"  # 依据的版本已变：作废进行中的认知操作，旧结果不能提交
    RECOVER_TASK = "recover_task"  # 任务租约过期、认知操作超时、到期事项连续失败：交给恢复流程
    RECONCILE = "reconcile"  # 投影与事实不一致（活动早该结束却没有到期事项、行程版本对不上、主活动未知）：重新对账


class ReasonCode(str, Enum):
    # 运行环境
    MAINTENANCE = "maintenance"
    CLOCK_REGRESSED = "clock_regressed"
    CLOCK_JUMPED = "clock_jumped"
    CLOCK_EVENT = "clock_event"  # 收到 clock_unhealthy 唤醒事件
    CATCHING_UP = "catching_up"  # 距上次评估已经很久（停机或积压），只补确定性事项，不补写错过的决定
    # 唤醒事件
    MESSAGE_RECEIVED = "message_received"
    VERSIONS_CHANGED = "versions_changed"
    DUPLICATE_EVENTS = "duplicate_events"
    FOREIGN_EVENTS = "foreign_events"
    FUTURE_EVENTS = "future_events"
    # 到期事项与恢复
    DUE_COMMITMENT = "due_commitment"
    DUE_WORLD_EVENT = "due_world_event"
    COMMITMENT_OVERDUE = "commitment_overdue"
    MORE_DUE_ITEMS = "more_due_items"
    DUE_ITEM_STUCK = "due_item_stuck"
    STALE_DUE_ITEM = "stale_due_item"
    TASK_EXPIRED = "task_expired"
    BRAIN_EXPIRED = "brain_expired"
    BRAIN_STALE = "brain_stale"
    BRAIN_IN_FLIGHT = "brain_in_flight"
    ACTIVITY_OVERDUE = "activity_overdue"
    ACTIVITY_UNKNOWN = "activity_unknown"
    # 生活状态
    IN_ACTIVITY = "in_activity"
    SUGGESTION_NOTED = "suggestion_noted"  # 活动进行中收到建议：先记着，活动结束后再考虑
    NOT_ACTIVATED = "not_activated"
    TIMEZONE_UNKNOWN = "timezone_unknown"
    DEFAULT_RHYTHM = "default_rhythm"  # 没有作息信息，按产品默认作息
    ASLEEP = "asleep"
    OUTSIDE_ACTIVE_HOURS = "outside_active_hours"
    ENOUGH_TODAY = "enough_today"
    REVIEW_NOT_DUE = "review_not_due"
    DECISION_INTERVAL = "decision_interval"
    # 自主复查的触发
    IDLE_REVIEW = "idle_review"
    OWNER_SUGGESTION = "owner_suggestion"
    ACTIVITY_ENDED = "activity_ended"
    # 大脑可用性
    BRAIN_DISABLED = "brain_disabled"
    BRAIN_EXHAUSTED = "brain_exhausted"
    BRAIN_UNAVAILABLE = "brain_unavailable"
    RESIDENT_RULE_LIFE = "resident_rule_life"
    RULE_FALLBACK = "rule_fallback"
    # 下次检查只剩看门狗兜底
    WATCHDOG = "watchdog"


class SilenceKind(str, Enum):
    NORMAL = "normal"  # 正在生活：睡觉、在路上、暂时没有新决定……
    DEFERRED = "deferred"  # 有意推迟：额度用完、管理员维护
    FAULT = "fault"  # 系统问题：依赖不可用、任务卡住、时钟异常、时区未知、数据不一致


class SilenceReason(str, Enum):
    LIVING = "living"
    ASLEEP = "asleep"
    OUTSIDE_ACTIVE_HOURS = "outside_active_hours"
    ENOUGH_TODAY = "enough_today"
    NO_NEW_DECISION = "no_new_decision"
    THINKING = "thinking"
    NOT_ACTIVATED = "not_activated"
    BUDGET_DEFERRED = "budget_deferred"
    MAINTENANCE = "maintenance"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    TASK_STUCK = "task_stuck"
    CLOCK_UNHEALTHY = "clock_unhealthy"
    TIMEZONE_UNKNOWN = "timezone_unknown"
    STATE_INCONSISTENT = "state_inconsistent"

    @property
    def kind(self) -> SilenceKind:
        if self in (SilenceReason.BUDGET_DEFERRED, SilenceReason.MAINTENANCE):
            return SilenceKind.DEFERRED
        if self in (SilenceReason.DEPENDENCY_UNAVAILABLE, SilenceReason.TASK_STUCK, SilenceReason.CLOCK_UNHEALTHY,
                    SilenceReason.TIMEZONE_UNKNOWN, SilenceReason.STATE_INCONSISTENT):
            return SilenceKind.FAULT
        return SilenceKind.NORMAL


def silence_code(reason: SilenceReason) -> str:
    return f"{SILENCE_PREFIX}{reason.value}"


def silence_of(decision: HeartbeatDecision) -> SilenceReason | None:
    """从心跳结论里读出安静原因（集成层据此写 RuntimeState.silence_reason）；在行动、没有安静原因时返回 None。

    0.1.1 起首选 silence_reason 字段；字段为空时再看 reason_codes 里的 "silence:<原因>"（兼容旧结论）。
    """
    field = getattr(decision, "silence_reason", None)
    if field:
        try:
            return SilenceReason(field)
        except ValueError:
            return None
    for code in decision.reason_codes:
        if code.startswith(SILENCE_PREFIX):
            try:
                return SilenceReason(code[len(SILENCE_PREFIX):])
            except ValueError:
                return None
    return None
