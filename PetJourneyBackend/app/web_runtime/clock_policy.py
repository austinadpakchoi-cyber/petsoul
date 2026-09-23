"""时钟与地区钟点（工作包 B）。

三种时间不混用（世界运行方案 v0.2 §5.1）：
- UTC 时刻：到期、结算、记录。一律带时区；拿到不带时区的时间直接报错，不猜。
- 地区日历时间：TA 所在地的作息与日期。只接受 IANA 时区名（集成层按“TA 此刻在哪”给出）；认不出就返回 None，
  由调用方给出明确的不可用结果。这里不回退香港或上海：moment._zone 与 city_timezones 的默认值只适合展示，不能用来做运行判断。
- 单调时钟：进程内耗时与校时检测，不写库，不跨进程比较。

生产用 SystemClock，测试注入 FakeClock（都实现 app.schemas.runtime_internal.Clock）；正式时钟不加速。
FakeClock 与 tests/web_base.py 里替换 utils.utcnow 的同名测试工具用途不同，这里的是给运行层用的 Clock 实现。
ClockMonitor 用单调时钟核对墙上时钟：发现回拨或大幅前跳后一直报异常，直到墙上时钟回到推算值附近，或运维核对校时后调用 reanchor()。
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..schemas.runtime_internal import Clock

UTC = timezone.utc


def ensure_utc(value: datetime, name: str = "time") -> datetime:
    """带时区的时刻 → UTC；不带时区的直接报错（不按宿主机时区猜）。"""
    if not isinstance(value, datetime):
        raise TypeError(f"{name} 必须是 datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} 必须带时区（UTC）")
    return value.astimezone(UTC)


class SystemClock:
    """生产时钟：真实 UTC 与单调时钟。"""

    def now_utc(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return _time.monotonic()


class FakeClock:
    """测试时钟：手动推进。advance 同时推进墙上时钟与单调时钟；jump_wall 只动墙上时钟，用来模拟校时回拨或跳变。"""

    def __init__(self, start: datetime, monotonic_start: float = 1000.0) -> None:
        self._now = ensure_utc(start, "start")
        self._monotonic = float(monotonic_start)

    def now_utc(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._monotonic

    def advance(self, delta: timedelta) -> datetime:
        if delta < timedelta(0):
            raise ValueError("advance 只能向前；模拟回拨请用 jump_wall")
        self._now += delta
        self._monotonic += delta.total_seconds()
        return self._now

    def jump_wall(self, delta: timedelta) -> datetime:
        self._now += delta
        return self._now


def resolve_zone(name: str | None) -> ZoneInfo | None:
    """IANA 时区名 → ZoneInfo；为空或认不出返回 None，不回退任何默认城市。"""
    if not name or not isinstance(name, str):
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def local_wall(now_utc: datetime, zone: ZoneInfo) -> datetime:
    """某个 UTC 时刻在该地区的当地时间（带时区）。"""
    return ensure_utc(now_utc, "now_utc").astimezone(zone)


def in_local_window(at: time, start: time, end: time) -> bool:
    """当地钟点是否落在 [start, end)。start > end 表示跨午夜（例如 23:30 睡、07:30 起）；start == end 视为空窗口。"""
    if start == end:
        return False
    if start < end:
        return start <= at < end
    return at >= start or at < end


def _instant(day: date, at: time, zone: ZoneInfo) -> datetime:
    """当地某天某钟点对应的 UTC 时刻。夏令时重复的钟点取第一次；被跳过的钟点顺延到跳变后的第一刻。"""
    wall = datetime.combine(day, at.replace(tzinfo=None))
    first = wall.replace(tzinfo=zone, fold=0).astimezone(UTC)
    if first.astimezone(zone).replace(tzinfo=None) == wall:
        return first
    # 这个钟点被夏令时跳过了：fold=1 按跳变后的偏移换算，落在跳变之前；fold=0 落在跳变之后。
    # 在两者之间按整秒二分，找当地时间第一次不早于该钟点的时刻（也就是跳变那一刻）。
    low = int(wall.replace(tzinfo=zone, fold=1).astimezone(UTC).timestamp())
    high = int(first.timestamp())
    low, high = min(low, high), max(low, high)
    while high - low > 1:
        middle = (low + high) // 2
        if datetime.fromtimestamp(middle, UTC).astimezone(zone).replace(tzinfo=None) >= wall:
            high = middle
        else:
            low = middle
    return datetime.fromtimestamp(high, UTC)


def next_local_occurrence(now_utc: datetime, zone: ZoneInfo, at: time) -> datetime:
    """严格晚于 now 的下一个当地 at 钟点，返回 UTC。跨午夜、夏令时都按当地日历计算。"""
    now_utc = ensure_utc(now_utc, "now_utc")
    today = now_utc.astimezone(zone).date()
    for offset in range(3):
        instant = _instant(today + timedelta(days=offset), at, zone)
        if instant > now_utc:
            return instant
    return _instant(today + timedelta(days=3), at, zone)


class ClockHealthStatus(str, Enum):
    OK = "ok"
    REGRESSED = "regressed"  # 墙上时钟比单调时钟推算的时刻早：被回拨
    JUMPED = "jumped"  # 墙上时钟比推算的时刻晚得多：大幅前跳


@dataclass(frozen=True, slots=True)
class ClockHealth:
    status: ClockHealthStatus = ClockHealthStatus.OK
    skew_seconds: float = 0.0  # 墙上时钟减推算时刻；正数为前跳，负数为回拨


@dataclass(frozen=True, slots=True)
class ClockReading:
    now_utc: datetime
    monotonic: float
    health: ClockHealth


class ClockMonitor:
    """同一进程内，两次读数的墙上时间差应当约等于单调时钟差。

    偏差在容忍度内：视为正常，并把参照点挪到这次读数（吸收小幅校时漂移）。
    超出容忍度：判为回拨或前跳，参照点不动，所以之后一直报异常，直到墙上时钟回到推算值附近，或运维核对后 reanchor()。
    进程重启后的第一次读数没有参照，按正常处理；跨重启的长时间停机属于正常补齐，由心跳按上次评估时刻识别。
    注意：Linux 的单调时钟不计入系统挂起时间，笔记本合盖恢复后会被判为前跳；服务器上一般不会出现。
    """

    def __init__(self, tolerance: timedelta = timedelta(seconds=30)) -> None:
        if tolerance <= timedelta(0):
            raise ValueError("tolerance 必须大于 0")
        self._tolerance = tolerance.total_seconds()
        self._anchor: tuple[datetime, float] | None = None

    def sample(self, clock: Clock) -> ClockReading:
        wall = ensure_utc(clock.now_utc(), "clock.now_utc()")
        mono = clock.monotonic()
        if self._anchor is None:
            self._anchor = (wall, mono)
            return ClockReading(wall, mono, ClockHealth())
        anchor_wall, anchor_mono = self._anchor
        skew = (wall - anchor_wall).total_seconds() - (mono - anchor_mono)
        if abs(skew) <= self._tolerance:
            self._anchor = (wall, mono)
            return ClockReading(wall, mono, ClockHealth())
        status = ClockHealthStatus.JUMPED if skew > 0 else ClockHealthStatus.REGRESSED
        return ClockReading(wall, mono, ClockHealth(status, round(skew, 3)))

    def reanchor(self, clock: Clock) -> None:
        """运维核对校时之后，以当前墙上时钟为准重新建立参照。"""
        self._anchor = (ensure_utc(clock.now_utc(), "clock.now_utc()"), clock.monotonic())
