from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from math import cos, pi, sin, sqrt

from .config import Settings
from .providers import JourneyCity
from .schemas import (
    ItineraryStop,
    JourneyPlan,
    JourneyStatus,
    PlaceSignal,
    RouteSegment,
    ScheduledTransportLeg,
    TransportLegStatus,
    TravelMode,
    WorldActivity,
    WorldSimulationSnapshot,
    WorldTimelineItem,
)
from .storage import PetRecord


@dataclass(frozen=True)
class _StopWindow:
    stop: ItineraryStop
    start: datetime
    end: datetime


class WorldSimulationEngine:
    provider_name = "world-simulation-engine"

    def __init__(self, settings: Settings):
        self.settings = settings

    def snapshot(
        self,
        *,
        pet: PetRecord,
        city: JourneyCity,
        plan: JourneyPlan,
        now: datetime,
    ) -> WorldSimulationSnapshot:
        now = self._aware(now)
        elapsed = max(0, int((now - pet.created_at).total_seconds()))
        active_transport = self._active_transport(plan.scheduled_transport, now)
        timeline = self._timeline(plan, now)
        current_item = next((item for item in timeline if item.is_current), None)
        next_stop = self._next_stop(plan.stops, now)

        activity = self._activity(
            pet=pet,
            city=city,
            plan=plan,
            now=now,
            active_transport=active_transport,
            current_item=current_item,
            next_stop=next_stop,
        )
        status = activity.status

        return WorldSimulationSnapshot(
            pet_id=pet.pet_id,
            city=plan.city,
            generated_at=now,
            provider=self.provider_name,
            elapsed_seconds=elapsed,
            travel_day=max(1, int(elapsed // 86_400) + 1),
            weather=city.weather,
            status=status,
            status_note=self._status_note(activity, active_transport),
            energy=self._energy(status, elapsed),
            happiness=self._clamp(78 + self._wave(elapsed + 4, 18, 2), 25, 99),
            curiosity=self._curiosity(activity, elapsed),
            current_activity=activity,
            active_transport=active_transport,
            next_stop=next_stop,
            timeline=timeline,
            rules=[
                "真实世界原则：长距离移动必须有交通方式，不瞬移。",
                "时间流逝原则：停留、候车、飞行和散步都按真实时间推进。",
                "自主性原则：用户可以收藏或参考攻略，但不能决定 TA 喜不喜欢哪里。",
                "手机原则：iOS 展示 TA 正在生活，不把地图做成命令式导航。",
            ],
        )

    def _activity(
        self,
        *,
        pet: PetRecord,
        city: JourneyCity,
        plan: JourneyPlan,
        now: datetime,
        active_transport: ScheduledTransportLeg | None,
        current_item: WorldTimelineItem | None,
        next_stop: ItineraryStop | None,
    ) -> WorldActivity:
        if active_transport and active_transport.status in {
            TransportLegStatus.waiting,
            TransportLegStatus.boarding,
            TransportLegStatus.in_transit,
        }:
            lat, lng = self._transport_coordinate(active_transport)
            status = self._transport_status(active_transport)
            return WorldActivity(
                id=f"transport-{active_transport.id}",
                kind="transport",
                status=status,
                title=active_transport.title,
                detail=active_transport.timeline_note or active_transport.detail,
                city=plan.city,
                place_name=active_transport.destination_name,
                lat=lat,
                lng=lng,
                mode=active_transport.mode,
                started_at=active_transport.scheduled_departure,
                ends_at=active_transport.scheduled_arrival,
                progress=active_transport.progress,
                next_place_name=active_transport.destination_name,
                icon_hint=self._icon_hint(active_transport.mode),
                source=active_transport.provider,
                current_transport_id=active_transport.id,
            )

        if current_item:
            status = self._timeline_status(current_item)
            lat, lng = self._fallback_coordinate(current_item, city.position.lat, city.position.lng)
            stop = self._stop_for_item(plan.stops, current_item)
            return WorldActivity(
                id=current_item.id,
                kind=current_item.kind,
                status=status,
                title=current_item.title,
                detail=current_item.detail,
                city=current_item.city,
                place_name=current_item.place_name,
                lat=lat,
                lng=lng,
                mode=current_item.mode,
                started_at=current_item.planned_start,
                ends_at=current_item.planned_end,
                progress=current_item.progress,
                dwell_minutes=stop.dwell_minutes if stop else None,
                next_place_name=next_stop.name if next_stop else None,
                icon_hint=self._icon_hint(current_item.mode),
                can_generate_photo=bool(stop and stop.photo_candidate),
                can_send_postcard=bool(stop and stop.postcard_candidate),
                source=stop.source if stop else plan.provider,
            )

        if next_stop:
            rest_stop = self._rest_stop_before_next(plan, next_stop)
            return WorldActivity(
                id=f"rest-before-{next_stop.id}",
                kind="rest",
                status=JourneyStatus.resting,
                title=f"{pet.name} 正在休息，等今天慢慢开始",
                detail=f"TA 还没有出发去 {next_stop.name}，现在先在 {rest_stop.name} 附近安静待着。",
                city=rest_stop.city,
                place_name=rest_stop.name,
                lat=rest_stop.lat,
                lng=rest_stop.lng,
                mode=TravelMode.stay,
                progress=0.0,
                dwell_minutes=rest_stop.dwell_minutes,
                next_place_name=next_stop.name,
                icon_hint="moon",
                can_generate_photo=False,
                can_send_postcard=False,
                source=rest_stop.source,
            )

        fallback_place = self._place_for_fallback(plan)
        return WorldActivity(
            id="world-rest-after-plan",
            kind="rest",
            status=JourneyStatus.resting,
            title=f"{pet.name} 正在慢慢休息",
            detail=f"今天的主要路线已经结束，TA 会在 {fallback_place.name} 附近安静待一会儿。",
            city=fallback_place.city,
            place_name=fallback_place.name,
            lat=fallback_place.lat,
            lng=fallback_place.lng,
            mode=TravelMode.stay,
            progress=1.0,
            next_place_name=None,
            icon_hint="moon",
            source=fallback_place.source,
        )

    def _timeline(self, plan: JourneyPlan, now: datetime) -> list[WorldTimelineItem]:
        windows = self._stop_windows(plan.stops, now)
        items: list[WorldTimelineItem] = []
        for index, window in enumerate(windows):
            current = window.start <= now < window.end
            items.append(
                WorldTimelineItem(
                    id=window.stop.id,
                    kind="stop",
                    title=window.stop.title,
                    detail=window.stop.detail,
                    city=window.stop.city,
                    place_name=window.stop.name,
                    lat=window.stop.lat,
                    lng=window.stop.lng,
                    mode=TravelMode.stay,
                    planned_start=window.start,
                    planned_end=window.end,
                    progress=self._progress(now, window.start, window.end),
                    is_current=current,
                )
            )

            if index + 1 < len(windows):
                segment = plan.route_segments[index] if index < len(plan.route_segments) else None
                next_window = windows[index + 1]
                move_start = window.end
                travel_seconds = segment.duration_seconds if segment and segment.duration_seconds else 900
                move_end = min(next_window.start, move_start + timedelta(seconds=max(480, travel_seconds)))
                if move_end <= move_start:
                    move_end = move_start + timedelta(minutes=max(8, travel_seconds // 60))
                items.append(self._movement_item(segment, window.stop, next_window.stop, move_start, move_end, now, plan))
                if move_end < next_window.start:
                    items.append(
                        self._pause_before_stop_item(
                            destination=next_window.stop,
                            start=move_end,
                            end=next_window.start,
                            now=now,
                        )
                    )

        for leg in plan.scheduled_transport:
            items.append(self._transport_item(leg, now, plan.city))

        return sorted(items, key=lambda item: item.planned_start or now)

    def _movement_item(
        self,
        segment: RouteSegment | None,
        origin: ItineraryStop,
        destination: ItineraryStop,
        start: datetime,
        end: datetime,
        now: datetime,
        plan: JourneyPlan,
    ) -> WorldTimelineItem:
        mode = segment.mode if segment else TravelMode.walk
        progress = self._progress(now, start, end)
        lat, lng = self._route_coordinate(segment, origin, destination, progress)
        return WorldTimelineItem(
            id=(segment.id if segment else f"move-{origin.id}-{destination.id}"),
            kind="movement",
            title=(segment.title if segment else f"前往 {destination.name}"),
            detail=(segment.detail if segment else "TA 会按真实路线慢慢接近下一站。"),
            city=destination.city or plan.city,
            place_name=destination.name,
            lat=lat,
            lng=lng,
            mode=mode,
            planned_start=start,
            planned_end=end,
            progress=progress,
            is_current=start <= now < end,
        )

    def _pause_before_stop_item(
        self,
        *,
        destination: ItineraryStop,
        start: datetime,
        end: datetime,
        now: datetime,
    ) -> WorldTimelineItem:
        return WorldTimelineItem(
            id=f"pause-before-{destination.id}",
            kind="rest",
            title=f"在 {destination.name} 附近等一会儿",
            detail="TA 已经慢慢靠近了下一站，但没有立刻打卡，只是在附近找了个不吵的位置停下来。",
            city=destination.city,
            place_name=destination.name,
            lat=destination.lat,
            lng=destination.lng,
            mode=TravelMode.stay,
            planned_start=start,
            planned_end=end,
            progress=self._progress(now, start, end),
            is_current=start <= now < end,
        )

    def _transport_item(self, leg: ScheduledTransportLeg, now: datetime, city: str) -> WorldTimelineItem:
        lat, lng = self._transport_coordinate(leg)
        return WorldTimelineItem(
            id=f"transport-{leg.id}",
            kind="transport",
            title=leg.title,
            detail=leg.timeline_note or leg.detail,
            city=city,
            place_name=leg.destination_name,
            lat=lat,
            lng=lng,
            mode=leg.mode,
            planned_start=leg.scheduled_departure,
            planned_end=leg.scheduled_arrival,
            progress=leg.progress,
            is_current=leg.status in {TransportLegStatus.waiting, TransportLegStatus.boarding, TransportLegStatus.in_transit},
        )

    def _stop_windows(self, stops: list[ItineraryStop], now: datetime) -> list[_StopWindow]:
        local_now = now.astimezone()
        day = local_now.date()
        windows: list[_StopWindow] = []
        for index, stop in enumerate(stops):
            start = self._planned_datetime(stop.planned_time, day, local_now.tzinfo, index)
            windows.append(_StopWindow(stop=stop, start=start, end=start + timedelta(minutes=stop.dwell_minutes)))
        return windows

    def _planned_datetime(self, raw: str | None, day, tzinfo, index: int) -> datetime:
        if raw:
            try:
                hour, minute = [int(part) for part in raw.split(":", 1)]
                return datetime.combine(day, time(hour=hour, minute=minute), tzinfo=tzinfo)
            except (TypeError, ValueError):
                pass
        return datetime.combine(day, time(hour=8, minute=0), tzinfo=tzinfo) + timedelta(hours=index * 2)

    def _next_stop(self, stops: list[ItineraryStop], now: datetime) -> ItineraryStop | None:
        for window in self._stop_windows(stops, now):
            if window.start > now:
                return window.stop
        return None

    def _rest_stop_before_next(self, plan: JourneyPlan, next_stop: ItineraryStop) -> ItineraryStop:
        if not plan.stops:
            return next_stop
        for index, stop in enumerate(plan.stops):
            if stop.id == next_stop.id:
                if index > 0:
                    return plan.stops[index - 1]
                return stop
        return plan.stops[-1]

    def _active_transport(self, legs: list[ScheduledTransportLeg], now: datetime) -> ScheduledTransportLeg | None:
        long_distance_modes = {TravelMode.flight, TravelMode.train, TravelMode.transit, TravelMode.ferry}
        for leg in legs:
            if leg.status == TransportLegStatus.in_transit:
                return leg
            if leg.mode in long_distance_modes and leg.status in {TransportLegStatus.waiting, TransportLegStatus.boarding}:
                return leg
        return None

    def _status_note(self, activity: WorldActivity, active_transport: ScheduledTransportLeg | None) -> str:
        if active_transport:
            if active_transport.status == TransportLegStatus.in_transit:
                return f"正在前往 {active_transport.destination_name}，进度约 {int(active_transport.progress * 100)}%"
            return f"正在为前往 {active_transport.destination_name} 做准备"
        if activity.kind == "movement":
            return f"正在接近 {activity.next_place_name or activity.place_name or '下一站'}"
        if activity.can_generate_photo:
            return "TA 正在等这一刻的光慢慢对上"
        if activity.can_send_postcard:
            return "TA 把这里记成了一封小信"
        return activity.title

    def _transport_status(self, leg: ScheduledTransportLeg) -> JourneyStatus:
        if leg.mode == TravelMode.flight and leg.status == TransportLegStatus.in_transit:
            return JourneyStatus.flying
        if leg.mode == TravelMode.walk:
            return JourneyStatus.walking
        return JourneyStatus.traveling

    def _timeline_status(self, item: WorldTimelineItem) -> JourneyStatus:
        if item.kind == "movement":
            if item.mode == TravelMode.walk:
                return JourneyStatus.walking
            if item.mode == TravelMode.flight:
                return JourneyStatus.flying
            return JourneyStatus.traveling
        if item.kind == "transport":
            if item.mode == TravelMode.flight:
                return JourneyStatus.flying
            if item.mode == TravelMode.walk:
                return JourneyStatus.walking
            return JourneyStatus.traveling
        return JourneyStatus.staying

    def _stop_for_item(self, stops: list[ItineraryStop], item: WorldTimelineItem) -> ItineraryStop | None:
        if item.kind != "stop":
            return None
        return next((stop for stop in stops if stop.id == item.id), None)

    def _place_for_fallback(self, plan: JourneyPlan) -> PlaceSignal:
        if plan.places:
            return plan.places[-1]
        return PlaceSignal(
            id="fallback-place",
            name=plan.city,
            category="city",
            city=plan.city,
            lat=0,
            lng=0,
            activity_hint="安静地待着",
            detail_hint="世界模拟暂时没有更多地点。",
            source=self.provider_name,
        )

    def _transport_coordinate(self, leg: ScheduledTransportLeg) -> tuple[float, float]:
        if leg.route_polyline:
            route_coordinate = self._coordinate_from_polyline(leg.route_polyline, leg.progress)
            if route_coordinate:
                return route_coordinate
        return self._interpolate(
            leg.origin_lat,
            leg.origin_lng,
            leg.destination_lat,
            leg.destination_lng,
            leg.progress,
        )

    def _fallback_coordinate(self, item: WorldTimelineItem, lat: float, lng: float) -> tuple[float, float]:
        return item.lat if item.lat is not None else lat, item.lng if item.lng is not None else lng

    def _route_coordinate(
        self,
        segment: RouteSegment | None,
        origin: ItineraryStop,
        destination: ItineraryStop,
        progress: float,
    ) -> tuple[float, float]:
        if segment and segment.polyline:
            route_coordinate = self._coordinate_from_polyline(segment.polyline, progress)
            if route_coordinate:
                return route_coordinate
        return self._interpolate(origin.lat, origin.lng, destination.lat, destination.lng, progress)

    def _coordinate_from_polyline(self, raw: str, progress: float) -> tuple[float, float] | None:
        points = self._decode_polyline(raw)
        if len(points) < 2:
            return None
        return self._coordinate_along(points, progress)

    def _decode_polyline(self, raw: str) -> list[tuple[float, float]]:
        points = self._decode_lng_lat_polyline(raw)
        if points:
            return points
        return self._decode_google_polyline(raw)

    def _decode_lng_lat_polyline(self, raw: str) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = []
        for chunk in raw.split(";"):
            parts = chunk.strip().split(",", 1)
            if len(parts) != 2:
                return []
            try:
                lng = float(parts[0])
                lat = float(parts[1])
            except ValueError:
                return []
            points.append((lat, lng))
        return points

    def _decode_google_polyline(self, raw: str) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = []
        index = 0
        lat = 0
        lng = 0
        while index < len(raw):
            lat_delta, index = self._decode_google_value(raw, index)
            lng_delta, index = self._decode_google_value(raw, index)
            lat += lat_delta
            lng += lng_delta
            points.append((lat / 1e5, lng / 1e5))
        return points

    def _decode_google_value(self, raw: str, index: int) -> tuple[int, int]:
        result = 0
        shift = 0
        while index < len(raw):
            byte = ord(raw[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        value = ~(result >> 1) if result & 1 else result >> 1
        return value, index

    def _coordinate_along(self, points: list[tuple[float, float]], progress: float) -> tuple[float, float]:
        progress = max(0.0, min(1.0, progress))
        distances = [
            self._rough_distance(start, end)
            for start, end in zip(points, points[1:])
        ]
        total = sum(distances)
        if total <= 0:
            return points[0]
        target = total * progress
        walked = 0.0
        for index, distance in enumerate(distances):
            if walked + distance >= target:
                local_progress = 0.0 if distance <= 0 else (target - walked) / distance
                start = points[index]
                end = points[index + 1]
                return self._interpolate(start[0], start[1], end[0], end[1], local_progress)
            walked += distance
        return points[-1]

    def _rough_distance(self, start: tuple[float, float], end: tuple[float, float]) -> float:
        avg_lat = ((start[0] + end[0]) / 2) * pi / 180
        lat_meters = (end[0] - start[0]) * 111_320
        lng_meters = (end[1] - start[1]) * 111_320 * cos(avg_lat)
        return sqrt(lat_meters * lat_meters + lng_meters * lng_meters)

    def _interpolate(self, start_lat: float, start_lng: float, end_lat: float, end_lng: float, progress: float) -> tuple[float, float]:
        progress = max(0.0, min(1.0, progress))
        return (
            start_lat + (end_lat - start_lat) * progress,
            start_lng + (end_lng - start_lng) * progress,
        )

    def _progress(self, now: datetime, start: datetime, end: datetime) -> float:
        total = max(1.0, (end - start).total_seconds())
        elapsed = (now - start).total_seconds()
        return round(max(0.0, min(1.0, elapsed / total)), 3)

    def _energy(self, status: JourneyStatus, elapsed: int) -> int:
        base = 64 if status in {JourneyStatus.traveling, JourneyStatus.flying, JourneyStatus.walking} else 76
        return self._clamp(base + self._wave(elapsed, 15, 5), 20, 99)

    def _curiosity(self, activity: WorldActivity, elapsed: int) -> int:
        base = 78 if activity.kind in {"movement", "transport"} else 70
        if activity.can_generate_photo or activity.can_send_postcard:
            base += 6
        return self._clamp(base + self._wave(elapsed + 8, 20, 4), 20, 99)

    def _wave(self, elapsed: float, period: float, amplitude: int) -> int:
        return int(round(sin((elapsed / period) * 2 * pi) * amplitude))

    def _clamp(self, value: int, lower: int, upper: int) -> int:
        return max(lower, min(upper, value))

    def _icon_hint(self, mode: TravelMode | None) -> str:
        if mode == TravelMode.flight:
            return "airplane"
        if mode == TravelMode.train:
            return "train"
        if mode == TravelMode.drive:
            return "car"
        if mode == TravelMode.transit:
            return "bus"
        if mode == TravelMode.ferry:
            return "ferry"
        if mode == TravelMode.walk:
            return "pawprint"
        return "mappin"

    def _aware(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


def build_world_simulation_engine(settings: Settings) -> WorldSimulationEngine:
    return WorldSimulationEngine(settings)
