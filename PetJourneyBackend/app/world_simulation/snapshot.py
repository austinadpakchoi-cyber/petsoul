"""世界模拟快照 mixin：快照组装、活动判定与状态量。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import pi, sin

from ..config import Settings
from ..providers import JourneyCity
from ..schemas import (
    ItineraryStop,
    JourneyPlan,
    JourneyStatus,
    ScheduledTransportLeg,
    TransportLegStatus,
    TravelMode,
    WorldActivity,
    WorldSimulationSnapshot,
    WorldTimelineItem,
)
from ..storage import PetRecord


class WorldSimulationSnapshotMixin:
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
        next_stop = self._next_stop(plan.stops, now, city_name=plan.city)

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
                "通讯器原则：iOS 展示 TA 正在生活，不把地图做成命令式导航。",
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
