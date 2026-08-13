from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import Field

from .base import PetJourneyBaseModel, TravelMode
from .economy import SouvenirItem
from .pet import ScheduledTransportLeg
from .place import PlaceSignal


class TravelQuestStatus(str, Enum):
    suggested = "suggested"
    thinking = "thinking"
    guide_ready = "guide_ready"
    preparing = "preparing"
    outbound = "outbound"
    traveling = "traveling"
    arrived = "arrived"
    onsite_exploring = "onsite_exploring"
    watching_event = "watching_event"
    post_event_rest = "post_event_rest"
    return_planning = "return_planning"
    return_traveling = "return_traveling"
    returned = "returned"
    continued_elsewhere = "continued_elsewhere"
    declined = "declined"
    completed = "completed"


class TravelQuestType(str, Enum):
    open_destination = "open_destination"
    worldcup = "worldcup"
    city_trip = "city_trip"


class TravelQuestTripType(str, Enum):
    round_trip = "round_trip"
    one_way = "one_way"
    multi_city = "multi_city"
    open_ended = "open_ended"


class TravelQuestReturnPolicy(str, Enum):
    return_to_origin = "return_to_origin"
    continue_journey = "continue_journey"
    ask_after_event = "ask_after_event"


class TravelGuideResearchProvider(str, Enum):
    mock = "mock"
    doubao_social = "doubao_social"
    openai_web_search = "openai_web_search"
    hybrid = "hybrid"


class SocialTravelFinding(PetJourneyBaseModel):
    claim: str
    evidence_type: str = "route_tip"
    mentioned_places: list[str] = Field(default_factory=list)
    sentiment: str = "mixed"
    usefulness: float = 0.5
    risk: str | None = None
    suggested_time: str | None = None
    tags: list[str] = Field(default_factory=list)
    evidence_level: str = "medium"
    source_type: str = "social_travel_notes"
    recency: str = "recent_or_unknown"
    confidence: float = 0.5
    should_verify_with_map: bool = True


class PlaceEvidenceScores(PetJourneyBaseModel):
    city_signature: float = 0.0
    local_food_value: float = 0.0
    photo_potential: float = 0.0
    pet_fit: float = 0.5
    crowd_penalty: float = 0.0
    chain_store_penalty: float = 0.0
    overhyped_penalty: float = 0.0
    confidence: float = 0.5


class PlaceEvidencePacket(PetJourneyBaseModel):
    canonical_place_id: str
    name: str
    city: str
    lat: float | None = None
    lng: float | None = None
    coordinate_source: str | None = None
    source_priority: list[str] = Field(default_factory=list)
    provider_evidence: dict[str, Any] = Field(default_factory=dict)
    derived_scores: PlaceEvidenceScores = Field(default_factory=PlaceEvidenceScores)
    eligible_roles: list[str] = Field(default_factory=list)
    user_visible: bool = True
    needs_verification: bool = True
    verification_status: str = "social_only_needs_map_verification"
    evidence_notes: list[str] = Field(default_factory=list)


class TravelAnchor(PetJourneyBaseModel):
    city: str
    place_name: str
    lat: float
    lng: float
    note: str


class TravelWishRequest(PetJourneyBaseModel):
    message: str = Field(min_length=1, max_length=600)
    destination: str | None = None
    event_name: str | None = None
    preferred_start_date: date | None = None
    force: bool = False


class TravelQuestStop(PetJourneyBaseModel):
    id: str
    city: str
    name: str
    role: str
    planned_time: str | None = None
    dwell_minutes: int
    pet_voice: str
    owner_tip: str
    source_notes: list[str] = Field(default_factory=list)


class TravelQuestTransportOutline(PetJourneyBaseModel):
    mode: TravelMode
    from_place: str
    to_place: str
    estimated_duration: str
    reality_level: str
    note: str


class TravelGuideResearch(PetJourneyBaseModel):
    provider: TravelGuideResearchProvider
    provider_name: str
    destination_region: str
    query: str
    strategy: str
    findings: list[str]
    research_brief: dict[str, Any] = Field(default_factory=dict)
    social_findings: list[SocialTravelFinding] = Field(default_factory=list)
    evidence_packets: list[PlaceEvidencePacket] = Field(default_factory=list)
    fact_provider_priority: list[str] = Field(default_factory=list)
    quality_gate_notes: list[str] = Field(default_factory=list)
    orchestration_roles: list[str] = Field(default_factory=list)
    pipeline_steps: list[str] = Field(default_factory=list)
    quality_gate_rules: list[str] = Field(default_factory=list)
    voice_writer: str = "local_pet_voice_template"
    deep_critic: str = "rules_only_critic"
    deep_critic_required: bool = False
    can_inform_replicable_route: bool = False
    recommended_sources: list[str]
    missing_capabilities: list[str] = Field(default_factory=list)
    generated_at: datetime


class TravelQuestGuide(PetJourneyBaseModel):
    id: str
    title: str
    summary: str
    pet_voice: str
    route_theme: str
    cities: list[str]
    stops: list[TravelQuestStop]
    transport_outline: list[TravelQuestTransportOutline]
    preparation_notes: list[str]
    source_notes: list[str]
    research: TravelGuideResearch | None = None
    generated_at: datetime
    provider: str


class TravelQuestNextOption(PetJourneyBaseModel):
    id: str
    title: str
    decision_type: str
    destination: str
    pet_voice: str
    owner_visible_reason: str
    transport_outline: list[TravelQuestTransportOutline]
    recommended: bool = False


class TravelQuestDecisionRequest(PetJourneyBaseModel):
    option_id: str | None = None
    owner_message: str | None = Field(default=None, max_length=600)


class TravelBagItemType(str, Enum):
    snack = "snack"
    comfort_item = "comfort_item"
    guide_hint = "guide_hint"
    lucky_charm = "lucky_charm"
    music_hint = "music_hint"
    toy = "toy"


class TravelBagItemInput(PetJourneyBaseModel):
    item_type: TravelBagItemType
    title: str = Field(min_length=1, max_length=40)
    note: str | None = Field(default=None, max_length=180)
    influence_tags: list[str] = Field(default_factory=list, max_length=6)


class TravelBagPackRequest(PetJourneyBaseModel):
    quest_id: str | None = None
    items: list[TravelBagItemInput] = Field(default_factory=list, max_length=8)
    owner_message: str | None = Field(default=None, max_length=240)


class TravelBagItem(PetJourneyBaseModel):
    id: str
    item_type: TravelBagItemType
    title: str
    note: str | None = None
    influence_tags: list[str] = Field(default_factory=list)
    added_at: datetime
    source: str = "owner"


class TravelBag(PetJourneyBaseModel):
    id: str
    pet_id: str
    quest_id: str | None = None
    items: list[TravelBagItem] = Field(default_factory=list)
    owner_message: str | None = None
    pet_visible_note: str
    updated_at: datetime


class RouteStep(PetJourneyBaseModel):
    id: str
    mode: str
    title: str
    detail: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    from_place: str | None = None
    to_place: str | None = None


class JourneyRoutePlan(PetJourneyBaseModel):
    pet_id: str
    city: str
    generated_at: datetime
    provider: str
    steps: list[RouteStep]
    places: list[PlaceSignal]


class RouteSegment(PetJourneyBaseModel):
    id: str
    mode: TravelMode
    title: str
    detail: str
    from_place: str
    to_place: str
    distance_meters: int | None = None
    duration_seconds: int | None = None
    provider: str
    polyline: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    is_simulated: bool = True


class ItineraryStop(PetJourneyBaseModel):
    id: str
    name: str
    category: str
    city: str
    lat: float
    lng: float
    title: str
    detail: str
    planned_time: str | None = None
    dwell_minutes: int
    postcard_candidate: bool = False
    photo_candidate: bool = False
    source: str = "mock"


class TransportDecision(PetJourneyBaseModel):
    selected_mode: TravelMode
    reason: str
    rejected_modes: list[TravelMode] = Field(default_factory=list)
    autonomy_note: str


class JourneyPlan(PetJourneyBaseModel):
    pet_id: str
    city: str
    generated_at: datetime
    provider: str
    horizon_hours: int
    summary: str
    current_activity: str
    transport_decision: TransportDecision
    route_segments: list[RouteSegment]
    scheduled_transport: list[ScheduledTransportLeg] = Field(default_factory=list)
    stops: list[ItineraryStop]
    places: list[PlaceSignal]
    next_postcard_hint: str | None = None
    worldcup_event: bool = False


class TravelQuest(PetJourneyBaseModel):
    id: str
    pet_id: str
    quest_type: TravelQuestType
    status: TravelQuestStatus
    current_phase: TravelQuestStatus = TravelQuestStatus.guide_ready
    trip_type: TravelQuestTripType = TravelQuestTripType.round_trip
    return_policy: TravelQuestReturnPolicy = TravelQuestReturnPolicy.ask_after_event
    origin_anchor: TravelAnchor | None = None
    owner_message: str
    destination: str
    event_name: str | None = None
    preferred_start_date: date | None = None
    autonomy_decision: str
    current_phase_message: str
    guide: TravelQuestGuide | None = None
    travel_bag: TravelBag | None = None
    journey_plan: JourneyPlan | None = None
    post_event_options: list[TravelQuestNextOption] = Field(default_factory=list)
    souvenir_preview: list[SouvenirItem] = Field(default_factory=list)
    selected_next_option_id: str | None = None
    worldcup_event: bool = False
    created_at: datetime
    updated_at: datetime


__all__ = [
    "TravelQuestStatus",
    "TravelQuestType",
    "TravelQuestTripType",
    "TravelQuestReturnPolicy",
    "TravelGuideResearchProvider",
    "SocialTravelFinding",
    "PlaceEvidenceScores",
    "PlaceEvidencePacket",
    "TravelAnchor",
    "TravelWishRequest",
    "TravelQuestStop",
    "TravelQuestTransportOutline",
    "TravelGuideResearch",
    "TravelQuestGuide",
    "TravelQuestNextOption",
    "TravelQuestDecisionRequest",
    "TravelBagItemType",
    "TravelBagItemInput",
    "TravelBagPackRequest",
    "TravelBagItem",
    "TravelBag",
    "RouteStep",
    "JourneyRoutePlan",
    "RouteSegment",
    "ItineraryStop",
    "TransportDecision",
    "JourneyPlan",
    "TravelQuest",
]
