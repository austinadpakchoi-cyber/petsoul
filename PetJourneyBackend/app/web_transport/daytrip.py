"""港澳一日行（坐船去澳门老城区喝杯咖啡再回来）：第一条完整打通的真实城市对。

规划规则（都由服务端裁定，模型不参与）：
- 家 → 港澳码头：高德驾车估时（记下供应商、抓取时间与有效期）；
- 从开船时间反推出门：出门时间 ＝ 开船 − 运营方建议的登船提前量（30 分钟）− 打车时间；最早能赶上的那一班；
- 船：已核验的 TurboJET 船期按服务日期落地（当地时间 → UTC），航行时间用运营方公布的约数（60 分钟）；
- 澳门：外港码头 → 议事亭前地一带的一家真实咖啡店（高德，带来源），打车往返按高德估时；
- 返程：到店待 60 分钟（至少 30 分钟），再按澳门出发的船期找最早能赶上的一班（同样留 30 分钟登船，最多在码头等 2 小时）；
  当天已经来不及往返（太晚、末班已过）就改成下一个服务日期的早班出发（TA 在家等到那时再出门），跨午夜的日期与时区都按出发港当地算；
- 任何一项现实资料拿不到（地图不可用、查不到码头附近的店、船期过了复核期限），整趟行程不成立并返回明确原因，
  不退回演示线路、不编造地点或时间。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..utils import iso
from ..web_journey.catalog import Destination, LegPlan, VenuePlan
from .hubs import anchor, hub
from .timetable import Sailing, Timetable, load_timetable

TIMETABLE = "turbojet_hk_macau_outer"
CARRIER, CODE_PREFIX = "海獭轮渡", "Otter"  # 动物世界承运身份（原创），编号追溯到参考班次
ROUTE_VALID = timedelta(hours=24)  # 路线估算按一般路况，缓存一天
MAX_PIER_WAIT = timedelta(hours=2)  # 回程最多在码头等 2 小时（等不到就换更早/更晚的去程，不在码头过夜）


class PlanUnavailable(Exception):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass
class RoadEstimate:
    minutes: int
    route: list[dict]
    reference: dict


@dataclass
class DayTripPlan:
    destination: Destination
    leave_home_at: datetime
    outbound: Sailing
    inbound: Sailing
    venue_place: object  # PlaceCandidate
    routes: dict[tuple[str, int], list[dict]] = field(default_factory=dict)
    references: dict[tuple[str, int], dict] = field(default_factory=dict)
    timetable: Timetable | None = None


def _road(geo, mode: str, origin: dict, destination: dict, now: datetime, label: str, max_age: timedelta | None = None) -> RoadEstimate:
    args = ("amap", mode, (origin["lat"], origin["lng"]), (destination["lat"], destination["lng"]))
    estimate = geo.route(*args, max_age=max_age) if max_age is not None else geo.route(*args)
    if estimate is None or estimate.duration_seconds <= 0:
        raise PlanUnavailable("route_unavailable", f"{label}的路线估算现在拿不到（地图服务不可用或超出当日额度），这趟先不出发。")
    fetched = getattr(estimate, "fetched_at", None) or iso(now)
    expires = iso(datetime.fromisoformat(fetched.replace("Z", "+00:00")) + ROUTE_VALID)
    minutes = max(1, math.ceil(estimate.duration_seconds / 60))
    word = "驾车" if mode == "drive" else "步行"
    return RoadEstimate(minutes=minutes, route=[{"lat": lat, "lng": lng} for lat, lng in estimate.points],
                        reference={"kind": "routed_estimate", "provider": estimate.provider, "mode": mode, "fetched_at": fetched, "expires_at": expires,
                                   "distance_meters": estimate.distance_meters,
                                   "source_label": f"高德地图{word}估时（按一般路况，不含实时拥堵；{fetched[:16].replace('T', ' ')} UTC 获取）"})


def _node(node_id: str, name: str, lat: float, lng: float, tz: str) -> dict:
    return {"node_id": node_id, "name": name, "kind": "place", "timezone": tz, "lat": lat, "lng": lng, "verified": True}


def _sailing_reference(table: Timetable, sailing: Sailing) -> dict:
    return {"kind": "verified_timetable", "reference_id": sailing.reference_id, "timetable_id": table.timetable_id, "operator": table.operator,
            "service_date": sailing.service_date.isoformat(), "departure_local": sailing.departure_local, "timezone": sailing.timezone,
            "source_url": table.source["url"], "fetched_at": table.source["fetched_at"], "verified_at": table.source.get("verified_at"),
            "duration_basis": table.duration_basis, "fare": table.fare_note(sailing), "source_label": table.source_label()}


def _buffer_reference(table: Timetable, minutes: int) -> dict:
    return {"kind": "operator_rule", "minutes": minutes, "source_url": table.source["url"], "fetched_at": table.source["fetched_at"],
            "source_label": f"候船：运营方建议开船前至少 {table.boarding_buffer_minutes} 分钟登船（查验证件）"}


def plan_macau_day_trip(home, geo, now: datetime, *, fee: int, stay_minutes: int = 60, min_stay_minutes: int = 30,
                        road_max_age: timedelta | None = None, awake=None) -> DayTripPlan:
    """home：HomePlace（出发的家，须在香港）；geo：GeoService。返回一整份门到门行程，或抛 PlanUnavailable。
    road_max_age：出门前复核时要求接驳估算不旧于这个时长（按最新路况重新取）。
    awake(t)：TA 在 t 时刻是不是醒着（按 DNA 作息）；出门时间落在 TA 睡觉的时段就换更晚的一班（不会半夜把 TA 叫起来出门）。"""
    table = load_timetable(TIMETABLE)
    if home.city != "香港":
        raise PlanUnavailable("not_supported_here", "坐船去澳门目前只从香港的家出发。")
    if geo is None or not geo.configured("amap"):
        raise PlanUnavailable("map_unavailable", "地图服务没有接通，没法估算去码头的时间，这趟先不出发。")
    hk, mo = hub("hk-macau-ferry-terminal"), hub("macau-outer-harbour-ferry-terminal")
    home_node, hk_node, mo_node = home.node(), hk.node(), mo.node()
    to_pier = _road(geo, "drive", home_node, hk_node, now, "去港澳码头", road_max_age)
    spot = anchor("macau-old-town")
    centre = geo.place_in_city("amap", spot["query"]["keywords"], spot["query"]["city"])
    if centre is None:
        raise PlanUnavailable("place_unavailable", "没能在地图上核对到澳门老城区的位置，这趟先不出发。")
    cafe = geo.place_near("amap", centre.lat, centre.lng, keyword="咖啡", radius=600)
    if cafe is None:
        raise PlanUnavailable("place_unavailable", "澳门老城区附近没找到能核对的咖啡店，这趟先不出发。")
    cafe_node = _node("node-macau-venue", cafe.name, cafe.lat, cafe.lng, "Asia/Macau")
    to_cafe = _road(geo, "drive", mo_node, cafe_node, now, "从外港码头去老城区")
    back_to_pier = _road(geo, "drive", cafe_node, mo_node, now, "从老城区回码头")
    home_leg = _road(geo, "drive", hk_node, home_node, now, "从港澳码头回家")
    buffer = timedelta(minutes=table.boarding_buffer_minutes)

    not_before = now + timedelta(minutes=to_pier.minutes) + buffer
    for _ in range(60):  # 从最早能赶上的一班往后找，直到往返都成立（最多两天内）
        outbound = table.next_sailing("hk_to_macau", not_before)
        if outbound is None:
            break
        leave_home = outbound.departs_at - buffer - timedelta(minutes=to_pier.minutes)
        if awake is not None and not awake(leave_home):
            not_before = outbound.departs_at + timedelta(minutes=1)
            continue
        at_cafe = outbound.arrives_at + timedelta(minutes=to_cafe.minutes)
        for stay in (stay_minutes, min_stay_minutes):
            at_pier = at_cafe + timedelta(minutes=stay + back_to_pier.minutes)
            inbound = table.next_sailing("macau_to_hk", at_pier + buffer, days=1, not_after=at_pier + buffer + MAX_PIER_WAIT)
            if inbound is None:
                continue
            wait_back = int((inbound.departs_at - at_pier).total_seconds() // 60)
            outbound_legs = (
                LegPlan("connection", "taxi", "passenger", to_pier.minutes, home_node, hk_node),
                LegPlan("wait", "ferry", "passenger", table.boarding_buffer_minutes, hk_node, hk_node),
                LegPlan("main", "ferry", "passenger", table.duration_minutes, hk_node, mo_node, carrier=CARRIER, code_prefix=CODE_PREFIX),
                LegPlan("connection", "taxi", "passenger", to_cafe.minutes, mo_node, cafe_node),
            )
            inbound_legs = (
                LegPlan("connection", "taxi", "passenger", back_to_pier.minutes, cafe_node, mo_node),
                LegPlan("wait", "ferry", "passenger", wait_back, mo_node, mo_node),
                LegPlan("main", "ferry", "passenger", table.duration_minutes, mo_node, hk_node, carrier=CARRIER, code_prefix=CODE_PREFIX),
                LegPlan("connection", "taxi", "passenger", home_leg.minutes, hk_node, home_node),
            )
            venue = VenuePlan(cafe.place_id, cafe.name, cafe.lat, cafe.lng, "Asia/Macau", cafe.category or "咖啡馆", stay)
            destination = Destination(key="macau_ferry", title="坐船去澳门老城区", city="澳门",
                                      summary=f"打车去港澳码头，坐 {outbound.departure_local} 的船去澳门外港，在{cafe.name}坐一会儿，"
                                              f"再坐 {inbound.departure_local} 的船回来。",
                                      fee=fee, outbound=outbound_legs, venue=venue, inbound=inbound_legs, wish_keywords=("海", "船", "澳门"),
                                      food_area="macau-old-town")
            plan = DayTripPlan(destination=destination, leave_home_at=leave_home, outbound=outbound, inbound=inbound, venue_place=cafe, timetable=table)
            plan.routes = {("outbound", 0): to_pier.route, ("outbound", 3): to_cafe.route, ("return", 0): back_to_pier.route, ("return", 3): home_leg.route}
            plan.references = {("outbound", 0): to_pier.reference, ("outbound", 1): _buffer_reference(table, table.boarding_buffer_minutes),
                               ("outbound", 2): _sailing_reference(table, outbound), ("outbound", 3): to_cafe.reference,
                               ("return", 0): back_to_pier.reference, ("return", 1): _buffer_reference(table, wait_back),
                               ("return", 2): _sailing_reference(table, inbound), ("return", 3): home_leg.reference}
            return plan
        not_before = outbound.departs_at + timedelta(minutes=1)
    if not table.fresh(now.date()):
        raise PlanUnavailable("timetable_needs_recheck", "船期资料已经过了复核期限，要重新核对官网后才能出发。")
    raise PlanUnavailable("no_sailing", "最近两天里没有能赶上又能当天回来的船班。")
