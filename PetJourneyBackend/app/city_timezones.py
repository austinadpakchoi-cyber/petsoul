"""城市 → IANA 时区映射与本地墙上时间换算。

世界快照的 `local_time` 表示「TA 所在地的当地时间」（墙上时间），用于 iOS 地图
昼夜相位——地图天色必须跟着 TA 走，而不是主人的设备时区（UI/UX 审计 P0-2）。
`local_time` 以无时区偏移的 ISO 串下发（墙上时间本身），iOS 侧按 GMT 解析后
直接取小时/分钟分量，两端都不再做设备时区换算。
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

CITY_TIMEZONES: dict[str, str] = {
    "厦门": "Asia/Shanghai",
    "京都": "Asia/Tokyo",
    "雷克雅未克": "Atlantic/Reykjavik",
    "洛杉矶": "America/Los_Angeles",
    "多伦多": "America/Toronto",
    "墨西哥城": "America/Mexico_City",
    "纽约": "America/New_York",
}

FALLBACK_TIMEZONE = "Asia/Shanghai"


def timezone_for_city(city_name: str | None) -> str:
    if city_name and city_name in CITY_TIMEZONES:
        return CITY_TIMEZONES[city_name]
    return FALLBACK_TIMEZONE


def local_wall_time(now: datetime, city_name: str | None) -> datetime:
    """把 UTC 时刻换算成城市当地墙上时间（naive datetime，表示墙上时间本身）。"""
    try:
        localized = now.astimezone(ZoneInfo(timezone_for_city(city_name)))
    except Exception:
        localized = now.astimezone(ZoneInfo(FALLBACK_TIMEZONE))
    return localized.replace(tzinfo=None)
