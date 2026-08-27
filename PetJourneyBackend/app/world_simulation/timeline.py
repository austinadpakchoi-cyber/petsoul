"""世界模拟时间线 mixin：时间线组装、polyline 解码与坐标插值。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from math import cos, pi, sqrt
from zoneinfo import ZoneInfo

from ..city_timezones import timezone_for_city
from ..schemas import (
    ItineraryStop,
    JourneyPlan,
    JourneyStatus,
    PlaceSignal,
    RouteSegment,
    ScheduledTransportLeg,
    TransportLegStatus,
    TravelMode,
    WorldTimelineItem,
)


@dataclass(frozen=True)
class _StopWindow:
    stop: ItineraryStop
    start: datetime
    end: datetime


class WorldSimulationTimelineMixin:
    def _timeline(self, plan: JourneyPlan, now: datetime) -> list[WorldTimelineItem]:
        windows = self._stop_windows(plan.stops, now, city_name=plan.city)
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
    def _stop_windows(self, stops: list[ItineraryStop], now: datetime, *, city_name: str | None = None) -> list[_StopWindow]:
        # 行程窗口必须按「TA 所在城市」的墙上时间划分，而不是宿主机时区
        # （CI 是 UTC、生产也是 UTC，裸 now.astimezone() 会让 TA 的活动漂移 8 小时）。
        local_now = now.astimezone(ZoneInfo(timezone_for_city(city_name)))
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
    def _next_stop(self, stops: list[ItineraryStop], now: datetime, *, city_name: str | None = None) -> ItineraryStop | None:
        for window in self._stop_windows(stops, now, city_name=city_name):
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
