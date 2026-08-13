from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .base import JourneyStatus, PetJourneyBaseModel, TravelMode
from .memory import MemoryRecord
from .pet import ScheduledTransportLeg
from .place import PlaceSignal
from .travel import ItineraryStop


class WorldTimelineItem(PetJourneyBaseModel):
    id: str
    kind: str
    title: str
    detail: str
    city: str
    place_name: str | None = None
    lat: float | None = None
    lng: float | None = None
    mode: TravelMode | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    progress: float = 0.0
    is_current: bool = False


class WorldActivity(PetJourneyBaseModel):
    id: str
    kind: str
    status: JourneyStatus
    title: str
    detail: str
    city: str
    place_name: str | None = None
    lat: float
    lng: float
    mode: TravelMode | None = None
    started_at: datetime | None = None
    ends_at: datetime | None = None
    progress: float = 0.0
    dwell_minutes: int | None = None
    next_place_name: str | None = None
    icon_hint: str
    can_generate_photo: bool = False
    can_send_postcard: bool = False
    source: str
    current_transport_id: str | None = None


class PetNeedState(PetJourneyBaseModel):
    energy: int
    hunger: int
    thirst: int = 0
    sleepiness: int = 0
    sensory_load: int = 0
    heat_stress: int = 0
    social: int
    curiosity: int
    comfort: int
    playfulness: int
    primary_need: str = "observe"


class WorldObservation(PetJourneyBaseModel):
    pet_id: str
    city: str
    weather: str
    local_time: datetime
    current_activity: WorldActivity
    nearby_places: list[PlaceSignal]
    active_transport: ScheduledTransportLeg | None = None
    constraints: list[str]


class PetIntent(PetJourneyBaseModel):
    id: str
    kind: str
    title: str
    reason: str
    confidence: float
    suggested_place_name: str | None = None
    owner_signal: str | None = None


class WorldAction(PetJourneyBaseModel):
    id: str
    action_type: str
    title: str
    detail: str
    mode: TravelMode
    place_name: str | None = None
    lat: float
    lng: float
    duration_minutes: int
    animation_hint: str
    photo_opportunity: bool = False
    message_opportunity: bool = False


class GameMasterDecision(PetJourneyBaseModel):
    allowed: bool
    reason: str
    adjusted: bool = False
    blocked_reasons: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)


class PetVisibleThought(PetJourneyBaseModel):
    current_inner_voice: str
    next_intention: str
    reason: str
    time_window: str
    confidence: float
    owner_message_echo: str | None = None


class LifeTickResult(PetJourneyBaseModel):
    pet_id: str
    generated_at: datetime
    provider: str
    observation: WorldObservation
    retrieved_memories: list[MemoryRecord]
    need_state: PetNeedState
    intent: PetIntent
    action: WorldAction
    decision: GameMasterDecision
    owner_visible_summary: str
    visible_thought: PetVisibleThought
    animal_text_hint: str
    animation_hint: str
    should_notify_owner: bool
    next_tick_after_seconds: int


class WorldSimulationSnapshot(PetJourneyBaseModel):
    pet_id: str
    city: str
    generated_at: datetime
    provider: str
    elapsed_seconds: int
    travel_day: int
    weather: str
    status: JourneyStatus
    status_note: str
    energy: int
    happiness: int
    curiosity: int
    current_activity: WorldActivity
    active_transport: ScheduledTransportLeg | None = None
    next_stop: ItineraryStop | None = None
    timeline: list[WorldTimelineItem]
    rules: list[str]
    life_tick: LifeTickResult | None = None


__all__ = [
    "WorldTimelineItem",
    "WorldActivity",
    "PetNeedState",
    "WorldObservation",
    "PetIntent",
    "WorldAction",
    "GameMasterDecision",
    "PetVisibleThought",
    "LifeTickResult",
    "WorldSimulationSnapshot",
]
