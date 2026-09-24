"""每天生成了多少张图（用户经 P 窗口转达的需求；平台成本的一部分）。只读。

数据只来自额度账 `web_budget_reservations`（provider='image'），按记账日与用途分组。
- **记账日**：额度按 UTC 记账日计（北京时间 08:00 换日），与额度计数器同一口径；个别按并发上限记的行没有日期（`inflight`），按它创建时刻的 UTC 日期归日。
- **每一格同时给两个数，不混成一个**：调用行数（发起了几次）与计入用量（metering 的 `COUNTED_UNITS_SQL`：没发出的计 0、在途不计）。
- **结果分类**按 status / outcome 合起来看：出图了（settled+succeeded）、发出去了没画成（settled+failed）、没发出（released，额度退回）、
  结果未确认（unknown / expired）、还在路上（reserved）。
- 上限取运行配置的现值（全站每天、每只宠物每个用途每天），后台只显示、不改。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from ..storage import JourneyStorage
from .metering import COUNTED_UNITS_SQL

DAYS = 30
# 至少这几列总在：没有调用的那天也看得出「角色形象 0、证件照 0、插画 0」，而不是少一列
# （证件照 web_character/id_photo.py 走自己的每宠车道 pet:<宠物>:id_photo，与角色同一个上限、单独计数）
BASE_PURPOSES = ("character", "id_photo", "illustration")


def _bucket(status: str, outcome: str | None) -> str:
    if status == "reserved":
        return "inflight"
    if status == "released":
        return "not_sent"
    if status in ("unknown", "expired"):
        return "unknown"
    return "failed" if outcome == "failed" else "ok"


def image_days(storage: JourneyStorage, settings, now: datetime, days: int = DAYS) -> dict[str, Any]:
    today = now.date()
    since = (today - timedelta(days=days - 1)).isoformat()
    day_sql = "CASE WHEN accounting_window = 'inflight' THEN substr(created_at, 1, 10) ELSE accounting_window END"
    try:
        with storage.connect() as conn:
            rows = conn.execute(
                f"SELECT {day_sql} AS day, purpose, status, outcome, COUNT(*) AS calls, SUM({COUNTED_UNITS_SQL}) AS units "
                f"FROM web_budget_reservations WHERE provider = 'image' AND {day_sql} >= ? "
                "GROUP BY day, purpose, status, outcome", (since,)).fetchall()
            counters = {r["window_key"]: {"used": int(r["used_units"]), "inflight": int(r["inflight_units"])} for r in conn.execute(
                "SELECT window_key, used_units, inflight_units FROM web_budget_counters WHERE scope_key = 'provider:image:daily' "
                "AND window_key >= ?", (since,))}
    except sqlite3.OperationalError:
        return {"days": None, "note": "这个库里还没有额度账，查不了（不等于没有）。"}

    by_day: dict[str, dict[str, Any]] = {}
    purposes = set(BASE_PURPOSES)
    for row in rows:
        day = by_day.setdefault(row["day"], {"day": row["day"], "purposes": {}, "total": {"calls": 0, "units": 0}})
        cell = day["purposes"].setdefault(row["purpose"], {"calls": 0, "units": 0, "buckets": {}})
        bucket = _bucket(row["status"], row["outcome"])
        calls, units = int(row["calls"]), int(row["units"] or 0)
        cell["buckets"][bucket] = cell["buckets"].get(bucket, 0) + calls
        cell["calls"] += calls
        cell["units"] += units
        day["total"]["calls"] += calls
        day["total"]["units"] += units
        purposes.add(row["purpose"])
    today_key = today.isoformat()
    by_day.setdefault(today_key, {"day": today_key, "purposes": {}, "total": {"calls": 0, "units": 0}})
    for key, day in by_day.items():
        day["global_counter"] = counters.get(key)  # 全站计数器这一天记下的已用与在途；没有就是 None（那天没有计数）
    ordered = sorted(by_day.values(), key=lambda d: d["day"], reverse=True)
    return {
        "days": ordered,
        "purposes": sorted(purposes, key=lambda p: (p not in BASE_PURPOSES, p)),
        "caps": {"global_daily": int(getattr(settings, "web_image_daily_cap", 0)),
                 "per_pet_daily": int(getattr(settings, "web_image_per_pet_daily_cap", 0))},
        "since": since, "today": today_key,
        "note": ("按 UTC 记账日（北京时间 08:00 换日）。只列有调用的日子，外加今天。"
                 "「调用」是发起了几次，「计入」是计进额度的张数（没发出的计 0、在途的还没计）；两个数分开看，不混成一个。"),
    }
