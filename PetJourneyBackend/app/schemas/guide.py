from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import Field

from .base import PetJourneyBaseModel
from .pet import ScheduledTransportLeg


class PetGuideStop(PetJourneyBaseModel):
    id: str
    place_id: str
    name: str
    category: str
    role: str = "core_anchor"
    is_core: bool = True
    is_user_visible: bool = True
    city: str
    lat: float
    lng: float
    planned_time: str | None = None
    dwell_minutes: int
    pet_reason: str
    owner_tip: str
    rating: float | None = None
    photo_url: str | None = None
    distance_meters: int | None = None
    guide_score: float | None = None
    source: str


class PetPlaceScore(PetJourneyBaseModel):
    place_id: str
    city_signature: float = 0.0
    route_coherence: float = 0.0
    pet_dna_fit: float
    memory_hook: float
    route_feasibility: float
    photo_potential: float
    emotional_softness: float
    local_food_value: float = 0.0
    novelty: float
    weather_fit: float
    crowd_noise_penalty: float
    chain_store_penalty: float = 0.0
    duplicate_category_penalty: float = 0.0
    overstay_penalty: float = 0.0
    total: float
    reasons: list[str] = Field(default_factory=list)


class PetGuideSelectedPlace(PetJourneyBaseModel):
    place_id: str
    name: str
    category: str
    city: str
    score: PetPlaceScore
    why_pet_likes_it: str
    why_owner_may_care: str
    photo_potential: str
    crowd_risk: str


class PetAuthoredGuide(PetJourneyBaseModel):
    pet_id: str
    city: str
    generated_at: datetime
    provider: str
    model: str
    title: str
    animal_text: str
    translation: str
    language_style: str
    route_theme: str
    mood: str
    guide_stops: list[PetGuideStop]
    scheduled_transport: list[ScheduledTransportLeg] = Field(default_factory=list)
    source_places_count: int
    autonomy_note: str = "这是 TA 自己根据真实地点和性格做出的游玩计划，用户可以参考，但不控制 TA 的喜好。"
    quality_score: float = 0.0
    is_replicable_route: bool = False
    quality_notes: list[str] = Field(default_factory=list)
    guide_theme: str | None = None
    selected_places: list[PetGuideSelectedPlace] = Field(default_factory=list)
    why_pet_likes_it: list[str] = Field(default_factory=list)
    why_owner_may_care: list[str] = Field(default_factory=list)
    photo_potential: list[str] = Field(default_factory=list)
    crowd_risk: list[str] = Field(default_factory=list)
    pet_first_person_guide: str | None = None
    orchestration_roles: list[str] = Field(default_factory=list)
    quality_gate_rules: list[str] = Field(default_factory=list)
    voice_provider: str = "local_pet_voice_template"
    critic_provider: str = "rules_only_critic"
    fact_provider_priority: list[str] = Field(default_factory=list)


class IllustratedGuideStatus(str, Enum):
    prompt_ready = "prompt_ready"
    generating = "generating"
    ready = "ready"
    failed = "failed"


class IllustratedGuideStop(PetJourneyBaseModel):
    index: int
    time: str | None = None
    name: str
    label: str
    short_note: str
    category: str


class IllustratedGuidePage(PetJourneyBaseModel):
    index: int
    title: str
    subtitle: str
    intent: str
    page_type: str = "cover"
    template_id: str = "sketchbook_route"
    visual_style: str = "手绘旅行手账"
    composition: str = "loose_page"
    style_id: str = "warm_travel_journal"
    style_name: str = "温柔手账风"
    image_prompt: str
    image_url: str | None = None
    thumbnail_url: str | None = None
    status: IllustratedGuideStatus = IllustratedGuideStatus.prompt_ready


class IllustratedGuide(PetJourneyBaseModel):
    id: str
    pet_id: str
    city: str
    date: date
    status: IllustratedGuideStatus
    title: str
    theme: str
    pet_name: str
    pet_thought: str
    stops: list[IllustratedGuideStop]
    style: str = "loose_handdrawn_travel_journal"
    style_id: str = "warm_travel_journal"
    style_name: str = "温柔手账风"
    style_pack_version: str = "2026-07-04-mvp1"
    style_locked: bool = True
    layout_mode: str = "multi_page_sketchbook"
    pages: list[IllustratedGuidePage] = Field(default_factory=list)
    source_itinerary_id: str
    image_prompt: str
    image_url: str | None = None
    thumbnail_url: str | None = None
    provider: str
    model: str | None = None
    error_message: str | None = None
    created_at: datetime


__all__ = [
    "PetGuideStop",
    "PetPlaceScore",
    "PetGuideSelectedPlace",
    "PetAuthoredGuide",
    "IllustratedGuideStatus",
    "IllustratedGuideStop",
    "IllustratedGuidePage",
    "IllustratedGuide",
]
