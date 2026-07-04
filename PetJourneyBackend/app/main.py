from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
import json
from pathlib import Path
import re
import shutil
import uuid

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .amap_services import build_amap_web_service
from .agent_brain import build_agent_brain
from .agent_engine import JourneyEngine, PetNotFoundError, ThoughtNotFoundError, TravelQuestNotFoundError
from .communicator.engine import PetCommunicatorEngine
from .communicator.schemas import (
    CommunicatorMessage,
    CommunicatorMoment,
    CommunicatorSendRequest,
    CommunicatorSendResponse,
    MomentReactionRequest,
    MomentReactionResponse,
)
from .config import Settings, load_settings
from .credential_prompt_builder import PetCredentialPromptBuilder
from .economy_engine import EconomyConflictError, PetEconomyEngine
from .event_generator import JourneyEventGenerator
from .feedback_effects import JourneyFeedbackPolicy
from .google_maps_services import build_google_maps_service
from .image_provider import build_image_provider
from .illustrated_guide import IllustratedGuideEngine
from .memory_store import build_memory_store
from .notifications import build_notification_dispatcher
from .owner_intent_brain import build_owner_intent_brain
from .pet_life_engine import build_pet_life_simulation_engine
from .pet_guide_engine import PetGuideEngine
from .place_interactions import PlaceInteractionEngine
from .photo_mission_brain import build_photo_mission_brain
from .providers import build_content_provider, build_map_provider
from .route_planner import build_route_planner
from .scheduler import BackgroundAgentScheduler
from .story_ticker import StoryTickerResponse, build_story_ticker
from .street_rank import PetStreetRankEngine
from .transport_reality import build_transport_reality_provider
from .travel_quest_engine import build_pet_travel_quest_engine
from .weather_provider import build_weather_provider
from .world_simulation import build_world_simulation_engine
from .schemas import (
    AgentStatus,
    ArchiveItemRequest,
    CityPosition,
    CollectSouvenirsResponse,
    CreatePetResponse,
    DayPlan,
    DeviceRegistrationRequest,
    DeviceRegistrationResponse,
    EconomyResponse,
    FeedbackResponse,
    IllustratedGuide,
    InventoryResponse,
    ItemMutationResponse,
    ItemStatus,
    JourneyPlan,
    JourneyRoutePlan,
    JourneyEngineTrace,
    LifeTickResult,
    MapSearchTip,
    MemoryConsolidationResult,
    MemoryCreateRequest,
    MemoryDeleteResponse,
    MemoryRecord,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryUpdateRequest,
    NotificationDelivery,
    OwnerMessageRequest,
    OwnerMessageResponse,
    OwnerFundGrantRequest,
    PetAuthoredGuide,
    PetCredentialPrompt,
    PetDNA,
    PetType,
    PhotoMission,
    Postcard,
    ReverseGeocodeResult,
    SchedulerConfig,
    SchedulerTickResult,
    StaticMapAsset,
    StreetRankResponse,
    SouvenirItem,
    ThoughtTranslation,
    SellItemRequest,
    TravelBag,
    TravelBagPackRequest,
    TravelQuest,
    TravelQuestDecisionRequest,
    TravelWishRequest,
    WorldSimulationSnapshot,
)
from .storage import JourneyStorage, utcnow


DEMO_FRENCHIE_PROFILE_PHOTO = "demo/frenchie-profile.png"
DEMO_FRENCHIE_POSTCARD_PHOTO = "demo/frenchie-netcafe-postcard.png"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    storage = JourneyStorage(settings.database_path)
    google_client = build_google_maps_service(settings)
    map_provider = build_map_provider(settings, google_client=google_client)
    amap_client = build_amap_web_service(settings)
    content_provider = build_content_provider(settings)
    image_provider = build_image_provider(settings)
    illustrated_guide_engine = IllustratedGuideEngine(settings=settings, image_provider=image_provider)
    agent_brain = build_agent_brain(settings)
    owner_intent_brain = build_owner_intent_brain(settings)
    pet_guide_engine = PetGuideEngine(settings)
    photo_mission_brain = build_photo_mission_brain(settings)
    place_interaction_engine = PlaceInteractionEngine(photo_mission_brain)
    memory_store = build_memory_store(storage, settings)
    pet_life_engine = build_pet_life_simulation_engine(settings, memory_store)
    travel_quest_engine = build_pet_travel_quest_engine(settings)
    economy_engine = PetEconomyEngine(storage, settings)
    notification_dispatcher = build_notification_dispatcher(storage, settings)
    weather_provider = build_weather_provider(settings, google_client=google_client)
    transport_reality_provider = build_transport_reality_provider(settings)
    route_planner = build_route_planner(settings, map_provider, transport_reality_provider, amap_client, google_client)
    street_rank_engine = PetStreetRankEngine(map_provider)
    world_simulation_engine = build_world_simulation_engine(settings)
    event_generator = JourneyEventGenerator(
        storage,
        content_provider,
        map_provider,
        image_provider,
        place_interaction_engine,
        settings,
    )
    feedback_policy = JourneyFeedbackPolicy()
    credential_prompt_builder = PetCredentialPromptBuilder()
    engine = JourneyEngine(
        storage,
        map_provider,
        agent_brain,
        settings,
        route_planner,
        event_generator,
        feedback_policy,
        pet_guide_engine,
        world_simulation_engine,
        weather_provider,
        street_rank_engine,
        amap_client,
        memory_store,
        place_interaction_engine,
        pet_life_engine,
        travel_quest_engine,
        economy_engine,
        owner_intent_brain,
    )
    scheduler = BackgroundAgentScheduler(
        storage=storage,
        engine=engine,
        notification_dispatcher=notification_dispatcher,
        memory_store=memory_store,
        settings=settings,
    )
    communicator_engine = PetCommunicatorEngine(
        storage=storage,
        journey_engine=engine,
        memory_store=memory_store,
    )
    engine.attach_communicator_engine(communicator_engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await scheduler.start()
        try:
            yield
        finally:
            await scheduler.stop()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.storage = storage
    app.state.engine = engine
    app.state.agent_brain = agent_brain
    app.state.owner_intent_brain = owner_intent_brain
    app.state.pet_guide_engine = pet_guide_engine
    app.state.photo_mission_brain = photo_mission_brain
    app.state.place_interaction_engine = place_interaction_engine
    app.state.image_provider = image_provider
    app.state.memory_store = memory_store
    app.state.pet_life_engine = pet_life_engine
    app.state.travel_quest_engine = travel_quest_engine
    app.state.economy_engine = economy_engine
    app.state.travel_research_engine = travel_quest_engine.research_engine
    app.state.notification_dispatcher = notification_dispatcher
    app.state.route_planner = route_planner
    app.state.scheduler = scheduler
    app.state.communicator_engine = communicator_engine
    app.state.transport_reality_provider = transport_reality_provider
    app.state.world_simulation_engine = world_simulation_engine
    app.state.weather_provider = weather_provider
    app.state.amap_client = amap_client
    app.state.google_client = google_client
    app.state.street_rank_engine = street_rank_engine
    app.state.credential_prompt_builder = credential_prompt_builder

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    ensure_demo_media(settings.upload_dir)
    app.mount("/media", StaticFiles(directory=settings.upload_dir), name="media")

    def lightweight_illustrated_guide_plan(pet) -> JourneyPlan:
        now = utcnow()
        elapsed = (now - pet.created_at).total_seconds()
        city = engine._city_for_elapsed(elapsed, now=now)
        planner = getattr(route_planner, "fallback", route_planner)
        return planner.build_journey_plan(pet, city, now)

    @app.get("/health")
    def health() -> dict[str, str | bool]:
        return {
            "status": "ok",
            "provider_mode": settings.provider_mode,
            "map_provider_mode": settings.map_provider,
            "map_provider": map_provider.provider_name,
            "content_provider": content_provider.provider_name,
            "image_provider": image_provider.provider_name,
            "agent_brain": agent_brain.provider_name,
            "owner_intent_brain": owner_intent_brain.provider_name,
            "pet_guide_engine": pet_guide_engine.provider_name,
            "photo_mission_brain": photo_mission_brain.provider_name,
            "place_interaction_engine": place_interaction_engine.provider_name,
            "transport_reality_provider": transport_reality_provider.provider_name,
            "route_planner": route_planner.provider_name,
            "world_simulation_engine": world_simulation_engine.provider_name,
            "weather_provider": weather_provider.provider_name,
            "amap_web_service": amap_client.provider_name if amap_client.configured else "mock-amap-web-service",
            "google_maps_service": google_client.provider_name if google_client.configured else "mock-google-maps-service",
            "street_rank_engine": street_rank_engine.provider_name,
            "notification_provider": str(notification_dispatcher.config_snapshot()["provider"]),
            "memory_provider": str(memory_store.config_snapshot()["provider"]),
            "pet_life_engine": pet_life_engine.provider_name,
            "travel_quest_engine": travel_quest_engine.provider_name,
            "economy_engine": economy_engine.provider_name,
            "economy_dev_grants_enabled": settings.economy_dev_grants_enabled,
            "travel_research_engine": travel_quest_engine.research_engine.provider_name,
            "scheduler": scheduler.provider_name,
            "scheduler_enabled": settings.scheduler_enabled,
            "communicator_engine": communicator_engine.provider_name,
            "credential_prompt_builder": credential_prompt_builder.provider_name,
        }

    @app.post("/api/v1/create_pet", response_model=CreatePetResponse)
    async def create_pet(
        pet_name: str = Form(...),
        pet_type: PetType = Form(...),
        dna: str = Form(...),
        pet_photo: UploadFile | None = File(default=None),
    ) -> CreatePetResponse:
        parsed_dna = parse_dna(dna)
        photo_path = await save_upload(settings.upload_dir, pet_photo)
        pet = storage.create_pet(
            name=pet_name.strip(),
            pet_type=pet_type,
            dna=parsed_dna,
            photo_path=photo_path,
        )
        engine.create_initial_journey(pet)

        city = engine.city_position(pet.pet_id).city
        return CreatePetResponse(
            success=True,
            pet_id=pet.pet_id,
            name=pet.name,
            location=city,
            photo_url=public_photo_url(settings, photo_path),
            message=f"{pet.name} 已经在 {city} 开始旅程了",
        )

    @app.post("/api/v1/demo/frenchie", response_model=CreatePetResponse)
    def create_demo_frenchie() -> CreatePetResponse:
        dna = PetDNA(
            owner_title="妈妈",
            personality="黏人、好奇、很会观察人的情绪，到了新地方会先看一圈再靠近。",
            favorite_places=["有地毯的小店", "安静网吧", "能晒太阳的街角"],
            hobby=["盯着屏幕看", "戴耳机陪人打游戏", "坐在咖啡店和小吃店里观察人来人往"],
            catchphrase="我在这里玩一会儿，也在想你。",
            emoji_pref="soft",
            voice_style="像发来一张随手拍照片，语气轻轻的但很认真。",
        )
        pet = storage.create_pet(
            name="小黑",
            pet_type=PetType.dog,
            dna=dna,
            photo_path=DEMO_FRENCHIE_PROFILE_PHOTO,
        )
        engine.create_initial_journey(pet)

        city = engine.city_position(pet.pet_id).city
        postcard_url = public_media_url(settings, DEMO_FRENCHIE_POSTCARD_PHOTO)
        storage.add_postcard(
            pet.pet_id,
            location=f"{city} · 安静网吧",
            text="我找到一个很亮的屏幕，旁边的人都很专心。我戴着耳机坐了一会儿，像是在陪他们赢一局。",
            weather="室内有蓝色的灯，外面应该还是温暖的",
            happiness=88,
            image_url=postcard_url,
        )
        storage.append_thought(
            pet.pet_id,
            "汪呜汪，汪汪！呜汪。",
            tone="selfie",
            animal_text="汪呜汪，汪汪！呜汪。",
            translation="我刚刚拍了一张照片给你。这里有键盘声、饮料杯，还有一点点像冒险的光。",
            language_style="dog_vocalization_with_hidden_translation",
            model=settings.agent_model,
        )
        storage.append_event(
            pet.pet_id,
            "发回一张场景照",
            "TA 在一个网吧里短暂停留，照片已经作为第一张明信片保存。",
        )

        return CreatePetResponse(
            success=True,
            pet_id=pet.pet_id,
            name=pet.name,
            location=city,
            photo_url=public_media_url(settings, DEMO_FRENCHIE_PROFILE_PHOTO),
            message=f"{pet.name} 的演示旅程已经建立，并发回了第一张照片。",
        )

    @app.get("/api/v1/agent_status/{pet_id}", response_model=AgentStatus)
    def agent_status(pet_id: str) -> AgentStatus:
        return with_not_found(lambda: engine.status(pet_id))

    @app.get("/api/v1/day_plan/{pet_id}", response_model=DayPlan)
    def day_plan(pet_id: str) -> DayPlan:
        return with_not_found(lambda: engine.day_plan(pet_id))

    @app.get("/api/v1/pet_dna/{pet_id}", response_model=PetDNA)
    def pet_dna(pet_id: str) -> PetDNA:
        return with_not_found(lambda: engine.pet_dna(pet_id))

    @app.patch("/api/v1/pet_dna/{pet_id}", response_model=PetDNA)
    def update_pet_dna(pet_id: str, dna: PetDNA) -> PetDNA:
        return with_not_found(lambda: engine.update_pet_dna(pet_id, dna))

    @app.get("/api/v1/pets/{pet_id}/credentials/prompts", response_model=list[PetCredentialPrompt])
    def credential_prompts(pet_id: str) -> list[PetCredentialPrompt]:
        pet = storage.get_pet(pet_id)
        if pet is None:
            raise HTTPException(status_code=404, detail="Pet not found")
        return credential_prompt_builder.build_wallet_prompts(
            pet=pet,
            has_pet_reference=bool(pet.photo_path),
        )

    @app.get("/api/v1/thoughts/{thought_id}/translation", response_model=ThoughtTranslation)
    def thought_translation(thought_id: str, pet_id: str) -> ThoughtTranslation:
        return with_not_found(lambda: engine.thought_translation(pet_id=pet_id, thought_id=thought_id))

    @app.get("/api/v1/agent_brain/config")
    def agent_brain_config() -> dict[str, str | bool | float]:
        return agent_brain.config_snapshot()

    @app.get("/api/v1/owner_intent_brain/config")
    def owner_intent_brain_config() -> dict[str, str | bool]:
        return owner_intent_brain.config_snapshot()

    @app.get("/api/v1/image_provider/config")
    def image_provider_config() -> dict[str, str | bool | float]:
        return image_provider.config_snapshot()

    @app.get("/api/v1/travel_research/config")
    def travel_research_config() -> dict[str, str | bool | float]:
        return {
            "provider": travel_quest_engine.research_engine.provider_name,
            "configured_provider": settings.travel_guide_research_provider,
            "doubao_configured": bool(settings.doubao_api_key),
            "doubao_provider": travel_quest_engine.research_engine.doubao_client.provider_name,
            "doubao_model": settings.doubao_guide_model,
            "doubao_base_url": settings.doubao_base_url,
            "doubao_timeout_seconds": settings.doubao_timeout_seconds,
            "doubao_reasoning_effort": settings.doubao_reasoning_effort,
            "openai_web_search_configured": bool(settings.openai_api_key),
        }

    @app.get("/api/v1/photo_mission_brain/config")
    def photo_mission_brain_config() -> dict[str, str | bool | float]:
        return photo_mission_brain.config_snapshot()

    @app.get("/api/v1/memory/config")
    def memory_provider_config() -> dict[str, str | bool | int]:
        return memory_store.config_snapshot()

    @app.get("/api/v1/notifications/config")
    def notification_provider_config() -> dict[str, str | bool]:
        return notification_dispatcher.config_snapshot()

    @app.get("/api/v1/google/config")
    def google_maps_config() -> dict[str, str | bool]:
        return google_client.config_snapshot()

    @app.get("/api/v1/scheduler/config", response_model=SchedulerConfig)
    def scheduler_config() -> SchedulerConfig:
        return scheduler.config()

    @app.post("/api/v1/scheduler/tick", response_model=SchedulerTickResult)
    def scheduler_tick() -> SchedulerTickResult:
        return scheduler.tick()

    @app.post("/api/v1/push/register", response_model=DeviceRegistrationResponse)
    def register_push_device(request: DeviceRegistrationRequest) -> DeviceRegistrationResponse:
        with_not_found(lambda: engine.pet_dna(request.pet_id))
        item = notification_dispatcher.register_device(
            pet_id=request.pet_id,
            device_token=request.device_token,
            platform=request.platform,
            environment=request.environment,
        )
        return DeviceRegistrationResponse(
            success=True,
            device_id=str(item["id"]),
            provider=str(notification_dispatcher.config_snapshot()["provider"]),
            message="设备已经登记，TA 可以在 app 未打开时继续来信。",
        )

    @app.post("/api/v1/push/unregister")
    def unregister_push_device(request: DeviceRegistrationRequest) -> dict[str, bool]:
        notification_dispatcher.unregister_device(device_token=request.device_token, platform=request.platform)
        return {"success": True}

    @app.get("/api/v1/pets/{pet_id}/notifications", response_model=list[NotificationDelivery])
    def notification_deliveries(pet_id: str, limit: int = 20) -> list[NotificationDelivery]:
        with_not_found(lambda: engine.pet_dna(pet_id))
        return [
            NotificationDelivery.model_validate(item)
            for item in storage.list_notification_deliveries(pet_id, limit=max(1, min(100, limit)))
        ]

    @app.get("/api/v1/pets/{pet_id}/memories", response_model=list[MemoryRecord])
    def memories(pet_id: str, limit: int = 50) -> list[MemoryRecord]:
        return with_not_found(lambda: engine.list_memories(pet_id, limit=limit))

    @app.post("/api/v1/pets/{pet_id}/memories", response_model=MemoryRecord)
    def add_memory(pet_id: str, request: MemoryCreateRequest) -> MemoryRecord:
        return with_not_found(
            lambda: engine.add_memory(
                pet_id=pet_id,
                kind=request.kind,
                title=request.title,
                content=request.content,
                salience=request.salience,
                source=request.source,
                metadata=request.metadata,
                memory_type=request.memory_type,
                importance=request.importance,
                emotional_valence=request.emotional_valence,
                confidence=request.confidence,
                source_event_id=request.source_event_id,
                structured_payload=request.structured_payload,
            )
        )

    @app.patch("/api/v1/pets/{pet_id}/memories/{memory_id}", response_model=MemoryRecord)
    def update_memory(pet_id: str, memory_id: str, request: MemoryUpdateRequest) -> MemoryRecord:
        return with_not_found(
            lambda: engine.update_memory(
                pet_id=pet_id,
                memory_id=memory_id,
                kind=request.kind,
                title=request.title,
                content=request.content,
                salience=request.salience,
                source=request.source,
                metadata=request.metadata,
                memory_type=request.memory_type,
                importance=request.importance,
                emotional_valence=request.emotional_valence,
                confidence=request.confidence,
                source_event_id=request.source_event_id,
                structured_payload=request.structured_payload,
            )
        )

    @app.delete("/api/v1/pets/{pet_id}/memories/{memory_id}", response_model=MemoryDeleteResponse)
    def delete_memory(pet_id: str, memory_id: str) -> MemoryDeleteResponse:
        with_not_found(lambda: engine.delete_memory(pet_id, memory_id))
        return MemoryDeleteResponse(success=True, memory_id=memory_id)

    @app.post("/api/v1/pets/{pet_id}/memories/search", response_model=MemorySearchResponse)
    def search_memories(pet_id: str, request: MemorySearchRequest) -> MemorySearchResponse:
        items = with_not_found(lambda: engine.search_memories(pet_id, query=request.query, limit=request.limit))
        return MemorySearchResponse(
            pet_id=pet_id,
            query=request.query,
            provider=memory_store.provider_name,
            items=items,
        )

    @app.post("/api/v1/pets/{pet_id}/memories/consolidate", response_model=MemoryConsolidationResult)
    def consolidate_memories(pet_id: str, target_date: date | None = None) -> MemoryConsolidationResult:
        return with_not_found(lambda: engine.consolidate_daily_memories(pet_id, target_date or date.today()))

    @app.get("/api/v1/pets/{pet_id}/traces", response_model=list[JourneyEngineTrace])
    def list_traces(pet_id: str, limit: int = 20) -> list[JourneyEngineTrace]:
        return with_not_found(lambda: engine.list_traces(pet_id, limit=limit))

    @app.get("/api/v1/pets/{pet_id}/traces/{trace_id}", response_model=JourneyEngineTrace)
    def get_trace(pet_id: str, trace_id: str) -> JourneyEngineTrace:
        return with_not_found(lambda: engine.get_trace(pet_id, trace_id))

    @app.get("/api/v1/pets/{pet_id}/city_position", response_model=CityPosition)
    def city_position(pet_id: str) -> CityPosition:
        return with_not_found(lambda: engine.city_position(pet_id))

    @app.get("/api/v1/pets/{pet_id}/route_plan", response_model=JourneyRoutePlan)
    def route_plan(pet_id: str) -> JourneyRoutePlan:
        return with_not_found(lambda: engine.route_plan(pet_id))

    @app.get("/api/v1/pets/{pet_id}/journey_plan", response_model=JourneyPlan)
    def journey_plan(pet_id: str) -> JourneyPlan:
        return with_not_found(lambda: engine.journey_plan(pet_id))

    @app.get("/api/v1/pets/{pet_id}/pet_guide", response_model=PetAuthoredGuide)
    def pet_guide(pet_id: str) -> PetAuthoredGuide:
        return with_not_found(lambda: engine.pet_guide(pet_id))

    @app.get("/api/v1/pets/{pet_id}/illustrated_guide", response_model=IllustratedGuide)
    def illustrated_guide(pet_id: str, style_id: str | None = None) -> IllustratedGuide:
        def build() -> IllustratedGuide:
            pet = storage.get_pet(pet_id)
            if not pet:
                raise PetNotFoundError(pet_id)
            plan = lightweight_illustrated_guide_plan(pet)
            return illustrated_guide_engine.build(
                pet=pet,
                plan=plan,
                now=plan.generated_at,
                style_id=style_id,
            )

        return with_not_found(build)

    @app.post("/api/v1/pets/{pet_id}/illustrated_guide/generate", response_model=IllustratedGuide)
    def generate_illustrated_guide(
        pet_id: str,
        style_id: str | None = None,
        force_new_style: bool = False,
    ) -> IllustratedGuide:
        def build() -> IllustratedGuide:
            pet = storage.get_pet(pet_id)
            if not pet:
                raise PetNotFoundError(pet_id)
            plan = lightweight_illustrated_guide_plan(pet)
            return illustrated_guide_engine.build(
                pet=pet,
                plan=plan,
                now=plan.generated_at,
                generate_image=True,
                style_id=style_id,
                force_new_style=force_new_style,
            )

        return with_not_found(build)

    @app.post("/api/v1/pets/{pet_id}/travel_quests", response_model=TravelQuest)
    def create_travel_quest(pet_id: str, request: TravelWishRequest) -> TravelQuest:
        return with_not_found(lambda: engine.create_travel_quest(pet_id, request))

    @app.get("/api/v1/pets/{pet_id}/travel_quests", response_model=list[TravelQuest])
    def list_travel_quests(pet_id: str, limit: int = 20) -> list[TravelQuest]:
        return with_not_found(lambda: engine.list_travel_quests(pet_id, limit=limit))

    @app.get("/api/v1/pets/{pet_id}/travel_quests/{quest_id}", response_model=TravelQuest)
    def get_travel_quest(pet_id: str, quest_id: str) -> TravelQuest:
        return with_not_found(lambda: engine.get_travel_quest(pet_id, quest_id))

    @app.post("/api/v1/pets/{pet_id}/travel_quests/{quest_id}/prepare_departure", response_model=TravelQuest)
    def prepare_travel_quest(pet_id: str, quest_id: str) -> TravelQuest:
        return with_not_found(lambda: engine.prepare_travel_quest(pet_id, quest_id))

    @app.post("/api/v1/pets/{pet_id}/travel_quests/{quest_id}/post_event_options", response_model=TravelQuest)
    def travel_quest_post_event_options(pet_id: str, quest_id: str) -> TravelQuest:
        return with_not_found(lambda: engine.travel_quest_post_event_options(pet_id, quest_id))

    @app.post("/api/v1/pets/{pet_id}/travel_quests/{quest_id}/select_next_step", response_model=TravelQuest)
    def select_travel_quest_next_step(
        pet_id: str,
        quest_id: str,
        request: TravelQuestDecisionRequest,
    ) -> TravelQuest:
        return with_not_found(lambda: engine.select_travel_quest_next_step(pet_id, quest_id, request))

    @app.get("/api/v1/pets/{pet_id}/travel_bag", response_model=TravelBag)
    def get_travel_bag(pet_id: str, quest_id: str | None = None) -> TravelBag:
        return with_not_found(lambda: engine.get_travel_bag(pet_id, quest_id=quest_id))

    @app.post("/api/v1/pets/{pet_id}/travel_bag", response_model=TravelBag)
    def pack_travel_bag(pet_id: str, request: TravelBagPackRequest) -> TravelBag:
        return with_not_found(lambda: engine.pack_travel_bag(pet_id, request))

    @app.get("/api/v1/pets/{pet_id}/souvenirs", response_model=list[SouvenirItem])
    def list_souvenirs(pet_id: str, limit: int = 50) -> list[SouvenirItem]:
        return with_not_found(lambda: engine.list_souvenirs(pet_id, limit=limit))

    @app.get("/api/v1/pets/{pet_id}/economy", response_model=EconomyResponse)
    def pet_economy(pet_id: str) -> EconomyResponse:
        return with_not_found(lambda: engine.economy(pet_id))

    @app.get("/api/v1/pets/{pet_id}/inventory", response_model=InventoryResponse)
    def pet_inventory(pet_id: str, status: str = "owned", limit: int = 50) -> InventoryResponse:
        item_status: ItemStatus | None
        if status == "all":
            item_status = None
        else:
            try:
                item_status = ItemStatus(status)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="invalid item status") from exc
        return with_not_found(lambda: engine.inventory(pet_id, status=item_status, limit=limit))

    @app.post(
        "/api/v1/pets/{pet_id}/travel_quests/{quest_id}/souvenirs/collect",
        response_model=CollectSouvenirsResponse,
    )
    def collect_travel_quest_souvenirs_with_economy(pet_id: str, quest_id: str) -> CollectSouvenirsResponse:
        return with_not_found(lambda: engine.collect_travel_quest_souvenirs_response(pet_id, quest_id))

    @app.post("/api/v1/pets/{pet_id}/travel_quests/{quest_id}/souvenirs", response_model=list[SouvenirItem])
    def collect_travel_quest_souvenirs(pet_id: str, quest_id: str) -> list[SouvenirItem]:
        return with_not_found(lambda: engine.collect_travel_quest_souvenirs(pet_id, quest_id))

    @app.post("/api/v1/pets/{pet_id}/items/{item_id}/sell", response_model=ItemMutationResponse)
    def sell_item(pet_id: str, item_id: str, request: SellItemRequest) -> ItemMutationResponse:
        try:
            return with_not_found(lambda: engine.sell_item(pet_id, item_id, request))
        except EconomyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/v1/pets/{pet_id}/items/{item_id}/archive", response_model=ItemMutationResponse)
    def archive_item(pet_id: str, item_id: str, request: ArchiveItemRequest) -> ItemMutationResponse:
        try:
            return with_not_found(lambda: engine.archive_item(pet_id, item_id, request))
        except EconomyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/v1/pets/{pet_id}/owner_fund/grant", response_model=EconomyResponse)
    def grant_owner_fund(
        pet_id: str,
        request: OwnerFundGrantRequest,
        admin_token: str | None = Header(default=None, alias="X-PetJourney-Admin-Token"),
    ) -> EconomyResponse:
        if not settings.economy_dev_grants_enabled or not settings.economy_admin_token:
            raise HTTPException(status_code=403, detail="owner fund grants are disabled")
        if admin_token != settings.economy_admin_token:
            raise HTTPException(status_code=403, detail="invalid admin token")
        try:
            return with_not_found(lambda: engine.grant_owner_fund(pet_id, request))
        except EconomyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/v1/pets/{pet_id}/world_snapshot", response_model=WorldSimulationSnapshot)
    def world_snapshot(pet_id: str) -> WorldSimulationSnapshot:
        return with_not_found(lambda: engine.world_snapshot(pet_id))

    @app.get("/api/v1/pets/{pet_id}/life_tick", response_model=LifeTickResult)
    def life_tick(pet_id: str) -> LifeTickResult:
        return with_not_found(lambda: engine.life_tick(pet_id))

    @app.get("/api/v1/pets/{pet_id}/street_rank", response_model=StreetRankResponse)
    def street_rank(pet_id: str, theme: str = "street") -> StreetRankResponse:
        return with_not_found(lambda: engine.street_rank(pet_id, theme))

    @app.get("/api/v1/world/story_ticker", response_model=StoryTickerResponse)
    def world_story_ticker(limit: int = 8) -> StoryTickerResponse:
        return build_story_ticker(limit=limit)

    @app.get("/api/v1/pets/{pet_id}/static_map", response_model=StaticMapAsset)
    def static_map(pet_id: str, zoom: int = 14) -> StaticMapAsset:
        return with_not_found(lambda: engine.static_map_for_pet(pet_id, zoom=zoom))

    @app.get("/api/v1/pets/{pet_id}/photo_mission", response_model=PhotoMission)
    def photo_mission(pet_id: str) -> PhotoMission:
        return with_not_found(lambda: engine.photo_mission(pet_id))

    @app.post("/api/v1/pets/{pet_id}/generate_selfie", response_model=Postcard)
    def generate_selfie(pet_id: str) -> Postcard:
        return with_not_found(lambda: engine.generate_selfie(pet_id))

    @app.post("/api/v1/pets/{pet_id}/messages", response_model=OwnerMessageResponse)
    def owner_message(pet_id: str, request: OwnerMessageRequest) -> OwnerMessageResponse:
        if not request.message.strip():
            raise HTTPException(status_code=422, detail="message must not be empty")
        return with_not_found(lambda: communicator_engine.legacy_owner_message(pet_id=pet_id, message=request.message, intent_hint=request.intent_hint))

    @app.post("/api/v1/pets/{pet_id}/communicator/messages", response_model=CommunicatorSendResponse)
    def send_communicator_message(pet_id: str, request: CommunicatorSendRequest) -> CommunicatorSendResponse:
        if not request.text.strip():
            raise HTTPException(status_code=422, detail="message must not be empty")
        return with_not_found(lambda: communicator_engine.send_message(pet_id=pet_id, request=request))

    @app.post("/api/v1/pets/{pet_id}/communicator/messages/photo", response_model=CommunicatorSendResponse)
    async def send_communicator_photo(
        pet_id: str,
        text: str = Form(default=""),
        image: UploadFile = File(...),
    ) -> CommunicatorSendResponse:
        media_path = await save_upload(settings.upload_dir, image, subdir="communicator_photos")
        if not media_path:
            raise HTTPException(status_code=422, detail="image must not be empty")
        image_url = public_media_url(settings, media_path)
        if not image_url:
            raise HTTPException(status_code=500, detail="public media url is not configured")
        return with_not_found(
            lambda: communicator_engine.send_photo(
                pet_id=pet_id,
                image_url=image_url,
                media_path=media_path,
                caption=text,
            )
        )

    @app.get("/api/v1/pets/{pet_id}/communicator/messages", response_model=list[CommunicatorMessage])
    def list_communicator_messages(pet_id: str, limit: int = 80) -> list[CommunicatorMessage]:
        return with_not_found(lambda: communicator_engine.list_messages(pet_id=pet_id, limit=limit))

    @app.get("/api/v1/pets/{pet_id}/communicator/moments", response_model=list[CommunicatorMoment])
    def list_communicator_moments(pet_id: str, limit: int = 50) -> list[CommunicatorMoment]:
        return with_not_found(lambda: communicator_engine.list_moments(pet_id=pet_id, limit=limit))

    @app.post(
        "/api/v1/pets/{pet_id}/communicator/moments/{moment_id}/reaction",
        response_model=MomentReactionResponse,
    )
    def react_to_communicator_moment(
        pet_id: str,
        moment_id: str,
        request: MomentReactionRequest,
    ) -> MomentReactionResponse:
        return with_not_found(lambda: communicator_engine.react_to_moment(pet_id=pet_id, moment_id=moment_id, request=request))

    @app.get("/api/v1/amap/input_tips", response_model=list[MapSearchTip])
    def amap_input_tips(keywords: str, city: str | None = None, limit: int = 10) -> list[MapSearchTip]:
        return amap_client.input_tips(keywords=keywords, city=city, limit=max(1, min(20, limit)))

    @app.get("/api/v1/amap/reverse_geocode", response_model=ReverseGeocodeResult | None)
    def amap_reverse_geocode(lat: float, lng: float) -> ReverseGeocodeResult | None:
        return amap_client.reverse_geocode(lat=lat, lng=lng)

    @app.get("/api/v1/google/reverse_geocode", response_model=ReverseGeocodeResult | None)
    def google_reverse_geocode(lat: float, lng: float) -> ReverseGeocodeResult | None:
        return google_client.reverse_geocode(lat=lat, lng=lng)

    @app.post("/api/v1/feedback", response_model=FeedbackResponse)
    def feedback(
        pet_id: str = Form(...),
        city: str = Form(...),
        liked: bool = Form(...),
    ) -> FeedbackResponse:
        return with_not_found(lambda: engine.feedback(pet_id=pet_id, city=city, liked=liked))

    return app


def parse_dna(raw: str) -> PetDNA:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"dna must be JSON: {exc}") from exc
    return PetDNA.model_validate(payload)


async def save_upload(upload_dir: Path, upload: UploadFile | None, subdir: str = "pet_photos") -> str | None:
    if upload is None:
        return None
    data = await upload.read()
    if not data:
        return None

    filename = sanitize_filename(upload.filename or "pet-photo.jpg")
    suffix = Path(filename).suffix.lower() or ".jpg"
    target_dir = upload_dir / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uuid.uuid4().hex}{suffix}"
    target.write_bytes(data)
    return str(target.relative_to(upload_dir))


def ensure_demo_media(upload_dir: Path) -> None:
    source_dir = Path(__file__).resolve().parents[1] / "data" / "uploads" / "demo"
    target_dir = upload_dir / "demo"
    if not source_dir.exists():
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    for filename in (DEMO_FRENCHIE_PROFILE_PHOTO, DEMO_FRENCHIE_POSTCARD_PHOTO):
        source = source_dir / Path(filename).name
        target = target_dir / Path(filename).name
        if source.exists() and not target.exists():
            shutil.copyfile(source, target)


def sanitize_filename(filename: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "-", filename)


def public_photo_url(settings: Settings, photo_path: str | None) -> str | None:
    return public_media_url(settings, photo_path)


def public_media_url(settings: Settings, media_path: str | None) -> str | None:
    if not media_path:
        return None
    if not settings.public_base_url:
        return None
    base = settings.public_base_url.rstrip("/")
    return f"{base}/media/{media_path}"


def with_not_found(factory):
    try:
        return factory()
    except PetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="pet not found") from exc
    except ThoughtNotFoundError as exc:
        raise HTTPException(status_code=404, detail="thought translation not found") from exc
    except TravelQuestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="travel quest not found") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="resource not found") from exc


app = create_app()
