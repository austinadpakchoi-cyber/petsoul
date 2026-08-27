from __future__ import annotations

import re

from ..city_timezones import local_wall_time
from ..schemas import AgentStatus, TravelMode, WorldSimulationSnapshot
from .schemas import CommunicatorWorldSnapshot


def _slug(value: str) -> str:
    clean = re.sub(r"\s+", "_", value.strip().lower())
    clean = re.sub(r"[^a-z0-9_\-\u4e00-\u9fff]+", "", clean)
    return clean or "scene"


class CommunicatorWorldSnapshotBuilder:
    provider_name = "communicator-world-snapshot-builder"

    def build(self, *, status: AgentStatus, world: WorldSimulationSnapshot) -> CommunicatorWorldSnapshot:
        activity = world.current_activity
        mode = activity.mode or (TravelMode.flight if world.status.value == "flying" else None)
        animation_hint = world.life_tick.animation_hint if world.life_tick else activity.icon_hint
        place_name = activity.place_name or (world.next_stop.name if world.next_stop else None)
        scene_anchor = "_".join(
            part for part in [
                world.city,
                place_name or activity.title,
                animation_hint,
            ] if part
        )
        local_hour = local_wall_time(world.generated_at, world.city).hour
        is_flying = world.status.value == "flying" or mode == TravelMode.flight
        is_sleeping = animation_hint == "sleep" or "睡" in activity.title or "睡" in activity.detail
        is_in_transit = activity.kind == "transport" or mode in {
            TravelMode.drive,
            TravelMode.transit,
            TravelMode.train,
            TravelMode.flight,
            TravelMode.ferry,
        }
        return CommunicatorWorldSnapshot(
            pet_id=status.pet_id,
            city=world.city,
            place_name=place_name,
            scene_anchor=scene_anchor,
            scene_hash=f"{_slug(scene_anchor)}_{local_hour}",
            journey_status=world.status,
            travel_mode=mode,
            activity_type=activity.kind,
            can_generate_photo=bool(activity.can_generate_photo and not is_flying and not is_sleeping),
            animation_hint=animation_hint,
            energy=world.energy,
            happiness=world.happiness,
            curiosity=world.curiosity,
            weather=world.weather,
            local_hour=local_hour,
            is_sleeping=is_sleeping,
            is_in_transit=is_in_transit,
            is_flying=is_flying,
            lat=activity.lat,
            lng=activity.lng,
        )
