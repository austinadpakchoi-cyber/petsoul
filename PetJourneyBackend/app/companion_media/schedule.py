"""途中活动的确定性日程：由交通段起止时间与角色推导，刷新/重启不会随机换歌或改成已看完。

循环（首发配置）：
- 步行/驾驶/出租车：听歌 → 休息；驾驶中永不安排视频；
- 飞机/火车/轮船乘客：听歌 → 看窗外 → 看短片 → 休息（主人确认“安静听歌”偏好时只听歌）；
- 候乘：看窗外（无影音入口）。
活动超出交通段结束时间时，在到站时刻被中断并保存进度——交通不会等播放器。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..schemas.web.companion_media import MediaAsset
from ..schemas.web.transport import TravelActivityKind, TravelActivityState
from .catalog import MUSIC, VIDEO

REST_SECONDS = 180
WALK_REST_SECONDS = 120
LONG_HAUL = {"flight", "train", "ferry"}


@dataclass(frozen=True)
class LegWindow:
    leg_id: str
    kind: str
    mode: str
    role: str
    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True)
class ScheduledActivity:
    activity_id: str
    leg_id: str
    index: int
    kind: TravelActivityKind
    starts_at: datetime
    natural_end: datetime
    leg_end: datetime
    media: MediaAsset | None

    @property
    def session_id(self) -> str | None:
        return f"ms-{self.leg_id}-{self.index}" if self.media else None

    @property
    def truncated(self) -> bool:
        return self.natural_end > self.leg_end

    @property
    def ends_at(self) -> datetime:
        return min(self.natural_end, self.leg_end)

    def state_at(self, now: datetime) -> TravelActivityState:
        if now < self.ends_at:
            return TravelActivityState.active
        return TravelActivityState.interrupted if self.truncated and self.media else TravelActivityState.ended


def _pattern(window: LegWindow, quiet: bool) -> list[tuple[TravelActivityKind, int, MediaAsset | None]]:
    if window.kind == "wait":
        return [(TravelActivityKind.window_gazing, 600, None)]
    music = (TravelActivityKind.listening, MUSIC.duration_ms // 1000, MUSIC)
    if window.role == "driver" or window.mode not in LONG_HAUL or quiet:
        rest = WALK_REST_SECONDS if window.mode == "walk" else REST_SECONDS
        return [music, (TravelActivityKind.resting, rest, None)]
    return [
        music,
        (TravelActivityKind.window_gazing, REST_SECONDS, None),
        (TravelActivityKind.watching, VIDEO.duration_ms // 1000, VIDEO),
        (TravelActivityKind.resting, REST_SECONDS, None),
    ]


def activity_at(window: LegWindow, when: datetime, quiet: bool = False) -> ScheduledActivity | None:
    """when 所在的活动；when 不在交通段内返回 None。"""
    if when < window.starts_at or when >= window.ends_at:
        return None
    pattern = _pattern(window, quiet)
    cycle = sum(seconds for _, seconds, _ in pattern)
    elapsed = int((when - window.starts_at).total_seconds())
    cycle_index, offset = divmod(elapsed, cycle)
    cursor = 0
    for position, (kind, seconds, media) in enumerate(pattern):
        if offset < cursor + seconds:
            index = cycle_index * len(pattern) + position
            start = window.starts_at + timedelta(seconds=cycle_index * cycle + cursor)
            return ScheduledActivity(
                activity_id=f"{window.leg_id}:a{index}",
                leg_id=window.leg_id,
                index=index,
                kind=kind,
                starts_at=start,
                natural_end=start + timedelta(seconds=seconds),
                leg_end=window.ends_at,
                media=media,
            )
        cursor += seconds
    return None


def last_media_activity(window: LegWindow, quiet: bool = False) -> ScheduledActivity | None:
    """交通段最后一个影音活动（用于到站后显示“已保存进度”）。"""
    probe = window.ends_at - timedelta(seconds=1)
    for _ in range(8):
        activity = activity_at(window, probe, quiet)
        if activity is None:
            return None
        if activity.media is not None:
            return activity
        probe = activity.starts_at - timedelta(seconds=1)
    return None


def activity_by_index(window: LegWindow, index: int, quiet: bool = False) -> ScheduledActivity | None:
    pattern = _pattern(window, quiet)
    cycle = sum(seconds for _, seconds, _ in pattern)
    cycle_index, position = divmod(index, len(pattern))
    offset = cycle_index * cycle + sum(seconds for _, seconds, _ in pattern[:position])
    return activity_at(window, window.starts_at + timedelta(seconds=offset), quiet)
