"""FastAPI 依赖注入层。

所有 router 通过 ``request.app.state`` 获取由 ``create_app`` 装配好的实例，
而不是依赖闭包捕获。这样端点可以被拆到独立的 APIRouter 文件里，而
main.py 只负责装配与挂载。
"""

from __future__ import annotations

from fastapi import Request

from .agent_brain import PetAgentBrain
from .agent_engine import JourneyEngine
from .amap_services import AMapWebServiceClient
from .auth import AuthService
from .communicator.engine import PetCommunicatorEngine
from .config import Settings
from .credential_prompt_builder import PetCredentialPromptBuilder
from .economy_engine import PetEconomyEngine
from .google_maps_services import GoogleMapsServiceClient
from .illustrated_guide import IllustratedGuideEngine
from .image_provider import ImageProvider
from .memory_store import MemoryStore
from .notifications import NotificationDispatcher
from .owner_intent_brain import OwnerIntentBrain
from .pet_guide_engine import PetGuideEngine
from .pet_life_engine import PetLifeSimulationEngine
from .photo_mission_brain import PhotoMissionBrain
from .place_interactions import PlaceInteractionEngine
from .providers import CompanionContentProvider, MapProvider
from .route_planner import TravelRoutePlanner
from .scheduler import BackgroundAgentScheduler
from .storage import JourneyStorage
from .street_rank import PetStreetRankEngine
from .transport_reality import TransportRealityProvider
from .travel_quest_engine import PetTravelQuestEngine
from .weather_provider import WeatherProvider
from .world_simulation import WorldSimulationEngine


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_storage(request: Request) -> JourneyStorage:
    return request.app.state.storage


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


def get_engine(request: Request) -> JourneyEngine:
    return request.app.state.engine


def get_agent_brain(request: Request) -> PetAgentBrain:
    return request.app.state.agent_brain


def get_owner_intent_brain(request: Request) -> OwnerIntentBrain:
    return request.app.state.owner_intent_brain


def get_pet_guide_engine(request: Request) -> PetGuideEngine:
    return request.app.state.pet_guide_engine


def get_photo_mission_brain(request: Request) -> PhotoMissionBrain:
    return request.app.state.photo_mission_brain


def get_place_interaction_engine(request: Request) -> PlaceInteractionEngine:
    return request.app.state.place_interaction_engine


def get_image_provider(request: Request) -> ImageProvider:
    return request.app.state.image_provider


def get_memory_store(request: Request) -> MemoryStore:
    return request.app.state.memory_store


def get_pet_life_engine(request: Request) -> PetLifeSimulationEngine:
    return request.app.state.pet_life_engine


def get_travel_quest_engine(request: Request) -> PetTravelQuestEngine:
    return request.app.state.travel_quest_engine


def get_economy_engine(request: Request) -> PetEconomyEngine:
    return request.app.state.economy_engine


def get_notification_dispatcher(request: Request) -> NotificationDispatcher:
    return request.app.state.notification_dispatcher


def get_route_planner(request: Request) -> TravelRoutePlanner:
    return request.app.state.route_planner


def get_scheduler(request: Request) -> BackgroundAgentScheduler:
    return request.app.state.scheduler


def get_communicator_engine(request: Request) -> PetCommunicatorEngine:
    return request.app.state.communicator_engine


def get_transport_reality_provider(request: Request) -> TransportRealityProvider:
    return request.app.state.transport_reality_provider


def get_world_simulation_engine(request: Request) -> WorldSimulationEngine:
    return request.app.state.world_simulation_engine


def get_weather_provider(request: Request) -> WeatherProvider:
    return request.app.state.weather_provider


def get_amap_client(request: Request) -> AMapWebServiceClient:
    return request.app.state.amap_client


def get_google_client(request: Request) -> GoogleMapsServiceClient:
    return request.app.state.google_client


def get_street_rank_engine(request: Request) -> PetStreetRankEngine:
    return request.app.state.street_rank_engine


def get_credential_prompt_builder(request: Request) -> PetCredentialPromptBuilder:
    return request.app.state.credential_prompt_builder


def get_map_provider(request: Request) -> MapProvider:
    return request.app.state.map_provider


def get_content_provider(request: Request) -> CompanionContentProvider:
    return request.app.state.content_provider


def get_illustrated_guide_engine(request: Request) -> IllustratedGuideEngine:
    return request.app.state.illustrated_guide_engine
