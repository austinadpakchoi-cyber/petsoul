"""已核验时刻表快照（web_transport/timetables/*.json）：按服务日期展开成一次次开航。

- 快照记下官网网址、抓取时间、原始页面摘要、生效声明与核验人；recheck_by 之后视为“待复核”，正式路径不再当作已核验使用；
- 时刻是出发港当地时间（IANA 时区），换算成 UTC 保存；航行时长用运营方公布的约数（duration_basis=operator_stated_approx）；
- 票价是现实参考（港币），和星币旅费分开。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from ..utils import parse_dt

ROOT = Path(__file__).resolve().parent / "timetables"
UTC = ZoneInfo("UTC")


@dataclass(frozen=True)
class Sailing:
    timetable_id: str
    direction: str
    service_date: date
    departure_local: str  # HH:MM（出发港当地）
    timezone: str
    departs_at: datetime  # UTC
    arrives_at: datetime  # UTC
    origin_hub: str
    destination_hub: str
    night: bool

    @property
    def reference_id(self) -> str:
        return f"{self.timetable_id}:{self.direction}:{self.service_date.isoformat()}:{self.departure_local}"


@dataclass(frozen=True)
class Timetable:
    timetable_id: str
    mode: str
    operator: str
    service_label: str
    source: dict
    effective_from: date
    effective_to: date | None
    recheck_by: date
    duration_minutes: int
    duration_basis: str
    boarding_buffer_minutes: int
    directions: dict
    reference_fares: dict | None

    def fresh(self, on: date) -> bool:
        """服务日期在生效期内、并且还没过复核期限：可以作为已核验班次使用。"""
        if on < self.effective_from or (self.effective_to is not None and on > self.effective_to):
            return False
        return on <= self.recheck_by

    def sailings(self, direction: str, service_date: date) -> list[Sailing]:
        spec = self.directions[direction]
        zone = ZoneInfo(spec["timezone"])
        night_from = spec.get("night_from")
        result = []
        for hhmm in spec["departures"]:
            hour, minute = (int(v) for v in hhmm.split(":"))
            departs = datetime.combine(service_date, time(hour, minute), tzinfo=zone).astimezone(UTC)
            result.append(Sailing(self.timetable_id, direction, service_date, hhmm, spec["timezone"], departs, departs + timedelta(minutes=self.duration_minutes),
                                  spec["from_hub"], spec["to_hub"], bool(night_from and hhmm >= night_from)))
        return result

    def next_sailing(self, direction: str, not_before: datetime, days: int = 2, not_after: datetime | None = None) -> Sailing | None:
        """不早于 not_before 的最近一班（最多往后看 days 天，可限定最晚出发时间）；跨过午夜时取下一个服务日期的班次。"""
        zone = ZoneInfo(self.directions[direction]["timezone"])
        start = not_before.astimezone(zone).date()
        for offset in range(days + 1):
            day = start + timedelta(days=offset)
            if not self.fresh(day):
                continue
            for sailing in self.sailings(direction, day):
                if sailing.departs_at >= not_before:
                    return None if not_after is not None and sailing.departs_at > not_after else sailing
        return None

    def fare_note(self, sailing: Sailing) -> dict | None:
        """这一班的现实参考票价（经济位，港币）：日间平日 / 日间周末 / 夜航。节假日没有接入日历，如实说明。"""
        if not self.reference_fares:
            return None
        economy = self.reference_fares["classes"]["economy"]
        weekend = sailing.service_date.weekday() >= 5
        band = "night" if sailing.night else ("day_weekend_holiday" if weekend else "day_weekday")
        return {"currency": self.reference_fares["currency"], "class": economy["label"], "amount": economy[band], "band": band,
                "effective_from": self.reference_fares["effective_from"], "holiday_note": "港澳公众假期适用节假日票价，以运营方公布为准",
                "source_url": self.source["url"], "fetched_at": self.source["fetched_at"]}

    def source_label(self) -> str:
        fetched = parse_dt(self.source["fetched_at"]).strftime("%Y-%m-%d")
        return f"{self.operator} 官网船期（{self.effective_from.isoformat()} 起生效，{fetched} 抓取核验）；航行时间为运营方公布的约数"


@lru_cache(maxsize=None)
def load_timetable(name: str) -> Timetable:
    data = json.loads((ROOT / f"{name}.json").read_text(encoding="utf-8"))
    return Timetable(
        timetable_id=data["timetable_id"], mode=data["mode"], operator=data["operator"], service_label=data["service_label"], source=data["source"],
        effective_from=date.fromisoformat(data["effective_from"]), effective_to=date.fromisoformat(data["effective_to"]) if data.get("effective_to") else None,
        recheck_by=date.fromisoformat(data["recheck_by"]), duration_minutes=int(data["duration_minutes"]), duration_basis=data["duration_basis"],
        boarding_buffer_minutes=int(data["boarding_buffer_minutes"]), directions=data["directions"], reference_fares=data.get("reference_fares"),
    )


def timetables() -> dict[str, Timetable]:
    return {path.stem: load_timetable(path.stem) for path in sorted(ROOT.glob("*.json"))}
