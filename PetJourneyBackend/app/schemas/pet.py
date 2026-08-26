from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from .base import JourneyStatus, PetJourneyBaseModel, PetType, TransportLegStatus, TravelMode


class PetDNA(PetJourneyBaseModel):
    owner_title: str = Field(default="妈妈")
    personality: str = Field(default="温柔")
    favorite_places: list[str] = Field(default_factory=lambda: ["海边", "草地"])
    hobby: list[str] = Field(default_factory=lambda: ["散步", "晒太阳"])
    catchphrase: str = Field(default="我在路上，也在想你")
    emoji_pref: str = Field(default="soft")
    voice_style: str = Field(default="轻轻的、像寄信")


class CreatePetResponse(PetJourneyBaseModel):
    success: bool
    pet_id: str
    name: str
    location: str
    photo_url: str | None = None
    message: str


class JourneyThought(PetJourneyBaseModel):
    id: str
    text: str
    timestamp: datetime
    tone: str
    animal_text: str | None = None
    translation_available: bool = False
    translation: str | None = None
    language_style: str = "human"
    model: str | None = None


class ThoughtTranslation(PetJourneyBaseModel):
    thought_id: str
    pet_id: str
    animal_text: str
    translation: str
    tone: str
    language_style: str
    model: str | None = None


class JourneyEvent(PetJourneyBaseModel):
    id: str
    title: str
    detail: str
    timestamp: datetime


class Postcard(PetJourneyBaseModel):
    id: str
    location: str
    text: str
    weather: str
    happiness: int
    timestamp: datetime
    image_url: str | None = None
    is_new: bool = True


class DeviceRegistrationRequest(PetJourneyBaseModel):
    pet_id: str
    device_token: str
    platform: str = "ios"
    environment: str = "sandbox"


class DeviceRegistrationResponse(PetJourneyBaseModel):
    success: bool
    device_id: str
    provider: str
    message: str


class NotificationDelivery(PetJourneyBaseModel):
    id: str
    pet_id: str
    device_token: str | None = None
    title: str
    body: str
    category: str
    provider: str
    status: str
    timestamp: datetime
    error: str | None = None


class SchedulerTickResult(PetJourneyBaseModel):
    provider: str
    started_at: datetime
    finished_at: datetime
    pets_seen: int
    agent_turns: int
    notifications_sent: int
    errors: list[str] = Field(default_factory=list)


class SchedulerConfig(PetJourneyBaseModel):
    enabled: bool
    interval_seconds: float
    provider: str
    running: bool
    notification_provider: str
    memory_provider: str


class EngineStepTrace(PetJourneyBaseModel):
    name: str
    status: str = "ok"
    started_at: datetime
    finished_at: datetime
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    fallback: str | None = None


class JourneyEngineTrace(PetJourneyBaseModel):
    id: str
    pet_id: str
    operation: str
    status: str = "ok"
    started_at: datetime
    finished_at: datetime
    steps: list[EngineStepTrace] = Field(default_factory=list)
    state_before: dict[str, Any] = Field(default_factory=dict)
    state_after: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    fallbacks: list[str] = Field(default_factory=list)


class AgentState(PetJourneyBaseModel):
    location: str
    travel_day: int
    weather: str
    status: JourneyStatus
    status_note: str
    energy: int
    happiness: int
    curiosity: int
    latest_thought: JourneyThought | None = None
    thoughts: list[JourneyThought]


class AgentStatus(PetJourneyBaseModel):
    pet_id: str
    name: str
    pet_type: PetType | None
    status: JourneyStatus
    agent_state: AgentState
    daily_logs: list[str]
    reflections: list[str]
    flight_number: str | None = None
    can_message: bool = True
    farewell_ready: bool = False
    postcards: list[Postcard]


class DayPlanItem(PetJourneyBaseModel):
    id: str
    time: str
    title: str
    detail: str
    kind: str


class ScheduledTransportLeg(PetJourneyBaseModel):
    id: str
    mode: TravelMode
    status: TransportLegStatus
    title: str
    detail: str
    origin_name: str
    destination_name: str
    origin_lat: float
    origin_lng: float
    destination_lat: float
    destination_lng: float
    scheduled_departure: datetime
    scheduled_arrival: datetime
    actual_departure: datetime | None = None
    actual_arrival: datetime | None = None
    carrier: str | None = None
    service_number: str | None = None
    terminal_or_platform: str | None = None
    distance_meters: int | None = None
    duration_seconds: int | None = None
    route_polyline: str | None = None
    progress: float = 0.0
    provider: str
    reality_level: str = "mock_schedule"
    is_simulated: bool = True
    timeline_note: str | None = None
    source_urls: list[str] = Field(default_factory=list)
    confidence: str | None = None
    search_query: str | None = None


class DayPlan(PetJourneyBaseModel):
    id: str
    location: str
    view_mode: str
    stay_duration: str
    day_plan: list[DayPlanItem]
    scheduled_transport: list[ScheduledTransportLeg] = Field(default_factory=list)
    thoughts: list[JourneyThought]
    events_today: list[JourneyEvent]


class CityPosition(PetJourneyBaseModel):
    city: str
    lat: float
    lng: float


class FeedbackResponse(PetJourneyBaseModel):
    success: bool
    message: str
    updated_status: AgentStatus | None = None


class OwnerMessageRequest(PetJourneyBaseModel):
    message: str = Field(min_length=1, max_length=500)
    intent_hint: str | None = None
    # 客户端生成、重发复用的幂等键：同 (pet_id, client_message_id) 只处理一次
    client_message_id: str | None = None


class OwnerIntentResult(PetJourneyBaseModel):
    intent: str
    strength: float
    entities: dict[str, Any] = Field(default_factory=dict)
    should_affect_route: bool = False
    should_write_memory: bool = True
    response_policy: str = "gentle_acknowledgement"
    decision: str = "remembered"
    safety_notes: list[str] = Field(default_factory=list)


class OwnerMessageResponse(PetJourneyBaseModel):
    success: bool
    decision: str
    message: str
    thought: JourneyThought
    updated_status: AgentStatus | None = None
    owner_intent: OwnerIntentResult | None = None


__all__ = [
    "PetDNA",
    "CreatePetResponse",
    "JourneyThought",
    "ThoughtTranslation",
    "JourneyEvent",
    "Postcard",
    "DeviceRegistrationRequest",
    "DeviceRegistrationResponse",
    "NotificationDelivery",
    "SchedulerTickResult",
    "SchedulerConfig",
    "EngineStepTrace",
    "JourneyEngineTrace",
    "AgentState",
    "AgentStatus",
    "DayPlanItem",
    "ScheduledTransportLeg",
    "DayPlan",
    "CityPosition",
    "FeedbackResponse",
    "OwnerMessageRequest",
    "OwnerIntentResult",
    "OwnerMessageResponse",
]
