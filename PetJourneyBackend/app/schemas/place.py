from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from .base import PetJourneyBaseModel


class PlaceSignal(PetJourneyBaseModel):
    id: str
    name: str
    category: str
    city: str
    lat: float
    lng: float
    activity_hint: str
    detail_hint: str
    source: str = "mock"
    rating: float | None = None
    cost: str | None = None
    photo_url: str | None = None
    business_area: str | None = None
    distance_meters: int | None = None
    guide_score: float | None = None
    guide_reason: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class PhotoPerspective(str, Enum):
    first_person_selfie = "first_person_selfie"
    passerby_third_person = "passerby_third_person"
    communicator_view = "communicator_view"


class PetCredentialKind(str, Enum):
    identity = "identity"
    passport = "passport"
    health_record = "health_record"
    driver_license = "driver_license"
    boarding_pass = "boarding_pass"
    hotel_key = "hotel_key"


class PetCredentialPrompt(PetJourneyBaseModel):
    kind: PetCredentialKind
    title: str
    subtitle: str
    serial: str
    image_prompt: str
    size: str = "1536x1024"
    reference_roles: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    fields: dict[str, str] = Field(default_factory=dict)


class PlaceInteraction(PetJourneyBaseModel):
    id: str
    pet_id: str
    place: PlaceSignal
    interaction_type: str
    title: str
    detail: str
    pet_action: str
    emotional_tone: str
    dwell_minutes: int
    can_generate_photo: bool = True
    source: str


class PhotoQualityReport(PetJourneyBaseModel):
    pet_identity_score: float
    place_recognition_score: float
    emotional_tone_score: float
    policy_safety: bool
    logo_brand_risk: float
    uncanny_risk: float
    retry_reason: str | None = None
    failure_category: str | None = None
    evaluator: str = "heuristic-photo-quality-evaluator"


class PhotoMission(PetJourneyBaseModel):
    id: str
    pet_id: str
    generated_at: datetime
    provider: str
    city: str
    place: PlaceSignal
    interaction: PlaceInteraction
    camera_perspective: PhotoPerspective
    scene_anchor: str
    landmark_hints: list[str]
    local_detail_hints: list[str]
    crowd_hints: list[str] = Field(default_factory=list)
    weather: str
    time_of_day: str
    image_prompt: str
    postcard_text: str
    safety_notes: list[str] = Field(default_factory=list)
    prompt_blocks: dict[str, str] = Field(default_factory=dict)
    quality_report: PhotoQualityReport | None = None
    retry_count: int = 0
    failure_category: str | None = None


class MapSearchTip(PetJourneyBaseModel):
    id: str | None = None
    name: str
    district: str | None = None
    adcode: str | None = None
    address: str | None = None
    typecode: str | None = None
    lat: float | None = None
    lng: float | None = None
    source: str


class ReverseGeocodeResult(PetJourneyBaseModel):
    formatted_address: str
    province: str | None = None
    city: str | None = None
    district: str | None = None
    township: str | None = None
    adcode: str | None = None
    street: str | None = None
    number: str | None = None
    poi_name: str | None = None
    source: str


class StaticMapAsset(PetJourneyBaseModel):
    provider: str
    center_lat: float
    center_lng: float
    zoom: int
    media_url: str | None = None
    fallback_url: str | None = None
    generated_at: datetime


class StreetRankItem(PetJourneyBaseModel):
    rank: int
    place: PlaceSignal
    rank_score: float
    reason: str
    pet_action: str
    owner_tip: str
    weather_note: str


class StreetRankResponse(PetJourneyBaseModel):
    pet_id: str
    city: str
    theme: str
    generated_at: datetime
    provider: str
    weather: str
    items: list[StreetRankItem]
    source_notes: list[str]


__all__ = [
    "PlaceSignal",
    "PhotoPerspective",
    "PetCredentialKind",
    "PetCredentialPrompt",
    "PlaceInteraction",
    "PhotoQualityReport",
    "PhotoMission",
    "MapSearchTip",
    "ReverseGeocodeResult",
    "StaticMapAsset",
    "StreetRankItem",
    "StreetRankResponse",
]
