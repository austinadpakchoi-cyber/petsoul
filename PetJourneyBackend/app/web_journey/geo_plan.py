"""出发时用真实地点与路线估时替换演示目录中可替换的部分（供应商可用时）。

- 目的地的咖啡馆换成附近真实咖啡店（高德：港澳；Google：其他地区），带来源署名；店内仍是原创场景；
- 步行/打车段用真实路线估时与道路几何（time_basis=routed_estimate），时长按真实估算，不压缩；
- 轮渡/航班/火车没有核验时刻表，保持 demo_fixture；
- 任何一步失败都保留演示数据并如实标注，不编造地点或时长。
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from typing import Protocol

from .catalog import Destination

AMAP_TIMEZONES = {"Asia/Hong_Kong", "Asia/Macau", "Asia/Shanghai"}
ROUTABLE = {"walk": "walk", "taxi": "drive", "drive": "drive"}


class GeoLike(Protocol):
    def configured(self, region: str) -> bool: ...
    def place_near(self, region, lat, lng, *, keyword: str = "咖啡", google_type: str = "cafe", radius: int = 800): ...
    def route(self, region, mode, origin, destination): ...


@dataclass
class GeoPlan:
    destination: Destination
    real_place: object | None = None  # PlaceCandidate
    routes: dict[tuple[str, int], list[dict]] = field(default_factory=dict)
    estimated: dict[tuple[str, int], str] = field(default_factory=dict)  # (direction, index) → provider
    fetched: dict[tuple[str, int], str | None] = field(default_factory=dict)  # (direction, index) → 估算取回时间


def region_of(timezone: str) -> str:
    return "amap" if timezone in AMAP_TIMEZONES else "google"


def _with_endpoint(node: dict, place) -> dict:
    return {**node, "name": place.name, "lat": place.lat, "lng": place.lng, "verified": False}


def apply_geo(destination: Destination, geo: GeoLike, *, find_place: bool = True) -> GeoPlan:
    """find_place=False：地点已经是真实地点（家附近的日常出门），只估算路线。"""
    venue = destination.venue
    venue_node_ids = {leg.destination["node_id"] for leg in destination.outbound[-1:]} | {leg.origin["node_id"] for leg in destination.inbound[:1]}
    region = region_of(venue.tz)
    place = geo.place_near(region, venue.lat, venue.lng) if find_place and geo.configured(region) else None

    outbound = list(destination.outbound)
    inbound = list(destination.inbound)
    if place is not None:
        outbound = [replace(l, destination=_with_endpoint(l.destination, place)) if l.destination["node_id"] in venue_node_ids else l for l in outbound]
        inbound = [replace(l, origin=_with_endpoint(l.origin, place)) if l.origin["node_id"] in venue_node_ids else l for l in inbound]
        venue = replace(venue, place_id=place.place_id, name=place.name, lat=place.lat, lng=place.lng, category=place.category or venue.category)

    jobs: dict[tuple[str, int], tuple[str, str, tuple[float, float], tuple[float, float]]] = {}
    for direction, legs in (("outbound", outbound), ("return", inbound)):
        for index, leg in enumerate(legs):
            mode = ROUTABLE.get(leg.mode)
            if mode is None or leg.kind == "wait":
                continue
            leg_region = region_of(leg.origin.get("timezone") or venue.tz)
            if not geo.configured(leg_region):
                continue
            jobs[(direction, index)] = (leg_region, mode, (leg.origin["lat"], leg.origin["lng"]), (leg.destination["lat"], leg.destination["lng"]))

    plan = GeoPlan(destination=destination, real_place=place)
    if jobs:
        with ThreadPoolExecutor(max_workers=min(4, len(jobs))) as pool:
            results = dict(zip(jobs, pool.map(lambda job: geo.route(*job), jobs.values())))
        for (direction, index), estimate in results.items():
            if estimate is None or estimate.duration_seconds <= 0:
                continue
            legs = outbound if direction == "outbound" else inbound
            legs[index] = replace(legs[index], minutes=max(1, math.ceil(estimate.duration_seconds / 60)))
            plan.routes[(direction, index)] = [{"lat": lat, "lng": lng} for lat, lng in estimate.points]
            plan.estimated[(direction, index)] = estimate.provider
            plan.fetched[(direction, index)] = getattr(estimate, "fetched_at", None)
    plan.destination = replace(destination, outbound=tuple(outbound), inbound=tuple(inbound), venue=venue)
    return plan

