"""唤醒事件：去重、合并、判断是否已经生效（包 B）。

事件只带事实类别、生效时间和来源引用，不带正文（runtime-internal 0.1.0 的 WakeEvent）。规则：
- 不属于这只宠物的事件不处理、也不确认消费：集成层路由出错时，不会把别人的事件吞掉；
- 同一 event_id 只算一次；同一 (kind, source_ref) 只留 sequence 最大的一条，其余作为重复一起确认消费；
- 生效时间晚于 now（超过容忍度）的事件还没发生，留到那时再处理，不消费；
- 事件只是“该看一眼了”的信号。承诺、活动、版本这些事实以状态投影为准，事件被消费不等于事实已处理。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from ..schemas.runtime_internal import WakeEvent, WakeKind
from .clock_policy import ensure_utc


@dataclass(frozen=True, slots=True)
class MergedEvents:
    effective: tuple[WakeEvent, ...] = ()  # 已生效、去重后，按 (生效时间, sequence) 排序
    pending: tuple[WakeEvent, ...] = ()  # 还没到生效时间
    consumed_ids: tuple[str, ...] = ()  # 建议确认消费：已生效的，加上被合并掉的重复
    duplicates: int = 0
    foreign: int = 0

    @property
    def kinds(self) -> frozenset[WakeKind]:
        return frozenset(event.kind for event in self.effective)

    def of_kind(self, kind: WakeKind) -> tuple[WakeEvent, ...]:
        return tuple(event for event in self.effective if event.kind is kind)


def _order(event: WakeEvent) -> tuple[datetime, int, str]:
    return ensure_utc(event.effective_at, f"事件 {event.event_id} 的 effective_at"), event.sequence, event.event_id


def merge_events(pet_id: str, events: Iterable[WakeEvent], now: datetime, *, tolerance: timedelta = timedelta(0)) -> MergedEvents:
    now = ensure_utc(now, "now")
    seen: set[str] = set()
    latest: dict[tuple[WakeKind, str], WakeEvent] = {}
    pending: list[WakeEvent] = []
    dropped: list[str] = []
    duplicates = foreign = 0
    for event in events:
        if event.pet_id != pet_id:
            foreign += 1
            continue
        if event.event_id in seen:
            duplicates += 1
            continue
        seen.add(event.event_id)
        event = event if isinstance(event.kind, WakeKind) else _with_kind(event)
        at, sequence, event_id = _order(event)
        if at > now + tolerance:
            pending.append(event)
            continue
        key = (event.kind, event.source_ref)
        current = latest.get(key)
        if current is None:
            latest[key] = event
            continue
        duplicates += 1
        if (sequence, at, event_id) > (current.sequence, _order(current)[0], current.event_id):
            dropped.append(current.event_id)
            latest[key] = event
        else:
            dropped.append(event_id)
    effective = tuple(sorted(latest.values(), key=_order))
    consumed = sorted(set(dropped) | {event.event_id for event in effective})
    return MergedEvents(effective, tuple(sorted(pending, key=_order)), tuple(consumed), duplicates, foreign)


def _with_kind(event: WakeEvent) -> WakeEvent:
    """kind 以字符串传入时换成枚举；认不出的类别直接报错（集成层契约错误，不静默忽略）。"""
    return WakeEvent(event.event_id, event.pet_id, WakeKind(event.kind), event.effective_at, event.source_ref, event.sequence)
