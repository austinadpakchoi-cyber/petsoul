"""旅程记录 → 契约 DTO（JourneyMapSnapshot / JourneyLeg / Visit / JourneyBrief）。

车辆位置由服务器时间与时间线计算；音符/电视入口只来自实际（确定性日程中的）影音活动；
到站后最近一次被中断的影音活动以“已保存进度”显示，直到旅程结束。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Callable

from ..companion_media.schedule import LegWindow, ScheduledActivity, activity_at, last_media_activity
from ..schemas.web.common import CoordSystem, DataOrigin, LatLng
from ..schemas.web.home import JourneyBrief
from ..schemas.web.journey import Place, PlaceProvider, VenueTemplate, Visit, VisitActivity, VisitActivityKind, VisitActivityState, VisitState
from ..schemas.web.transport import (
    LegTimeSource,
    ActivityBadgeKind,
    DataFreshness,
    JourneyLeg,
    JourneyMapSnapshot,
    LegKind,
    LegPhase,
    LegTimes,
    MapActivityEntry,
    MapEntryAction,
    PetArrivalContext,
    PositionBasis,
    TimeBasis,
    TransportMode,
    TransportNode,
    TransportReferenceSummary,
    TravelActivity,
    TravelActivityKind,
    TravelActivityState,
    TravellerRole,
    VehiclePosition,
)
from ..transport_world.registry import WorldServiceRegistry
from ..transport_world.timeline import leg_progress, position_along
from ..utils import parse_dt, utcnow
from .repository import JourneyRecord, LegRecord, VisitRecord
from .trip_titles import going_to

MODE_TEXT = {"flight": "飞机", "train": "火车", "ferry": "轮船", "drive": "汽车", "taxi": "出租车", "transit": "公交", "walk": "步行"}
ACTIVITY_TEXT = {"listening": "在听歌", "watching": "在看剧", "resting": "在休息", "window_gazing": "在看窗外", "dining": "在吃东西", "writing_postcard": "在写明信片"}


def window_of(leg: LegRecord) -> LegWindow:
    return LegWindow(leg.leg_id, leg.kind, leg.mode, leg.role, leg.starts_at, leg.ends_at)


def leg_in_progress(legs: Sequence[LegRecord], now: datetime) -> LegRecord | None:
    """此刻**正在走**的那一段。换乘间隙、还没出发、已经到了，都是 None。"""
    return next((leg for leg in legs if leg.starts_at <= now < leg.ends_at), None)


def current_leg(legs: Sequence[LegRecord], now: datetime) -> LegRecord | None:
    """TA 现在**算在哪一段**：地图把位置点画在哪条线上、显示成什么交通方式，都按这个。

    回退顺序是**产品判断**，不是各写各的实现细节：
      · 正在走的那一段；
      · 换乘间隙（打车到了机场、飞机还没起飞）算**刚过去那一段**——TA 人还在那个地方；
      · 一段都还没开始（出发时间还没到）算第一段。

    这三条一旦有第二份副本，地图上「TA 在哪一段」和行程详情页就会各说一套，
    **而这种不一致不会报错，只会显示错**。所以只留一份，`map_snapshot` 自己也调它。

    多段行程（打车→飞机→火车）里取"主段"是错的：TA 还在打车去机场，
    主段却是飞机，位置点会被画到航线上。

    前提：`legs` 按 `sequence` 排好序传进来（`JourneyRepository.legs()` 就是这个顺序）。
    纯计算，不碰连接、不写任何东西。
    """
    in_progress = leg_in_progress(legs, now)
    if in_progress is not None:
        return in_progress
    passed = [leg for leg in legs if leg.ends_at <= now]
    if passed:
        return passed[-1]
    return legs[0] if legs else None


def _node(data: dict) -> TransportNode:
    return TransportNode(**{k: data[k] for k in ("node_id", "name", "kind", "timezone", "lat", "lng", "verified")})


class JourneySnapshotBuilder:
    def __init__(self, registry: WorldServiceRegistry, quiet_of: Callable[[str], bool], session_state_of: Callable[[str], str | None]) -> None:
        self.registry = registry
        self.quiet_of = quiet_of
        self.session_state_of = session_state_of

    def leg_dto(self, leg: LegRecord, itinerary_version: int, now: datetime) -> JourneyLeg:
        progress = leg_progress(self._times(leg), now)
        if now < leg.starts_at:
            phase = LegPhase.scheduled
        elif now >= leg.ends_at:
            phase = LegPhase.arrived
        elif leg.kind == "wait":
            phase = LegPhase.waiting
        elif leg.kind == "connection":
            phase = LegPhase.connecting
        else:
            phase = LegPhase.arriving if progress > 0.95 else LegPhase.in_transit
        return JourneyLeg(
            leg_id=leg.leg_id,
            journey_id=leg.journey_id,
            sequence=leg.sequence,
            kind=LegKind(leg.kind),
            mode=TransportMode(leg.mode),
            role=TravellerRole(leg.role),
            world_service=self.registry.by_id(leg.world_service_id) if leg.world_service_id else None,
            origin=_node(leg.origin),
            destination=_node(leg.destination),
            times=self._times(leg),
            time_basis=TimeBasis(leg.time_basis),
            freshness=DataFreshness(leg.freshness),
            position_basis=PositionBasis(leg.position_basis),
            phase=phase,
            itinerary_version=itinerary_version,
            route=[LatLng(**p) for p in leg.route],
            reference=self._reference(leg),
            time_source=LegTimeSource((leg.reference or {}).get("kind")) if (leg.reference or {}).get("kind") in LegTimeSource._value2member_map_ else None,
            rescheduled_reason=None,
        )

    @staticmethod
    def _reference(leg: LegRecord) -> TransportReferenceSummary:
        """这段时间从哪来：参考班次（带编号与核验时间）/ 路线估算（供应商与取回时间）/ 世界规则 / 演示。"""
        ref = leg.reference or {}
        label = ref.get("source_label") or "演示线路：时长为演示设定并按真实时间推进，未接入核验时刻表"
        verified = ref.get("verified_at") or (ref.get("fetched_at") if ref.get("kind") == "routed_estimate" else None)
        return TransportReferenceSummary(reference_id=ref.get("reference_id"), time_basis=TimeBasis(leg.time_basis), freshness=DataFreshness(leg.freshness),
                                         source_label=label, verified_at=parse_dt(verified) if verified else None)

    @staticmethod
    def _times(leg: LegRecord) -> LegTimes:
        return LegTimes(origin_timezone=leg.origin["timezone"], destination_timezone=leg.destination["timezone"],
                        planned_departure_utc=leg.starts_at, planned_arrival_utc=leg.ends_at)

    def _activity_dto(self, activity: ScheduledActivity, now: datetime) -> TravelActivity:
        state = activity.state_at(now)
        if state is TravelActivityState.active and activity.session_id and self.session_state_of(activity.session_id) == "paused":
            state = TravelActivityState.paused
        return TravelActivity(activity_id=activity.activity_id, leg_id=activity.leg_id, kind=activity.kind, state=state, starts_at=activity.starts_at,
                              ends_at=activity.ends_at, media_session_id=activity.session_id, interruptible=True, version=1)

    def _entry(self, activity: TravelActivity, title: str) -> MapActivityEntry:
        badge = ActivityBadgeKind.music if activity.kind is TravelActivityKind.listening else ActivityBadgeKind.tv
        verb = "听" if badge is ActivityBadgeKind.music else "看"
        label = {TravelActivityState.paused: f"和 TA 一起暂停了《{title}》", TravelActivityState.interrupted: f"到站了，《{title}》已保存进度"}.get(
            activity.state, f"TA 在{verb}《{title}》")
        actions = [MapEntryAction.solo, MapEntryAction.open_leg_card] if activity.state is TravelActivityState.interrupted else [MapEntryAction.join, MapEntryAction.solo, MapEntryAction.open_leg_card]
        return MapActivityEntry(entry_id=f"entry-{activity.activity_id}", leg_id=activity.leg_id, activity_id=activity.activity_id, badge=badge,
                                badge_state=activity.state, media_session_id=activity.media_session_id, label=label, actions=actions)

    def map_snapshot(self, journey: JourneyRecord, legs: list[LegRecord], visit: VisitRecord | None, now: datetime | None = None) -> JourneyMapSnapshot:
        now = now or utcnow()
        quiet = self.quiet_of(journey.pet_id)
        current = leg_in_progress(legs, now)
        passed = [l for l in legs if l.ends_at <= now]
        focus = current_leg(legs, now)
        activities: list[TravelActivity] = []
        entries: list[MapActivityEntry] = []
        if current is not None:
            scheduled = activity_at(window_of(current), now, quiet)
            if scheduled is not None:
                dto = self._activity_dto(scheduled, now)
                activities.append(dto)
                if scheduled.media is not None:
                    entries.append(self._entry(dto, scheduled.media.title))
        elif journey.lifecycle == "active":
            recent = next((l for l in reversed(passed) if l.kind == "main"), None)
            if recent is not None and now < recent.ends_at + timedelta(minutes=90):
                last = last_media_activity(window_of(recent), quiet)
                if last is not None and last.truncated:
                    dto = self._activity_dto(last, now)
                    activities.append(dto)
                    entries.append(self._entry(dto, last.media.title if last.media else ""))
        vehicle = None
        if focus.route:
            progress = leg_progress(self._times(focus), now)
            point, heading = position_along([LatLng(**p) for p in focus.route], progress)
            vehicle = VehiclePosition(leg_id=focus.leg_id, lat=point.lat, lng=point.lng, heading_deg=heading, progress=progress, computed_at=now,
                                      position_basis=PositionBasis(focus.position_basis))
        arrival = None
        if visit is not None:
            last_outbound = [l for l in legs if l.direction == "outbound"][-1]
            arrival = PetArrivalContext(journey_id=journey.journey_id, itinerary_version=journey.itinerary_version, leg_id=last_outbound.leg_id,
                                        city=journey.city, destination_timezone=visit.place.get("timezone", "Asia/Hong_Kong"),
                                        feasible_arrival_utc=visit.starts_at, stay_window_start_utc=visit.starts_at, stay_window_end_utc=visit.ends_at)
        return JourneyMapSnapshot(
            journey_id=journey.journey_id, pet_id=journey.pet_id, itinerary_version=journey.itinerary_version, lifecycle=journey.lifecycle,
            destination_title=journey.title, current_visit_id=visit.visit_id if visit and visit.starts_at <= now < visit.ends_at else None,
            planned_visit_id=visit.visit_id if visit else None, server_time=now, legs=[self.leg_dto(l, journey.itinerary_version, now) for l in legs], current_leg_id=focus.leg_id,
            vehicle=vehicle, activities=activities, activity_entries=entries, arrival_context=arrival, data_origin=DataOrigin.live,
        )

    def visit_dto(self, visit: VisitRecord, state: str) -> Visit:
        place = visit.place
        return Visit(
            visit_id=visit.visit_id, journey_id=visit.journey_id, pet_id=visit.pet_id,
            place=Place(provider=PlaceProvider(place["provider"]), place_id=place["place_id"], name=place["name"], address=place.get("address"),
                        lat=place["lat"], lng=place["lng"], coord_system=CoordSystem(place["coord_system"]), category=place.get("category"),
                        source_updated_at=parse_dt(place["source_updated_at"]) if place.get("source_updated_at") else None,
                        attribution=place.get("attribution"), data_origin=DataOrigin.fixture if place["provider"] == "fixture" else DataOrigin.live),
            state=VisitState(state), template=VenueTemplate(visit.template), planned_arrival_utc=visit.starts_at,
            arrived_at=visit.starts_at if state in ("active", "completed") else None, leaving_at=visit.ends_at, recommendation_id=visit.recommendation_id,
            activities=[VisitActivity(activity_id=a["activity_id"], kind=VisitActivityKind(a["kind"]), label=a["label"],
                                      state=VisitActivityState(a["state"]) if state == "active" or a["state"] == "done" else VisitActivityState.disabled,
                                      result_text=a.get("result_text")) for a in visit.activities],
            interior_is_original=True, data_origin=DataOrigin.live,
        )

    def brief(self, journey: JourneyRecord, legs: list[LegRecord], visit: VisitRecord | None, now: datetime) -> JourneyBrief:
        current = leg_in_progress(legs, now)
        if visit and visit.starts_at <= now < visit.ends_at:
            headline = f"TA 在{visit.place['name']}"
        elif current is not None:
            service = self.registry.by_id(current.world_service_id) if current.world_service_id else None
            ride = f"{service.carrier_name} {service.service_code}" if service else MODE_TEXT.get(current.mode, current.mode)
            scheduled = activity_at(window_of(current), now, self.quiet_of(journey.pet_id))
            doing = f"，{ACTIVITY_TEXT[scheduled.kind.value]}" if scheduled else ""
            headline = f"TA 正在{'等' if current.kind == 'wait' else '坐'}{ride}{doing}" if current.mode != "walk" else f"TA 正在步行{doing}"
        else:
            headline = f"TA 在去{going_to(journey.title)}的路上"
        return JourneyBrief(journey_id=journey.journey_id, itinerary_version=journey.itinerary_version, headline=headline,
                            current_visit_id=visit.visit_id if visit and visit.starts_at <= now < visit.ends_at else None,
                            current_leg_id=current.leg_id if current else None)
