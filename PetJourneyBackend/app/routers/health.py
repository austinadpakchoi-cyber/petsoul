"""运行状态与各 Provider 配置快照端点。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..dependencies import (
    get_agent_brain,
    get_google_client,
    get_image_provider,
    get_memory_store,
    get_notification_dispatcher,
    get_owner_intent_brain,
    get_photo_mission_brain,
    get_settings,
    get_travel_quest_engine,
)

router = APIRouter()


@router.get("/health")
def health(request: Request) -> dict[str, str | bool]:
    state = request.app.state
    settings = state.settings
    map_provider = state.map_provider
    content_provider = state.content_provider
    image_provider = state.image_provider
    agent_brain = state.agent_brain
    owner_intent_brain = state.owner_intent_brain
    pet_guide_engine = state.pet_guide_engine
    photo_mission_brain = state.photo_mission_brain
    place_interaction_engine = state.place_interaction_engine
    transport_reality_provider = state.transport_reality_provider
    route_planner = state.route_planner
    world_simulation_engine = state.world_simulation_engine
    weather_provider = state.weather_provider
    amap_client = state.amap_client
    google_client = state.google_client
    street_rank_engine = state.street_rank_engine
    notification_dispatcher = state.notification_dispatcher
    memory_store = state.memory_store
    pet_life_engine = state.pet_life_engine
    travel_quest_engine = state.travel_quest_engine
    economy_engine = state.economy_engine
    scheduler = state.scheduler
    communicator_engine = state.communicator_engine
    credential_prompt_builder = state.credential_prompt_builder
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


@router.get("/api/v1/agent_brain/config")
def agent_brain_config(agent_brain=Depends(get_agent_brain)) -> dict[str, str | bool | float]:
    return agent_brain.config_snapshot()


@router.get("/api/v1/owner_intent_brain/config")
def owner_intent_brain_config(owner_intent_brain=Depends(get_owner_intent_brain)) -> dict[str, str | bool]:
    return owner_intent_brain.config_snapshot()


@router.get("/api/v1/image_provider/config")
def image_provider_config(image_provider=Depends(get_image_provider)) -> dict[str, str | bool | float]:
    return image_provider.config_snapshot()


@router.get("/api/v1/travel_research/config")
def travel_research_config(
    settings=Depends(get_settings),
    travel_quest_engine=Depends(get_travel_quest_engine),
) -> dict[str, str | bool | float]:
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


@router.get("/api/v1/photo_mission_brain/config")
def photo_mission_brain_config(photo_mission_brain=Depends(get_photo_mission_brain)) -> dict[str, str | bool | float]:
    return photo_mission_brain.config_snapshot()


@router.get("/api/v1/memory/config")
def memory_provider_config(memory_store=Depends(get_memory_store)) -> dict[str, str | bool | int]:
    return memory_store.config_snapshot()


@router.get("/api/v1/notifications/config")
def notification_provider_config(
    notification_dispatcher=Depends(get_notification_dispatcher),
) -> dict[str, str | bool]:
    return notification_dispatcher.config_snapshot()


@router.get("/api/v1/google/config")
def google_maps_config(google_client=Depends(get_google_client)) -> dict[str, str | bool]:
    return google_client.config_snapshot()
