"""旅程引擎基类：依赖装配 + 实例状态缓存。

将原 agent_engine.py 的 `__init__`（17 个依赖注入）与 `attach_communicator_engine`
抽为基类 mixin，其余场景编排 mixin 只承载方法，通过多重继承组合进门面。
"""

from __future__ import annotations

from typing import Any

from ..amap_services import AMapWebServiceClient
from ..agent_brain import PetAgentBrain
from ..config import Settings
from ..economy_engine import PetEconomyEngine
from ..event_generator import JourneyEventGenerator
from ..feedback_effects import JourneyFeedbackPolicy
from ..memory_store import MemoryStore
from ..owner_intent_brain import OwnerIntentBrain
from ..pet_life_engine import PetLifeSimulationEngine
from ..pet_guide_engine import PetGuideEngine
from ..place_interactions import PlaceInteractionEngine
from ..providers import MapProvider
from ..route_planner import TravelRoutePlanner
from ..schemas import JourneyPlan
from ..storage import JourneyStorage
from ..street_rank import PetStreetRankEngine
from ..travel_quest_engine import PetTravelQuestEngine
from ..weather_provider import WeatherProvider
from ..world_simulation import WorldSimulationEngine


class JourneyEngineBaseMixin:
    def __init__(
        self,
        storage: JourneyStorage,
        map_provider: MapProvider,
        agent_brain: PetAgentBrain,
        settings: Settings,
        route_planner: TravelRoutePlanner,
        event_generator: JourneyEventGenerator,
        feedback_policy: JourneyFeedbackPolicy,
        pet_guide_engine: PetGuideEngine,
        world_simulation_engine: WorldSimulationEngine,
        weather_provider: WeatherProvider,
        street_rank_engine: PetStreetRankEngine,
        amap_client: AMapWebServiceClient,
        memory_store: MemoryStore,
        place_interaction_engine: PlaceInteractionEngine,
        pet_life_engine: PetLifeSimulationEngine,
        travel_quest_engine: PetTravelQuestEngine,
        economy_engine: PetEconomyEngine,
        owner_intent_brain: OwnerIntentBrain,
    ):
        self.storage = storage
        self.map_provider = map_provider
        self.agent_brain = agent_brain
        self.settings = settings
        self.route_planner = route_planner
        self.event_generator = event_generator
        self.feedback_policy = feedback_policy
        self.pet_guide_engine = pet_guide_engine
        self.world_simulation_engine = world_simulation_engine
        self.weather_provider = weather_provider
        self.street_rank_engine = street_rank_engine
        self.amap_client = amap_client
        self.memory_store = memory_store
        self.place_interaction_engine = place_interaction_engine
        self.pet_life_engine = pet_life_engine
        self.travel_quest_engine = travel_quest_engine
        self.economy_engine = economy_engine
        self.owner_intent_brain = owner_intent_brain
        self._journey_plan_cache: dict[tuple[str, str, str, bool], JourneyPlan] = {}
        self._pending_content_intents: dict[str, dict[str, object]] = {}
        self.communicator_engine: Any | None = None

    def attach_communicator_engine(self, communicator_engine: Any) -> None:
        self.communicator_engine = communicator_engine
