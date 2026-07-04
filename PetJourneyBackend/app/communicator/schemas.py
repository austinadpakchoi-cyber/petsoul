from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from ..schemas import JourneyStatus, PetJourneyBaseModel, TravelMode


class CommunicatorIntent(str, Enum):
    emotional_distress = "EMOTIONAL_DISTRESS"
    farewell_or_grief_spike = "FAREWELL_OR_GRIEF_SPIKE"
    current_status_visual_request = "CURRENT_STATUS_VISUAL_REQUEST"
    photo_request = "PHOTO_REQUEST"
    confirm_pending_photo = "CONFIRM_PENDING_PHOTO"
    owner_photo_share = "OWNER_PHOTO_SHARE"
    postcard_request = "POSTCARD_REQUEST"
    location_check = "LOCATION_CHECK"
    affection_i_miss_you = "AFFECTION_I_MISS_YOU"
    care_check = "CARE_CHECK"
    general_chat = "GENERAL_CHAT"


class ReplyMode(str, Enum):
    immediate = "immediate"
    delayed = "delayed"
    queued_until_landed = "queued_until_landed"
    queued_until_morning = "queued_until_morning"
    queued_until_photoable_scene = "queued_until_photoable_scene"
    no_reply_needed = "no_reply_needed"


class MessageSender(str, Enum):
    owner = "owner"
    pet = "pet"
    system = "system"


class UserMessageState(str, Enum):
    created = "created"
    delivered = "delivered"
    seen_by_pet = "seen_by_pet"
    batched = "batched"
    replied = "replied"
    expired = "expired"


class PetReplyState(str, Enum):
    drafted = "drafted"
    scheduled = "scheduled"
    sent = "sent"
    failed = "failed"
    cancelled = "cancelled"


class AttachmentState(str, Enum):
    planned = "planned"
    placeholder = "placeholder"
    generating = "generating"
    ready = "ready"
    failed = "failed"
    expired = "expired"


class PendingStatus(str, Enum):
    pending = "pending"
    fulfilled = "fulfilled"
    expired = "expired"
    cancelled = "cancelled"
    failed = "failed"


class AttachmentType(str, Enum):
    text = "text"
    sticker = "sticker"
    location_card = "location_card"
    photo_status_card = "photo_status_card"
    photo_placeholder = "photo_placeholder"
    photo = "photo"
    owner_photo = "owner_photo"
    pending_photo_request = "pending_photo_request"
    postcard_candidate = "postcard_candidate"


class MomentSourceType(str, Enum):
    journey_event = "journey_event"
    arrival = "arrival"
    day_plan_completed = "day_plan_completed"
    current_status_photo = "current_status_photo"
    photo_request_fulfilled = "photo_request_fulfilled"
    postcard_candidate = "postcard_candidate"
    resting = "resting"
    night_thought = "night_thought"
    mock = "mock"


class MomentReaction(str, Enum):
    like = "like"
    paw = "paw"
    hug = "hug"


class CommunicatorLocation(PetJourneyBaseModel):
    city: str
    place_name: str | None = None
    lat: float | None = None
    lng: float | None = None


class CommunicatorWorldSnapshot(PetJourneyBaseModel):
    pet_id: str
    city: str
    place_name: str | None = None
    scene_anchor: str
    scene_hash: str
    journey_status: JourneyStatus
    travel_mode: TravelMode | None = None
    activity_type: str
    can_generate_photo: bool
    animation_hint: str
    energy: int
    happiness: int
    curiosity: int
    weather: str
    local_hour: int
    is_sleeping: bool
    is_in_transit: bool
    is_flying: bool
    lat: float | None = None
    lng: float | None = None

    @property
    def location(self) -> CommunicatorLocation:
        return CommunicatorLocation(city=self.city, place_name=self.place_name, lat=self.lat, lng=self.lng)


class ReplyPolicy(PetJourneyBaseModel):
    mode: ReplyMode
    estimated_reply_seconds: int
    visible_status: str
    reason_code: str
    should_batch: bool = False
    should_mark_seen: bool = True
    cooldown_applied: bool = False


class CommunicatorAttachment(PetJourneyBaseModel):
    type: AttachmentType
    title: str
    text: str
    state: AttachmentState = AttachmentState.planned
    photo_url: str | None = None
    location: CommunicatorLocation | None = None
    photo_mission_id: str | None = None
    available_after: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MomentSocialReactor(PetJourneyBaseModel):
    id: str
    name: str
    species: str
    avatar_emoji: str = "🐾"
    reaction: MomentReaction = MomentReaction.like
    note: str | None = None
    created_at: datetime


class CommunicatorMessage(PetJourneyBaseModel):
    id: str
    pet_id: str
    sender: MessageSender
    text: str
    intent: CommunicatorIntent | None = None
    scene_hash: str | None = None
    message_state: UserMessageState | PetReplyState
    reply_policy: ReplyPolicy | None = None
    attachments: list[CommunicatorAttachment] = Field(default_factory=list)
    related_message_id: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class CommunicatorSendRequest(PetJourneyBaseModel):
    text: str = Field(min_length=1, max_length=500)
    client_time: datetime | None = None


class CommunicatorSendResponse(PetJourneyBaseModel):
    success: bool
    intent: CommunicatorIntent
    reply_policy: ReplyPolicy
    owner_message: CommunicatorMessage
    messages: list[CommunicatorMessage] = Field(default_factory=list)
    pending_request: "PendingPhotoRequest | None" = None


class PendingPhotoRequest(PetJourneyBaseModel):
    id: str
    pet_id: str
    source_message_id: str
    intent: CommunicatorIntent
    pending_type: ReplyMode
    status: PendingStatus
    reason: str
    trigger: str
    requested_scene: str
    scene_hash: str
    created_at: datetime
    available_after: datetime
    expires_at: datetime
    attempt_count: int = 0
    max_attempts: int = 3
    fulfilled_message_id: str | None = None


class CommunicatorMoment(PetJourneyBaseModel):
    id: str
    pet_id: str
    source_type: MomentSourceType
    source_event_id: str | None = None
    text: str
    location: CommunicatorLocation | None = None
    mood: str = "calm"
    attachments: list[CommunicatorAttachment] = Field(default_factory=list)
    reactions: dict[str, int] = Field(default_factory=lambda: {
        MomentReaction.like.value: 0,
        MomentReaction.paw.value: 0,
        MomentReaction.hug.value: 0,
    })
    social_reactors: list[MomentSocialReactor] = Field(default_factory=list)
    owner_reaction: MomentReaction | None = None
    is_read: bool = False
    created_at: datetime
    updated_at: datetime | None = None


class MomentReactionRequest(PetJourneyBaseModel):
    reaction: MomentReaction


class MomentReactionResponse(PetJourneyBaseModel):
    success: bool
    moment_id: str
    reaction: MomentReaction
    message: str


CommunicatorSendResponse.model_rebuild()
