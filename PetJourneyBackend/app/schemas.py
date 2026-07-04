from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PetJourneyBaseModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class PetType(str, Enum):
    dog = "dog"
    cat = "cat"
    parrot = "parrot"
    rabbit = "rabbit"
    hamster = "hamster"
    bird = "bird"
    other = "other"


class JourneyStatus(str, Enum):
    traveling = "traveling"
    flying = "flying"
    resting = "resting"
    staying = "staying"
    walking = "walking"


class TravelMode(str, Enum):
    stay = "stay"
    walk = "walk"
    drive = "drive"
    transit = "transit"
    train = "train"
    flight = "flight"
    ferry = "ferry"
    check_in = "check_in"


class TransportLegStatus(str, Enum):
    scheduled = "scheduled"
    waiting = "waiting"
    boarding = "boarding"
    in_transit = "in_transit"
    arrived = "arrived"
    delayed = "delayed"
    cancelled = "cancelled"


class TradePolicy(str, Enum):
    tradable = "tradable"
    soulbound = "soulbound"
    time_locked = "time_locked"
    quest_locked = "quest_locked"
    system_locked = "system_locked"
    dev_only = "dev_only"


class ItemStatus(str, Enum):
    owned = "owned"
    equipped = "equipped"
    stored = "stored"
    listed = "listed"
    sold = "sold"
    consumed = "consumed"
    archived = "archived"
    deleted = "deleted"


class AcquisitionSource(str, Enum):
    found = "found"
    shop_purchase = "shop_purchase"
    npc_gift = "npc_gift"
    quest_reward = "quest_reward"
    photo_mission = "photo_mission"
    event_reward = "event_reward"
    activity_reward = "activity_reward"
    dev_grant = "dev_grant"


class EconomyTransactionType(str, Enum):
    item_acquired = "item_acquired"
    item_sold = "item_sold"
    owner_fund_granted = "owner_fund_granted"
    fund_to_coin_converted = "fund_to_coin_converted"
    item_locked = "item_locked"
    item_unlocked = "item_unlocked"
    item_archived = "item_archived"


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


class MemoryRecord(PetJourneyBaseModel):
    id: str
    pet_id: str
    kind: str
    title: str
    content: str
    salience: float
    source: str
    created_at: datetime
    last_seen_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    memory_type: str = "episodic"
    importance: float = 0.5
    emotional_valence: float = 0.0
    confidence: float = 1.0
    source_event_id: str | None = None
    structured_payload: dict[str, Any] = Field(default_factory=dict)


class MemoryCreateRequest(PetJourneyBaseModel):
    kind: str = "note"
    title: str
    content: str
    salience: float = 0.5
    source: str = "manual"
    metadata: dict[str, Any] = Field(default_factory=dict)
    memory_type: str = "episodic"
    importance: float | None = None
    emotional_valence: float = 0.0
    confidence: float = 1.0
    source_event_id: str | None = None
    structured_payload: dict[str, Any] = Field(default_factory=dict)


class MemoryUpdateRequest(PetJourneyBaseModel):
    kind: str | None = None
    title: str | None = None
    content: str | None = None
    salience: float | None = None
    source: str | None = None
    metadata: dict[str, Any] | None = None
    memory_type: str | None = None
    importance: float | None = None
    emotional_valence: float | None = None
    confidence: float | None = None
    source_event_id: str | None = None
    structured_payload: dict[str, Any] | None = None


class MemoryDeleteResponse(PetJourneyBaseModel):
    success: bool
    memory_id: str


class MemorySearchRequest(PetJourneyBaseModel):
    query: str
    limit: int = 8


class MemorySearchResponse(PetJourneyBaseModel):
    pet_id: str
    query: str
    provider: str
    items: list[MemoryRecord]


class MemoryConsolidationResult(PetJourneyBaseModel):
    pet_id: str
    date: date
    provider: str
    source_memory_count: int
    created_memories: list[MemoryRecord] = Field(default_factory=list)
    relationship_summary: str
    place_affect: dict[str, float] = Field(default_factory=dict)
    preference_updates: list[str] = Field(default_factory=list)
    tomorrow_bias: list[str] = Field(default_factory=list)


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


class CurrencyAmounts(PetJourneyBaseModel):
    travel_coin: int = 0
    star_dust: int = 0
    merit: int = 0


class Wallet(PetJourneyBaseModel):
    pet_id: str
    travel_coin: int = 0
    star_dust: int = 0
    merit: int = 0
    updated_at: datetime


class OwnerFund(PetJourneyBaseModel):
    pet_id: str
    star_dust: int = 0
    project_budget: int = 0
    cosmetic_budget: int = 0
    travel_opportunity_budget: int = 0
    daily_coin_limit: int = 300
    coin_inflow_today: int = 0
    coin_inflow_date: date
    updated_at: datetime


class EconomySnapshot(PetJourneyBaseModel):
    pet_id: str
    total_display_value: int = 0
    sellable_value: int = 0
    collection_value: int = 0
    honor_value: int = 0
    owned_item_count: int = 0
    sellable_item_count: int = 0
    archived_item_count: int = 0
    sold_item_count: int = 0
    updated_at: datetime


class EconomyTransaction(PetJourneyBaseModel):
    tx_id: str
    pet_id: str
    type: EconomyTransactionType
    idempotency_key: str
    amounts: CurrencyAmounts = Field(default_factory=CurrencyAmounts)
    item_ids: list[str] = Field(default_factory=list)
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    reason: str
    operator: str = "system"
    source: str
    status: str = "committed"
    created_at: datetime


class ItemValue(PetJourneyBaseModel):
    market_value: int = 0
    emotional_value: int = 0
    honor_value: int = 0
    value_breakdown: dict[str, Any] = Field(default_factory=dict)


class EconomyResponse(PetJourneyBaseModel):
    wallet: Wallet
    owner_fund: OwnerFund
    snapshot: EconomySnapshot
    recent_transactions: list[EconomyTransaction] = Field(default_factory=list)


class SellItemRequest(PetJourneyBaseModel):
    client_request_id: str = Field(min_length=1, max_length=120)
    expected_item_version: int = Field(ge=1)


class ArchiveItemRequest(PetJourneyBaseModel):
    client_request_id: str = Field(min_length=1, max_length=120)
    expected_item_version: int = Field(ge=1)


class OwnerFundGrantRequest(PetJourneyBaseModel):
    grant_id: str = Field(min_length=1, max_length=120)
    star_dust: int = Field(default=0, ge=0)
    project_budget: int = Field(default=0, ge=0)
    cosmetic_budget: int = Field(default=0, ge=0)
    travel_opportunity_budget: int = Field(default=0, ge=0)
    reason: str = Field(default="开发环境主人基金入账", max_length=240)


class SouvenirItemType(str, Enum):
    toy = "toy"
    cultural_creative = "cultural_creative"
    ticket_stub = "ticket_stub"
    charm = "charm"
    snack_pack = "snack_pack"
    photo_print = "photo_print"
    found_object = "found_object"


class SouvenirItem(PetJourneyBaseModel):
    id: str
    pet_id: str
    quest_id: str | None = None
    template_id: str | None = None
    item_type: SouvenirItemType
    title: str
    subtitle: str
    city: str
    place_name: str
    story: str
    pet_voice: str
    image_prompt: str
    image_url: str | None = None
    rarity: str = "common"
    obtained_at: datetime
    source: str
    memory_type: str = "souvenir"
    source_photo_mission_id: str | None = None
    bag_influence_tags: list[str] = Field(default_factory=list)
    status: ItemStatus = ItemStatus.owned
    version: int = 1
    trade_policy: TradePolicy = TradePolicy.tradable
    lock_until: datetime | None = None
    market_value: int = 0
    emotional_value: int = 0
    honor_value: int = 0
    value_breakdown: dict[str, Any] = Field(default_factory=dict)
    acquire_source: AcquisitionSource = AcquisitionSource.quest_reward
    origin_event_id: str | None = None
    origin_activity_id: str | None = None
    origin_activity_type: str | None = None
    origin_poi_name: str | None = None
    origin_city: str | None = None
    origin_weather: str | None = None
    origin_coords: list[float] = Field(default_factory=list)
    updated_at: datetime | None = None


class CollectSouvenirsResponse(PetJourneyBaseModel):
    items: list[SouvenirItem]
    transactions: list[EconomyTransaction]
    wallet: Wallet
    snapshot: EconomySnapshot


class InventoryResponse(PetJourneyBaseModel):
    items: list[SouvenirItem]
    snapshot: EconomySnapshot


class ItemMutationResponse(PetJourneyBaseModel):
    success: bool
    transaction: EconomyTransaction
    wallet: Wallet
    item: SouvenirItem
    snapshot: EconomySnapshot


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
