"""路线规划协议与通用处理（架构审计 P1-2 包化）。"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ..place_display import display_name
from ..providers import JourneyCity
from ..schemas import (
    JourneyPlan,
    JourneyRoutePlan,
    RouteSegment,
    RouteStep,
    TransportDecision,
    TravelMode,
)
from ..storage import PetRecord

class TravelRoutePlanner(Protocol):
    provider_name: str

    def build_journey_plan(self, pet: PetRecord, city: JourneyCity, now: datetime) -> JourneyPlan:
        ...

    def build_route_plan(self, pet: PetRecord, city: JourneyCity, now: datetime) -> JourneyRoutePlan:
        ...


# 各交通方式的最快巡航速度（米/秒）与最短时长（秒）：任何腿的时长都不得快于
# 距离/速度推出的下限，杜绝"瞬移"。
_MODE_SPEED_FLOORS: dict[TravelMode, tuple[float, int]] = {
    TravelMode.walk: (1.6, 60),
    TravelMode.drive: (22.0, 120),
    TravelMode.transit: (16.0, 180),
    TravelMode.train: (60.0, 300),
    TravelMode.flight: (260.0, 1800),
}

def enforce_transport_reality(plan: JourneyPlan) -> JourneyPlan:
    """展示前的世界规则校验：地名走展示规则，交通腿时长不得低于物理下限。"""
    segments: list[RouteSegment] = []
    for segment in plan.route_segments:
        updated: dict = {}
        floor = _MODE_SPEED_FLOORS.get(segment.mode)
        if floor and segment.distance_meters:
            speed, minimum = floor
            min_duration = max(int(segment.distance_meters / speed), minimum)
            if (segment.duration_seconds or 0) < min_duration:
                updated["duration_seconds"] = min_duration
        segments.append(segment.model_copy(update=updated) if updated else segment)

    stops = [
        stop.model_copy(update={"name": display_name(stop.name)})
        if display_name(stop.name) != stop.name
        else stop
        for stop in plan.stops
    ]
    places = [
        place.model_copy(update={"name": display_name(place.name)})
        if display_name(place.name) != place.name
        else place
        for place in plan.places
    ]
    return plan.model_copy(update={"route_segments": segments, "stops": stops, "places": places})

def adapt_journey_plan_to_route_plan(plan: JourneyPlan) -> JourneyRoutePlan:
    steps: list[RouteStep] = []
    for stop in plan.stops:
        steps.append(
            RouteStep(
                id=f"{stop.id}-stay",
                mode=TravelMode.stay.value,
                title=stop.title,
                detail=stop.detail,
                from_place=stop.name,
            )
        )
    for segment in plan.route_segments:
        steps.append(
            RouteStep(
                id=segment.id,
                mode=segment.mode.value,
                title=segment.title,
                detail=segment.detail,
                start_time=segment.start_time,
                end_time=segment.end_time,
                from_place=segment.from_place,
                to_place=segment.to_place,
            )
        )
    return JourneyRoutePlan(
        pet_id=plan.pet_id,
        city=plan.city,
        generated_at=plan.generated_at,
        provider=plan.provider,
        steps=steps,
        places=plan.places,
    )
