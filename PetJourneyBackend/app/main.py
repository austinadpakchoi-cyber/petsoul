from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .amap_services import build_amap_web_service
from .agent_brain import build_agent_brain
from .agent_engine import JourneyEngine
from .auth import build_auth_service
from .communicator.engine import PetCommunicatorEngine
from .config import Settings, load_settings
from .credential_prompt_builder import PetCredentialPromptBuilder
from .economy_engine import PetEconomyEngine
from .event_generator import JourneyEventGenerator
from .feedback_effects import JourneyFeedbackPolicy
from .google_maps_services import build_google_maps_service
from .seeding import ensure_demo_media
from .illustrated_guide import IllustratedGuideEngine
from .image_provider import build_image_provider
from .memory_store import build_memory_store
from .notifications import build_notification_dispatcher
from .owner_intent_brain import build_owner_intent_brain
from .pet_guide_engine import PetGuideEngine
from .pet_life_engine import build_pet_life_simulation_engine
from .photo_mission_brain import build_photo_mission_brain
from .place_interactions import PlaceInteractionEngine
from .providers import build_content_provider, build_map_provider
from .route_planner import build_route_planner
from .routers import ALL_ROUTERS
from .scheduler import BackgroundAgentScheduler
from .storage import JourneyStorage
from .street_rank import PetStreetRankEngine
from .transport_reality import build_transport_reality_provider
from .travel_quest_engine import build_pet_travel_quest_engine
from .weather_provider import build_weather_provider
from .world_simulation import build_world_simulation_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    storage = JourneyStorage(settings.database_path)
    auth_service = build_auth_service(settings)
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
    app.state.auth_service = auth_service
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
    app.state.map_provider = map_provider
    app.state.content_provider = content_provider
    app.state.illustrated_guide_engine = illustrated_guide_engine

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

    for router in ALL_ROUTERS:
        app.include_router(router)

    return app


app = create_app()
