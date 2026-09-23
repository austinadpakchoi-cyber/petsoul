"""把目的地目录展开成门到门时间线（纯函数）。时长按目录设定原样使用，不因下一站或任何原因压缩。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from .catalog import Destination, LegPlan


@dataclass(frozen=True)
class PlannedLeg:
    sequence: int
    direction: str
    plan: LegPlan
    starts_at: datetime
    ends_at: datetime
    route: list[dict]


@dataclass(frozen=True)
class PlannedTimeline:
    legs: list[PlannedLeg]
    visit_starts_at: datetime
    visit_ends_at: datetime
    completes_at: datetime


def route_between(origin: dict, destination: dict, schematic: bool, steps: int = 12) -> list[dict]:
    a = (origin["lat"], origin["lng"])
    b = (destination["lat"], destination["lng"])
    if a == b:
        return [{"lat": a[0], "lng": a[1]}]
    if not schematic:
        # 没有真实道路/航路几何：用起终点直线加一个轻微折点，页面标“示意/模拟线路位置”。
        mid = {"lat": (a[0] + b[0]) / 2 + (b[1] - a[1]) * 0.08, "lng": (a[1] + b[1]) / 2 - (b[0] - a[0]) * 0.08}
        return [{"lat": a[0], "lng": a[1]}, mid, {"lat": b[0], "lng": b[1]}]
    distance = math.hypot(b[0] - a[0], b[1] - a[1])
    bulge = min(6.0, distance * 0.15)
    return [
        {"lat": a[0] + (b[0] - a[0]) * t + math.sin(math.pi * t) * bulge, "lng": a[1] + (b[1] - a[1]) * t}
        for t in (i / steps for i in range(steps + 1))
    ]


def plan_timeline(destination: Destination, departed_at: datetime, route_overrides: dict[tuple[str, int], list[dict]] | None = None) -> PlannedTimeline:
    """route_overrides：(方向, 段序号) → 真实道路几何（来自路线估时）；缺省用示意/模拟线路。"""
    legs: list[PlannedLeg] = []
    cursor = departed_at
    sequence = 0
    overrides = route_overrides or {}
    for direction, plans in (("outbound", destination.outbound), ("return", destination.inbound)):
        if direction == "return":
            visit_starts_at = cursor
            cursor = cursor + timedelta(minutes=destination.venue.stay_minutes)
            visit_ends_at = cursor
        for index, plan in enumerate(plans):
            sequence += 1
            ends = cursor + timedelta(minutes=plan.minutes)
            route = overrides.get((direction, index)) or route_between(plan.origin, plan.destination, plan.schematic)
            legs.append(PlannedLeg(sequence, direction, plan, cursor, ends, route))
            cursor = ends
    return PlannedTimeline(legs=legs, visit_starts_at=visit_starts_at, visit_ends_at=visit_ends_at, completes_at=cursor)
