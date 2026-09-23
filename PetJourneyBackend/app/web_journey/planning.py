"""旅程规划（出发与预览共用）：出发站选项、目的地解析（附近活动 / 真实交通 / 演示环境的演示线路）、每段交通的时间来源、到访地点。

- 正式环境没有演示线路；真实远行（REAL_TRIPS）按已核验时刻表与地图接驳规划，现实资料拿不到时明确不成立；
- 每段交通都记下时间从哪来：参考班次 / 运营方规定 / 路线估算（供应商与取回时间、有效期）/ 星球内规则 / 演示资料；
- 需要 self.storage / economy / geo / demo_catalog / can_drive / waiver_available / wishes_of / home_place_of（WebJourneyService 提供）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..schemas.web.journey import DestinationOption
from ..utils import iso as iso_now, parse_dt, utcnow
from ..web_home.place import default_place
from ..web_transport.daytrip import PlanUnavailable, plan_macau_day_trip
from ..web_transport.timetable import load_timetable
from .catalog import DESTINATIONS, Destination
from .errors import JourneyError
from .geo_plan import GeoPlan, apply_geo
from .local import NEEDS_LICENSE, NEEDS_REAL_PLACE, LocalPlan, LocalUnavailable, is_local, job_of, local_options, local_plan
from .planner import plan_timeline

import logging

logger = logging.getLogger("petsoul.web.journey")

WORLD_RULE = {"kind": "world_rule", "source_label": "星球内的路程：按世界规则估算（步行每小时约 4.5 公里），不是现实路线"}
ROUTE_MISSING = {"kind": "world_rule", "source_label": "这段路线估算没拿到：时长按世界规则估算，不是现实路况"}
DEMO_REFERENCE = {"kind": "demo_fixture", "source_label": "演示线路：时长为演示设定并按真实时间推进，未接入核验时刻表"}


def routed_reference(provider: str, mode: str, fetched_at: str) -> dict:
    word = {"walk": "步行", "taxi": "驾车", "drive": "驾车"}.get(mode, "路线")
    label = {"amap": "高德地图", "google": "Google 地图"}.get(provider, provider)
    return {"kind": "routed_estimate", "provider": provider, "mode": mode, "fetched_at": fetched_at,
            "expires_at": iso_now(parse_dt(fetched_at) + timedelta(hours=24)),
            "source_label": f"{label}{word}估时（按一般路况，不含实时拥堵；{fetched_at[:16].replace('T', ' ')} UTC 获取）"}


@dataclass(frozen=True)
class RealTrip:
    """正式环境的远行（真实交通）。fee 是星币旅费（世界内经济），与现实参考票价无关。"""

    key: str
    title: str
    city: str
    summary: str
    fee: int
    approx_minutes: int
    modes: tuple[str, ...]
    wish_keywords: tuple[str, ...]
    timetable: str
    home_city: str


REAL_TRIPS = {
    "macau_ferry": RealTrip("macau_ferry", "坐船去澳门老城区", "澳门",
                            "打车去港澳码头，按 TurboJET 官网船期坐船去澳门外港，在老城区一家真实咖啡店坐一会儿再坐船回来；出门时间按开船时间反推。",
                            40, 330, ("taxi", "ferry"), ("海", "船", "澳门"), "turbojet_hk_macau_outer", "香港"),
}


@dataclass
class Resolved:
    """一次出发（或预览）解析出的完整目的地：目录/附近活动/真实交通，外加地图估算与地点依据。"""

    destination: Destination
    local: LocalPlan | None
    trip: object | None  # web_transport.daytrip.DayTripPlan
    geo_plan: GeoPlan | None
    basis: str  # real / world_rule / demo_fixture
    template: str

    @property
    def final(self) -> Destination:
        return self.geo_plan.destination if self.geo_plan else self.destination

    @property
    def real_place(self):
        if self.geo_plan is not None and self.geo_plan.real_place is not None:
            return self.geo_plan.real_place
        return self.local.real_place if self.local else (self.trip.venue_place if self.trip else None)


class JourneyPlanningMixin:
    def destinations(self, user_id: str, pet_id: str, home_id: str | None = None, now: datetime | None = None) -> list[DestinationOption]:
        """出发站选项（不调用地图服务）。time_basis：routed_estimate＝出发时按地图估时；world_rule＝星球内的路程；
        verified_timetable＝已核验时刻表；demo_fixture＝演示环境。不成立的选项 available=false 并说明原因。"""
        now = now or utcnow()
        balance = self.economy.wallet(pet_id).balance
        wishes = self.wishes_of(user_id, pet_id)
        home = self.home_place_of(home_id) if home_id else default_place()
        region = "amap" if home.timezone in ("Asia/Hong_Kong", "Asia/Macau", "Asia/Shanghai") else "google"
        mapped = self.geo is not None and self.geo.configured(region)
        options = []
        for key, title, summary, fee, minutes in local_options(home, licensed=self.can_drive(pet_id)):
            modes = ["taxi"] if key == "local:city_trip" else (["drive"] if key == "local:drive_trip" else ["walk"])
            needs_real = key.split(":", 1)[1] in NEEDS_REAL_PLACE
            available = mapped or self.demo_catalog or not needs_real
            basis = "routed_estimate" if mapped else ("demo_fixture" if self.demo_catalog else "world_rule")
            options.append(DestinationOption(destination_key=key, title=title, city=home.city, summary=summary, fee=fee, total_minutes=minutes,
                                             modes=modes, time_basis=basis, wish_match=None,
                                             affordable=balance >= fee or self.waiver_available(pet_id, key), available=available,
                                             unavailable_reason=None if available else "地图服务现在不可用：进城和自驾要去现实里的地方，暂时去不了"))
        if not self.demo_catalog:
            for trip in REAL_TRIPS.values():
                if home.city != trip.home_city:
                    continue
                table = load_timetable(trip.timetable)
                reason = None if mapped else "地图服务现在不可用，没法估算去码头的时间"
                if table.fresh(now.date()) is False:
                    reason = "船期资料已过复核期限，要重新核对官网后才能出发"
                match = next((w for w in wishes if any(k in w for k in trip.wish_keywords)), None)
                fare = table.reference_fares["classes"]["economy"] if table.reference_fares else None
                note = f"现实参考：{table.source_label()}" + (f"；经济位 HK${fare['day_weekday']} 起（现实票价，与星币无关）" if fare else "")
                options.append(DestinationOption(destination_key=trip.key, title=trip.title, city=trip.city, summary=trip.summary, fee=trip.fee,
                                                 total_minutes=trip.approx_minutes, modes=list(trip.modes), time_basis="verified_timetable",
                                                 wish_match=f"你交代过：{match}" if match else None, affordable=balance >= trip.fee,
                                                 available=reason is None, unavailable_reason=reason, reference_note=note))
            return options
        for dest in (DESTINATIONS.values() if self.catalog_available(home) else ()):
            match = next((w for w in wishes if any(k in w for k in dest.wish_keywords)), None)
            options.append(
                DestinationOption(
                    destination_key=dest.key,
                    title=dest.title,
                    city=dest.city,
                    summary=dest.summary,
                    fee=dest.fee,
                    total_minutes=dest.total_minutes,
                    modes=dest.modes,
                    time_basis="demo_fixture",
                    wish_match=f"你交代过：{match}" if match else None,
                    affordable=balance >= dest.fee,
                )
            )
        return options

    @staticmethod
    def catalog_available(home) -> bool:
        """首发演示线路（海边咖啡馆/坐船去澳门/飞去东京）从香港·中环出发，只给住在那里的宠物。"""
        return home.area_key == "hk_central"

    def resolve(self, home, pet_id: str, destination_key: str, now: datetime) -> Resolved:
        """把一个出发选项解析成完整目的地（出发与预览共用）。现实资料拿不到时抛 JourneyError(transport_unavailable)，不退回演示。"""
        local: LocalPlan | None = None
        trip = None
        if destination_key in NEEDS_LICENSE and not self.can_drive(pet_id):
            raise JourneyError("no_license", "还没有驾照，不能自己开车；可以打车、坐公共交通或者走路。")
        if is_local(destination_key):
            try:
                local = local_plan(destination_key, home, self.geo, demo=self.demo_catalog)
            except LocalUnavailable as exc:
                raise JourneyError("transport_unavailable", exc.message, unavailable_reason=exc.reason) from exc
            dest = local.destination if local else None
        elif self.demo_catalog:
            dest = DESTINATIONS.get(destination_key) if self.catalog_available(home) else None
        elif destination_key in REAL_TRIPS and home.city == REAL_TRIPS[destination_key].home_city:
            awake = (lambda t, _pet=pet_id: self.awake_at(_pet, t)) if self.awake_at is not None else None
            try:
                trip = plan_macau_day_trip(home, self.geo, now, fee=REAL_TRIPS[destination_key].fee, awake=awake)
            except PlanUnavailable as exc:
                raise JourneyError("transport_unavailable", exc.message, unavailable_reason=exc.reason) from exc
            dest = trip.destination
        else:
            dest = None
        if dest is None:
            raise JourneyError("unknown_destination", "没有这个目的地。")
        geo_plan = None
        if trip is None and (local is None or local.basis == "real" or self.demo_catalog):
            geo_plan = self._geo_plan(dest, find_place=local is None)  # 真实地点才按地图估路程；星球内的路程按世界规则
        if geo_plan is not None and local is not None:
            geo_plan.real_place = local.real_place
        template = ("work" if job_of(destination_key) else local.template) if local else "cafe"
        basis = local.basis if local else ("real" if trip else "demo_fixture")
        return Resolved(destination=dest, local=local, trip=trip, geo_plan=geo_plan, basis=basis, template=template)

    def preview(self, pet_id: str, home_id: str, destination_key: str, now: datetime | None = None):
        """出发前看一眼真实行程：(Resolved, PlannedTimeline, [每段来源])。不扣钱、不写行程、不分配动物世界编号。"""
        now = now or utcnow()
        resolved = self.resolve(self.home_place_of(home_id), pet_id, destination_key, now)
        trip = resolved.trip
        departed_at = trip.leave_home_at if trip is not None else now
        routes = trip.routes if trip is not None else (resolved.geo_plan.routes if resolved.geo_plan else None)
        timeline = plan_timeline(resolved.final, departed_at, routes)
        references = []
        index_in_direction: dict[str, int] = {}
        for planned in timeline.legs:
            index = index_in_direction.get(planned.direction, 0)
            index_in_direction[planned.direction] = index + 1
            references.append(self._leg_reference(resolved, planned.direction, index, planned.plan.mode, now))
        return resolved, timeline, references

    def _leg_reference(self, resolved: Resolved, direction: str, index: int, mode: str, now: datetime) -> dict:
        """这段时间从哪来：真实交通的参考班次/运营方规定/路线估算；附近活动的路线估算；星球内规则；演示环境的演示资料。"""
        trip, geo_plan = resolved.trip, resolved.geo_plan
        reference = trip.references.get((direction, index)) if trip is not None else None
        if reference is None and geo_plan is not None and (direction, index) in geo_plan.estimated:
            reference = routed_reference(geo_plan.estimated[(direction, index)], mode, geo_plan.fetched.get((direction, index)) or iso_now(now))
        if reference is None:
            if resolved.basis == "world_rule":
                reference = WORLD_RULE
            elif resolved.basis == "real":
                reference = ROUTE_MISSING  # 真实地点但路线估算没拿到：如实说是规则估算，不标成演示
            else:
                reference = DEMO_REFERENCE
        return reference

    def _geo_plan(self, dest: Destination, find_place: bool = True) -> GeoPlan | None:
        if self.geo is None:
            return None
        try:
            return apply_geo(dest, self.geo, find_place=find_place)
        except Exception:  # noqa: BLE001 - 地图供应商异常不阻断出发：回退演示线路并如实标注
            logger.exception("geo plan failed destination=%s", dest.key)
            return None

    @staticmethod
    def visit_place(dest: Destination, real, basis: str, now: datetime) -> dict:
        """到访地点：真实地点（供应商、编号、取回时间、署名）/ 星球内的地方 / 演示资料（只在演示环境）。"""
        venue = dest.venue
        if real is not None:
            return {"provider": real.provider, "place_id": real.place_id, "name": real.name, "address": real.address, "lat": real.lat, "lng": real.lng,
                    "coord_system": "wgs84", "category": real.category, "source_updated_at": getattr(real, "fetched_at", None) or iso_now(now),
                    "attribution": real.attribution, "timezone": venue.tz, "food_area": dest.food_area}
        if basis in ("world_rule", "real"):
            return {"provider": "world", "place_id": venue.place_id, "name": venue.name, "address": None, "lat": venue.lat, "lng": venue.lng,
                    "coord_system": "wgs84", "category": venue.category, "source_updated_at": None,
                    "attribution": "星球内的地方：世界规则设定，不对应现实地址或商家", "timezone": venue.tz, "food_area": dest.food_area}
        return {"provider": "fixture", "place_id": venue.place_id, "name": venue.name, "address": None, "lat": venue.lat, "lng": venue.lng,
                "coord_system": "wgs84", "category": venue.category, "source_updated_at": None, "attribution": "演示资料：不对应真实商家",
                "timezone": venue.tz, "food_area": dest.food_area}

    def _record_reference_trip(self, table, sailing, now: datetime) -> None:
        with self.storage.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO web_transport_reference_trips (reference_id, timetable_id, direction, service_date, departure_local, timezone, "
                "departure_utc, arrival_utc, origin_hub, destination_hub, operator, duration_basis, source_url, source_fetched_at, source_sha256, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (sailing.reference_id, table.timetable_id, sailing.direction, sailing.service_date.isoformat(), sailing.departure_local, sailing.timezone,
                 iso_now(sailing.departs_at), iso_now(sailing.arrives_at), sailing.origin_hub, sailing.destination_hub, table.operator, table.duration_basis,
                 table.source["url"], table.source["fetched_at"], table.source["raw_sha256"], iso_now(now)))
