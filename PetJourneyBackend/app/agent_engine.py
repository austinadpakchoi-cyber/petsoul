from __future__ import annotations

from datetime import date, datetime
from math import sin, pi
from typing import Any
import uuid

from .amap_services import AMapWebServiceClient
from .agent_brain import AgentTurnContext, PetAgentBrain
from .config import Settings
from .economy_engine import PetEconomyEngine
from .event_generator import JourneyEventGenerator
from .feedback_effects import JourneyFeedbackPolicy
from .memory_store import MemoryStore
from .owner_intent_brain import OwnerIntentBrain
from .pet_life_engine import PetLifeSimulationEngine
from .pet_guide_engine import PetGuideEngine
from .place_interactions import PlaceInteractionEngine
from .providers import JourneyCity, MapProvider
from .route_planner import TravelRoutePlanner, adapt_journey_plan_to_route_plan
from .schemas import (
    AgentState,
    AgentStatus,
    ArchiveItemRequest,
    CityPosition,
    CollectSouvenirsResponse,
    DayPlan,
    DayPlanItem,
    EconomyResponse,
    EngineStepTrace,
    FeedbackResponse,
    InventoryResponse,
    ItemMutationResponse,
    ItemStatus,
    JourneyEngineTrace,
    JourneyEvent,
    JourneyPlan,
    JourneyRoutePlan,
    JourneyStatus,
    JourneyThought,
    MemoryConsolidationResult,
    MemoryRecord,
    OwnerIntentResult,
    OwnerMessageResponse,
    OwnerFundGrantRequest,
    PetAuthoredGuide,
    PetDNA,
    LifeTickResult,
    PhotoMission,
    Postcard,
    SellItemRequest,
    StaticMapAsset,
    StreetRankResponse,
    ThoughtTranslation,
    SouvenirItem,
    TravelBag,
    TravelBagItem,
    TravelBagPackRequest,
    TravelQuest,
    TravelQuestDecisionRequest,
    TravelWishRequest,
    WorldSimulationSnapshot,
)
from .street_rank import PetStreetRankEngine
from .storage import JourneyStorage, PetRecord, utcnow
from .travel_quest_engine import PetTravelQuestEngine
from .weather_provider import WeatherProvider
from .world_simulation import WorldSimulationEngine


class PetNotFoundError(Exception):
    pass


class ThoughtNotFoundError(Exception):
    pass


class TravelQuestNotFoundError(Exception):
    pass


class JourneyEngine:
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
        self.communicator_engine: Any | None = None

    def attach_communicator_engine(self, communicator_engine: Any) -> None:
        self.communicator_engine = communicator_engine

    def list_traces(self, pet_id: str, limit: int = 20) -> list[JourneyEngineTrace]:
        self._pet(pet_id)
        return self.storage.list_engine_traces(pet_id, limit=limit)

    def get_trace(self, pet_id: str, trace_id: str) -> JourneyEngineTrace:
        self._pet(pet_id)
        trace = self.storage.get_engine_trace(pet_id, trace_id)
        if not trace:
            raise KeyError(trace_id)
        return trace

    def _trace_step(
        self,
        name: str,
        *,
        started_at: datetime | None = None,
        status: str = "ok",
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
        error: str | None = None,
        fallback: str | None = None,
    ) -> EngineStepTrace:
        started = started_at or utcnow()
        return EngineStepTrace(
            name=name,
            status=status,
            started_at=started,
            finished_at=utcnow(),
            inputs=inputs or {},
            outputs=outputs or {},
            error=error,
            fallback=fallback,
        )

    def _save_trace(
        self,
        *,
        pet_id: str,
        operation: str,
        started_at: datetime,
        steps: list[EngineStepTrace],
        state_before: dict[str, Any] | None = None,
        state_after: dict[str, Any] | None = None,
        error: Exception | str | None = None,
    ) -> None:
        error_text = str(error) if error else None
        fallbacks = [step.fallback for step in steps if step.fallback]
        errors = [step.error for step in steps if step.error]
        if error_text:
            errors.append(error_text)
        trace = JourneyEngineTrace(
            id=f"trace-{uuid.uuid4().hex[:16]}",
            pet_id=pet_id,
            operation=operation,
            status="error" if error_text else "ok",
            started_at=started_at,
            finished_at=utcnow(),
            steps=steps,
            state_before=state_before or {},
            state_after=state_after or {},
            errors=errors,
            fallbacks=fallbacks,
        )
        try:
            self.storage.save_engine_trace(trace)
        except Exception:
            return

    def create_initial_journey(self, pet: PetRecord) -> None:
        city = self._city_for_elapsed(0)
        self._append_agent_thought(
            pet=pet,
            city=city,
            trigger="connecting",
            scene=f"{pet.name} 的通讯频率正在变清晰。",
            status="connecting",
            timestamp=pet.created_at,
        )
        self.storage.append_event(
            pet.pet_id,
            "旅程建立",
            f"{pet.name} 的第一段信号已经被保存。",
            timestamp=pet.created_at,
        )
        self._remember_identity(pet)

    def status(self, pet_id: str) -> AgentStatus:
        trace_started = utcnow()
        steps: list[EngineStepTrace] = []
        pet = self._pet(pet_id)
        try:
            now = utcnow()
            elapsed = (now - pet.created_at).total_seconds()
            city = self._city_for_elapsed(elapsed, now=now)
            plan = self._journey_plan_for(pet, city, now)
            snapshot = self._life_snapshot(pet=pet, city=city, plan=plan, now=now)
            status = snapshot.status
            steps.append(
                self._trace_step(
                    "world_snapshot",
                    outputs={
                        "city": snapshot.city,
                        "activity": snapshot.current_activity.title,
                        "activity_kind": snapshot.current_activity.kind,
                        "travel_day": snapshot.travel_day,
                    },
                )
            )
            if snapshot.life_tick:
                steps.append(
                    self._trace_step(
                        "memory_retrieval",
                        outputs={
                            "count": len(snapshot.life_tick.retrieved_memories),
                            "memory_types": [memory.memory_type for memory in snapshot.life_tick.retrieved_memories[:5]],
                        },
                    )
                )
                steps.append(
                    self._trace_step(
                        "life_intent",
                        outputs={
                            "intent": snapshot.life_tick.intent.kind,
                            "action": snapshot.life_tick.action.action_type,
                            "confidence": snapshot.life_tick.intent.confidence,
                        },
                    )
                )

            thoughts = [JourneyThought.model_validate(item) for item in self.storage.list_thoughts(pet_id)]
            postcards = [Postcard.model_validate(item) for item in self.storage.list_postcards(pet_id)]

            state = AgentState(
                location=snapshot.current_activity.city or snapshot.city,
                travel_day=snapshot.travel_day,
                weather=snapshot.weather,
                status=status,
                status_note=snapshot.status_note,
                energy=snapshot.energy,
                happiness=snapshot.happiness,
                curiosity=snapshot.curiosity,
                latest_thought=thoughts[-1] if thoughts else None,
                thoughts=thoughts,
            )

            result = AgentStatus(
                pet_id=pet.pet_id,
                name=pet.name,
                pet_type=pet.pet_type,
                status=status,
                agent_state=state,
                daily_logs=[
                    f"{snapshot.city} 的天气是「{snapshot.weather}」",
                    f"当前位置：{snapshot.current_activity.place_name or snapshot.current_activity.city}",
                    f"此刻：{snapshot.current_activity.title}",
                ],
                reflections=[
                    "TA 似乎更喜欢安静、有风、可以慢慢停留的地方。",
                    "你可以收藏攻略或轻轻提出建议，但 TA 会按自己的节奏选择。",
                ],
                flight_number=None,
                can_message=True,
                farewell_ready=False,
                postcards=postcards,
            )
            self._save_trace(
                pet_id=pet.pet_id,
                operation="status",
                started_at=trace_started,
                steps=steps,
                state_after={
                    "status": result.status.value,
                    "location": result.agent_state.location,
                    "postcards": len(result.postcards),
                },
            )
            return result
        except Exception as exc:
            self._save_trace(pet_id=pet.pet_id, operation="status", started_at=trace_started, steps=steps, error=exc)
            raise

    def advance_status(self, pet_id: str) -> AgentStatus:
        trace_started = utcnow()
        steps: list[EngineStepTrace] = []
        pet = self._pet(pet_id)
        try:
            now = utcnow()
            elapsed = (now - pet.created_at).total_seconds()
            city = self._city_for_elapsed(elapsed, now=now)
            status = self._status_for(now)
            self.event_generator.advance(
                pet=pet,
                city=city,
                elapsed=elapsed,
                now=now,
                status=status,
                append_agent_thought=self._append_agent_thought,
            )
            steps.append(
                self._trace_step(
                    "agent_speech",
                    outputs={"status": status.value, "city": city.name, "event_generator": self.event_generator.__class__.__name__},
                )
            )
            if self.communicator_engine is not None:
                self.communicator_engine.resolve_pending_for_pet(pet_id)
                steps.append(self._trace_step("fallback_or_pending_resolution", outputs={"communicator_pending_checked": True}))
            result = self.status(pet_id)
            self._save_trace(
                pet_id=pet.pet_id,
                operation="advance_status",
                started_at=trace_started,
                steps=steps,
                state_after={"status": result.status.value, "location": result.agent_state.location},
            )
            return result
        except Exception as exc:
            self._save_trace(pet_id=pet.pet_id, operation="advance_status", started_at=trace_started, steps=steps, error=exc)
            raise

    def day_plan(self, pet_id: str) -> DayPlan:
        pet = self._pet(pet_id)
        status = self.status(pet_id)
        now = utcnow()
        elapsed = (now - pet.created_at).total_seconds()
        city_context = self._city_for_elapsed(elapsed, now=now)
        journey_plan = self._journey_plan_for(pet, city_context, now)
        city = journey_plan.city
        events = [JourneyEvent.model_validate(item) for item in self.storage.list_events(pet_id)]
        thoughts = status.agent_state.thoughts[-4:]

        return DayPlan(
            id=f"day-plan-{pet.pet_id}",
            location=city,
            view_mode="agent_timeline",
            stay_duration="会在这个城市停留 1-2 天，期间按真实时间走走停停",
            day_plan=[
                DayPlanItem(
                    id=stop.id,
                    time=stop.planned_time or "--:--",
                    title=stop.title,
                    detail=self._stop_detail(stop),
                    kind=self._day_plan_kind(stop.planned_time),
                )
                for stop in journey_plan.stops
            ],
            scheduled_transport=journey_plan.scheduled_transport,
            thoughts=thoughts,
            events_today=events,
        )

    def city_position(self, pet_id: str) -> CityPosition:
        pet = self._pet(pet_id)
        elapsed = (utcnow() - pet.created_at).total_seconds()
        return self._city_for_elapsed(elapsed).position

    def route_plan(self, pet_id: str) -> JourneyRoutePlan:
        pet = self._pet(pet_id)
        now = utcnow()
        elapsed = (now - pet.created_at).total_seconds()
        city = self._city_for_elapsed(elapsed, now=now)
        return adapt_journey_plan_to_route_plan(self._journey_plan_for(pet, city, now))

    def journey_plan(self, pet_id: str) -> JourneyPlan:
        pet = self._pet(pet_id)
        now = utcnow()
        elapsed = (now - pet.created_at).total_seconds()
        city = self._city_for_elapsed(elapsed, now=now)
        return self._journey_plan_for(pet, city, now)

    def pet_guide(self, pet_id: str) -> PetAuthoredGuide:
        pet = self._pet(pet_id)
        now = utcnow()
        elapsed = (now - pet.created_at).total_seconds()
        city = self._city_for_elapsed(elapsed, now=now)
        plan = self._journey_plan_for(pet, city, now)
        return self.pet_guide_engine.build_pet_guide(pet, plan, now)

    def create_travel_quest(self, pet_id: str, request: TravelWishRequest) -> TravelQuest:
        pet = self._pet(pet_id)
        now = utcnow()
        elapsed = (now - pet.created_at).total_seconds()
        city = self._city_for_elapsed(elapsed, now=now)
        plan = self._journey_plan_for(pet, city, now)
        quest = self.travel_quest_engine.create_quest(
            pet=pet,
            request=request,
            current_city=city,
            current_plan=plan,
            now=now,
        )
        self.storage.save_travel_quest(quest)
        self._append_agent_thought(
            pet=pet,
            city=city,
            trigger="travel_quest_guide_ready",
            scene=quest.current_phase_message,
            status=self._status_for(now),
            timestamp=now,
        )
        self.storage.append_event(
            pet.pet_id,
            "TA 做好一份旅行攻略",
            f"{pet.name} 根据你的想法整理了去 {quest.destination} 的小攻略，还没有立刻出发。",
            timestamp=now,
        )
        self._remember_travel_quest(pet=pet, quest=quest, city=city.name)
        return quest

    def list_travel_quests(self, pet_id: str, limit: int = 20) -> list[TravelQuest]:
        self._pet(pet_id)
        return self.storage.list_travel_quests(pet_id, limit=limit)

    def get_travel_quest(self, pet_id: str, quest_id: str) -> TravelQuest:
        self._pet(pet_id)
        quest = self.storage.get_travel_quest(pet_id, quest_id)
        if not quest:
            raise TravelQuestNotFoundError(quest_id)
        return quest

    def prepare_travel_quest(self, pet_id: str, quest_id: str) -> TravelQuest:
        pet = self._pet(pet_id)
        quest = self.get_travel_quest(pet_id, quest_id)
        now = utcnow()
        elapsed = (now - pet.created_at).total_seconds()
        city = self._city_for_elapsed(elapsed, now=now)
        updated = self.travel_quest_engine.prepare_departure(
            pet=pet,
            quest=quest,
            current_city=city,
            now=now,
        )
        self.storage.save_travel_quest(updated)
        self._append_agent_thought(
            pet=pet,
            city=city,
            trigger="travel_quest_preparing",
            scene=updated.current_phase_message,
            status=self._status_for(now),
            timestamp=now,
        )
        self.storage.append_event(
            pet.pet_id,
            "TA 开始准备出发",
            f"{pet.name} 接受了这份攻略，开始准备去 {updated.destination}。",
            timestamp=now,
        )
        self._remember_travel_quest(pet=pet, quest=updated, city=city.name)
        return updated

    def travel_quest_post_event_options(self, pet_id: str, quest_id: str) -> TravelQuest:
        pet = self._pet(pet_id)
        quest = self.get_travel_quest(pet_id, quest_id)
        now = utcnow()
        updated = self.travel_quest_engine.build_post_event_options(pet=pet, quest=quest, now=now)
        self.storage.save_travel_quest(updated)
        city = self._city_for_elapsed((now - pet.created_at).total_seconds(), now=now)
        self._append_agent_thought(
            pet=pet,
            city=city,
            trigger="travel_quest_return_planning",
            scene=updated.current_phase_message,
            status=self._status_for(now),
            timestamp=now,
        )
        self.storage.append_event(
            pet.pet_id,
            "TA 开始整理赛后下一步",
            f"{pet.name} 看完这段旅程后，开始考虑回到原来的地方、留下，或继续去下一座城市。",
            timestamp=now,
        )
        self._remember_travel_quest(pet=pet, quest=updated, city=city.name)
        return updated

    def select_travel_quest_next_step(
        self,
        pet_id: str,
        quest_id: str,
        request: TravelQuestDecisionRequest,
    ) -> TravelQuest:
        pet = self._pet(pet_id)
        quest = self.get_travel_quest(pet_id, quest_id)
        now = utcnow()
        updated = self.travel_quest_engine.select_next_step(
            pet=pet,
            quest=quest,
            request=request,
            now=now,
        )
        self.storage.save_travel_quest(updated)
        city = self._city_for_elapsed((now - pet.created_at).total_seconds(), now=now)
        self._append_agent_thought(
            pet=pet,
            city=city,
            trigger=f"travel_quest_next_step_{updated.status.value}",
            scene=updated.current_phase_message,
            status=self._status_for(now),
            timestamp=now,
        )
        self.storage.append_event(
            pet.pet_id,
            "TA 选好了赛后的下一段路",
            updated.current_phase_message,
            timestamp=now,
        )
        self._remember_travel_quest(pet=pet, quest=updated, city=city.name)
        return updated

    def get_travel_bag(self, pet_id: str, quest_id: str | None = None) -> TravelBag:
        self._pet(pet_id)
        if quest_id:
            self.get_travel_quest(pet_id, quest_id)
        existing = self.storage.get_travel_bag(pet_id, quest_id=quest_id)
        if existing:
            return existing
        return self._empty_travel_bag(pet_id=pet_id, quest_id=quest_id, now=utcnow())

    def pack_travel_bag(self, pet_id: str, request: TravelBagPackRequest) -> TravelBag:
        pet = self._pet(pet_id)
        quest = self.get_travel_quest(pet_id, request.quest_id) if request.quest_id else None
        now = utcnow()
        existing = self.storage.get_travel_bag(pet_id, quest_id=request.quest_id)
        bag = existing or self._empty_travel_bag(pet_id=pet_id, quest_id=request.quest_id, now=now)
        new_items = [
            TravelBagItem(
                id=f"TBI-{uuid.uuid4().hex[:8].upper()}",
                item_type=item.item_type,
                title=item.title.strip(),
                note=item.note.strip() if item.note else None,
                influence_tags=[tag.strip() for tag in item.influence_tags if tag.strip()][:6],
                added_at=now,
            )
            for item in request.items
            if item.title.strip()
        ]
        merged_items = [*bag.items, *new_items][-12:]
        updated = bag.model_copy(
            update={
                "items": merged_items,
                "owner_message": request.owner_message.strip() if request.owner_message else bag.owner_message,
                "pet_visible_note": self._travel_bag_note(merged_items),
                "updated_at": now,
            }
        )
        self.storage.save_travel_bag(updated)
        if quest:
            quest = quest.model_copy(update={"travel_bag": updated, "updated_at": now})
            self.storage.save_travel_quest(quest)
        if new_items or request.owner_message:
            item_titles = "、".join(item.title for item in new_items) or "一句轻轻的叮嘱"
            self.storage.append_event(
                pet.pet_id,
                "旅行小包更新",
                f"你往小包里放进了：{item_titles}。",
                timestamp=now,
            )
            self._remember_travel_bag(pet=pet, bag=updated, new_items=new_items)
        return updated

    def list_souvenirs(self, pet_id: str, limit: int = 50) -> list[SouvenirItem]:
        self._pet(pet_id)
        return self.storage.list_souvenirs(pet_id, limit=limit)

    def economy(self, pet_id: str) -> EconomyResponse:
        self._pet(pet_id)
        return self.economy_engine.economy(pet_id)

    def inventory(self, pet_id: str, status: ItemStatus | None = ItemStatus.owned, limit: int = 50) -> InventoryResponse:
        self._pet(pet_id)
        return self.economy_engine.inventory(pet_id, status=status, limit=limit)

    def collect_travel_quest_souvenirs(self, pet_id: str, quest_id: str) -> list[SouvenirItem]:
        return self.collect_travel_quest_souvenirs_response(pet_id, quest_id).items

    def collect_travel_quest_souvenirs_response(self, pet_id: str, quest_id: str) -> CollectSouvenirsResponse:
        pet = self._pet(pet_id)
        quest = self.get_travel_quest(pet_id, quest_id)
        existing = self.storage.list_souvenirs_for_quest(pet_id, quest_id)
        now = utcnow()
        generated = existing
        if not generated:
            bag = quest.travel_bag or self.storage.get_travel_bag(pet_id, quest_id=quest_id)
            generated = self.travel_quest_engine.generate_souvenirs(pet=pet, quest=quest, bag=bag, now=now)
            generated = self._attach_souvenir_images(pet=pet, souvenirs=generated)
        city = self._city_for_elapsed((now - pet.created_at).total_seconds(), now=now)
        response = self.economy_engine.collect_souvenirs(
            pet=pet,
            quest=quest,
            souvenirs=generated,
            weather=city.weather,
            now=now,
        )
        updated_quest = quest.model_copy(update={"souvenir_preview": response.items, "updated_at": now})
        self.storage.save_travel_quest(updated_quest)
        if response.items and not existing:
            names = "、".join(item.title for item in response.items[:3])
            self.storage.append_event(
                pet.pet_id,
                "TA 带回了一点小东西",
                f"{pet.name} 从 {quest.destination} 带回了：{names}。",
                timestamp=now,
            )
            for souvenir in response.items:
                self._remember_souvenir(pet=pet, souvenir=souvenir)
        return response

    def _attach_souvenir_images(self, *, pet: PetRecord, souvenirs: list[SouvenirItem]) -> list[SouvenirItem]:
        if not self.settings.souvenir_images_enabled:
            return souvenirs
        budget = max(0, self.settings.souvenir_image_max_count)
        updated: list[SouvenirItem] = []
        for souvenir in souvenirs:
            if budget <= 0 or souvenir.image_url:
                updated.append(souvenir)
                continue
            image_url = self.event_generator.souvenir_image_url(pet=pet, souvenir=souvenir)
            if image_url:
                souvenir = souvenir.model_copy(update={"image_url": image_url})
                budget -= 1
            updated.append(souvenir)
        return updated

    def sell_item(self, pet_id: str, item_id: str, request: SellItemRequest) -> ItemMutationResponse:
        self._pet(pet_id)
        return self.economy_engine.sell_item(pet_id=pet_id, item_id=item_id, request=request, now=utcnow())

    def archive_item(self, pet_id: str, item_id: str, request: ArchiveItemRequest) -> ItemMutationResponse:
        self._pet(pet_id)
        return self.economy_engine.archive_item(pet_id=pet_id, item_id=item_id, request=request, now=utcnow())

    def grant_owner_fund(self, pet_id: str, request: OwnerFundGrantRequest) -> EconomyResponse:
        self._pet(pet_id)
        return self.economy_engine.grant_owner_fund(pet_id=pet_id, request=request, now=utcnow())

    def world_snapshot(self, pet_id: str) -> WorldSimulationSnapshot:
        pet = self._pet(pet_id)
        now = utcnow()
        elapsed = (now - pet.created_at).total_seconds()
        city = self._city_for_elapsed(elapsed, now=now)
        plan = self._journey_plan_for(pet, city, now)
        return self._life_snapshot(pet=pet, city=city, plan=plan, now=now)

    def life_tick(self, pet_id: str) -> LifeTickResult:
        snapshot = self.world_snapshot(pet_id)
        if snapshot.life_tick is None:
            raise RuntimeError("life tick unavailable")
        return snapshot.life_tick

    def street_rank(self, pet_id: str, theme: str) -> StreetRankResponse:
        pet = self._pet(pet_id)
        now = utcnow()
        elapsed = (now - pet.created_at).total_seconds()
        city = self._city_for_elapsed(elapsed, now=now)
        return self.street_rank_engine.rank(pet=pet, city=city, theme=theme, weather=city.weather, now=now)

    def static_map_for_pet(self, pet_id: str, zoom: int = 14) -> StaticMapAsset:
        pet = self._pet(pet_id)
        elapsed = (utcnow() - pet.created_at).total_seconds()
        city = self._city_for_elapsed(elapsed)
        return self.amap_client.static_map_asset(center_lat=city.lat, center_lng=city.lng, zoom=zoom)

    def photo_mission(self, pet_id: str) -> PhotoMission:
        trace_started = utcnow()
        steps: list[EngineStepTrace] = []
        pet = self._pet(pet_id)
        try:
            now = utcnow()
            elapsed = (now - pet.created_at).total_seconds()
            city = self._city_for_elapsed(elapsed, now=now)
            plan = self._journey_plan_for(pet, city, now)
            snapshot = self.world_simulation_engine.snapshot(pet=pet, city=city, plan=plan, now=now)
            steps.append(
                self._trace_step(
                    "world_snapshot",
                    outputs={"city": snapshot.city, "activity": snapshot.current_activity.title, "places": len(plan.places)},
                )
            )
            mission = self.place_interaction_engine.build_photo_mission(
                pet=pet,
                activity=snapshot.current_activity,
                places=plan.places,
                weather=snapshot.weather,
                now=now,
                worldcup_event=plan.worldcup_event,
            )
            steps.append(
                self._trace_step(
                    "photo_mission",
                    outputs={
                        "mission_id": mission.id,
                        "place_id": mission.place.id,
                        "place_name": mission.place.name,
                        "quality_report": mission.quality_report.model_dump(mode="json") if mission.quality_report else None,
                    },
                    fallback="photo_mission_quality_retry_needed" if mission.failure_category else None,
                )
            )
            self._save_trace(
                pet_id=pet.pet_id,
                operation="photo_mission",
                started_at=trace_started,
                steps=steps,
                state_after={"mission_id": mission.id, "place": mission.place.name, "failure_category": mission.failure_category},
            )
            return mission
        except Exception as exc:
            self._save_trace(pet_id=pet.pet_id, operation="photo_mission", started_at=trace_started, steps=steps, error=exc)
            raise

    def generate_selfie(self, pet_id: str) -> Postcard:
        trace_started = utcnow()
        steps: list[EngineStepTrace] = []
        pet = self._pet(pet_id)
        try:
            now = utcnow()
            elapsed = (now - pet.created_at).total_seconds()
            city = self._city_for_elapsed(elapsed, now=now)
            mission = self.photo_mission(pet_id)
            steps.append(
                self._trace_step(
                    "photo_mission",
                    outputs={"mission_id": mission.id, "place": mission.place.name, "quality": mission.quality_report.model_dump(mode="json") if mission.quality_report else None},
                    fallback="photo_mission_quality_retry_needed" if mission.failure_category else None,
                )
            )
            existing = self.storage.find_postcard_by_mission(pet.pet_id, mission.id)
            if existing:
                result = Postcard.model_validate(existing)
                steps.append(self._trace_step("action_validation", outputs={"deduped_by_mission": True}))
                self._save_trace(
                    pet_id=pet.pet_id,
                    operation="generate_selfie",
                    started_at=trace_started,
                    steps=steps,
                    state_after={"postcard_id": result.id, "reused": True},
                )
                return result
            latest = self.storage.latest_postcard(pet.pet_id)
            if latest and (now - latest["timestamp"]).total_seconds() < 20 * 60:
                result = Postcard.model_validate(latest)
                steps.append(self._trace_step("action_validation", outputs={"cooldown_reused_latest": True}))
                self._save_trace(
                    pet_id=pet.pet_id,
                    operation="generate_selfie",
                    started_at=trace_started,
                    steps=steps,
                    state_after={"postcard_id": result.id, "reused": True},
                )
                return result
            postcard = Postcard.model_validate(self.event_generator.generate_selfie_postcard(pet, city, now, mission=mission))
            steps.append(
                self._trace_step(
                    "photo_generation",
                    outputs={"postcard_id": postcard.id, "has_image": bool(postcard.image_url), "mission_id": mission.id},
                    fallback=None if postcard.image_url else "image_provider_returned_empty_or_fallback",
                )
            )
            self._append_agent_thought(
                pet=pet,
                city=city,
                trigger="selfie",
                scene=f"我在 {postcard.location} 拍了一张照片给你。{mission.interaction.pet_action}。",
                status=self._status_for(now),
                timestamp=now,
            )
            steps.append(self._trace_step("agent_speech", outputs={"trigger": "selfie"}))
            self._remember_postcard(pet, postcard, mission=mission)
            steps.append(self._trace_step("memory_write", outputs={"kind": "postcard", "mission_id": mission.id}))
            self._save_trace(
                pet_id=pet.pet_id,
                operation="generate_selfie",
                started_at=trace_started,
                steps=steps,
                state_after={"postcard_id": postcard.id, "location": postcard.location, "has_image": bool(postcard.image_url)},
            )
            return postcard
        except Exception as exc:
            self._save_trace(pet_id=pet.pet_id, operation="generate_selfie", started_at=trace_started, steps=steps, error=exc)
            raise

    def list_memories(self, pet_id: str, limit: int = 50) -> list[MemoryRecord]:
        self._pet(pet_id)
        return self.memory_store.list_memories(pet_id, limit=max(1, min(100, limit)))

    def add_memory(
        self,
        *,
        pet_id: str,
        kind: str,
        title: str,
        content: str,
        salience: float,
        source: str,
        metadata: dict[str, object] | None = None,
        memory_type: str = "episodic",
        importance: float | None = None,
        emotional_valence: float = 0.0,
        confidence: float = 1.0,
        source_event_id: str | None = None,
        structured_payload: dict[str, object] | None = None,
    ) -> MemoryRecord:
        self._pet(pet_id)
        return self.memory_store.add_memory(
            pet_id=pet_id,
            kind=kind,
            title=title,
            content=content,
            salience=salience,
            source=source,
            metadata=metadata,
            memory_type=memory_type,
            importance=importance,
            emotional_valence=emotional_valence,
            confidence=confidence,
            source_event_id=source_event_id,
            structured_payload=structured_payload,
        )

    def update_memory(
        self,
        *,
        pet_id: str,
        memory_id: str,
        kind: str | None = None,
        title: str | None = None,
        content: str | None = None,
        salience: float | None = None,
        source: str | None = None,
        metadata: dict[str, object] | None = None,
        memory_type: str | None = None,
        importance: float | None = None,
        emotional_valence: float | None = None,
        confidence: float | None = None,
        source_event_id: str | None = None,
        structured_payload: dict[str, object] | None = None,
    ) -> MemoryRecord:
        self._pet(pet_id)
        return self.memory_store.update_memory(
            pet_id=pet_id,
            memory_id=memory_id,
            kind=kind,
            title=title,
            content=content,
            salience=salience,
            source=source,
            metadata=metadata,
            memory_type=memory_type,
            importance=importance,
            emotional_valence=emotional_valence,
            confidence=confidence,
            source_event_id=source_event_id,
            structured_payload=structured_payload,
        )

    def delete_memory(self, pet_id: str, memory_id: str) -> bool:
        self._pet(pet_id)
        deleted = self.memory_store.delete_memory(pet_id, memory_id)
        if not deleted:
            raise KeyError(memory_id)
        return deleted

    def search_memories(self, pet_id: str, query: str, limit: int = 8) -> list[MemoryRecord]:
        self._pet(pet_id)
        return self.memory_store.search_memories(pet_id, query=query, limit=max(1, min(30, limit)))

    def consolidate_daily_memories(self, pet_id: str, target_date: date) -> MemoryConsolidationResult:
        self._pet(pet_id)
        return self.memory_store.consolidate_daily_memories(pet_id, target_date)

    def pet_dna(self, pet_id: str):
        return self._pet(pet_id).dna

    def update_pet_dna(self, pet_id: str, dna: PetDNA) -> PetDNA:
        self._pet(pet_id)
        updated = self.storage.update_pet_dna(pet_id, dna)
        if not updated:
            raise PetNotFoundError(pet_id)
        self.memory_store.add_memory(
            pet_id=pet_id,
            kind="dna_update",
            title=f"{updated.name} 的通讯 DNA 更新",
            content=(
                f"主人称呼：{dna.owner_title}；性格：{dna.personality}；"
                f"喜欢的地方：{'、'.join(dna.favorite_places)}；爱好：{'、'.join(dna.hobby)}；"
                f"口头禅：{dna.catchphrase}；说话风格：{dna.voice_style}。"
            ),
            salience=0.82,
            source="owner_dna_editor",
            memory_type="preference",
            importance=0.86,
            emotional_valence=0.25,
            confidence=1.0,
            structured_payload=dna.model_dump(by_alias=True),
        )
        return updated.dna

    def thought_translation(self, pet_id: str, thought_id: str) -> ThoughtTranslation:
        self._pet(pet_id)
        thought = self.storage.get_thought(pet_id, thought_id, include_translation=True)
        if not thought or not thought["translation"]:
            raise ThoughtNotFoundError(thought_id)
        return ThoughtTranslation(
            thought_id=thought["id"],
            pet_id=pet_id,
            animal_text=thought["animal_text"] or thought["text"],
            translation=thought["translation"],
            tone=thought["tone"],
            language_style=thought["language_style"],
            model=thought["model"],
        )

    def feedback(self, pet_id: str, city: str, liked: bool) -> FeedbackResponse:
        pet = self._pet(pet_id)
        now = utcnow()
        current_city = self._city_for_elapsed((now - pet.created_at).total_seconds(), now=now)
        self.storage.save_feedback(pet.pet_id, city, liked)
        effect = self.feedback_policy.resolve(pet, liked)
        self._append_agent_thought(
            pet=pet,
            city=current_city,
            trigger=effect.thought_tone,
            scene=effect.message,
            status=self._status_for(utcnow()),
        )
        self.storage.append_event(pet.pet_id, effect.event_title, effect.event_detail)
        self._remember_feedback(pet=pet, city=city, liked=liked, message=effect.message)
        return FeedbackResponse(success=True, message=effect.message, updated_status=self.status(pet.pet_id))

    def owner_message(self, pet_id: str, message: str, intent_hint: str | None = None) -> OwnerMessageResponse:
        trace_started = utcnow()
        steps: list[EngineStepTrace] = []
        pet = self._pet(pet_id)
        cleaned = " ".join(message.strip().split())
        if not cleaned:
            raise ValueError("empty owner message")
        try:
            now = utcnow()
            city = self._city_for_elapsed((now - pet.created_at).total_seconds(), now=now)
            owner_intent = self.owner_intent_brain.classify(pet=pet, message=cleaned, intent_hint=intent_hint)
            decision = owner_intent.decision or self._owner_message_decision(cleaned, intent_hint=intent_hint)
            steps.append(
                self._trace_step(
                    "owner_intent",
                    inputs={"intent_hint": intent_hint or ""},
                    outputs=owner_intent.model_dump(mode="json"),
                    fallback="rule_owner_intent" if self.owner_intent_brain.provider_name.startswith("rule") else None,
                )
            )
            scene = self._owner_message_scene(pet, cleaned, decision, owner_intent=owner_intent)
            steps.append(
                self._trace_step(
                    "action_validation",
                    outputs={
                        "should_affect_route": owner_intent.should_affect_route,
                        "route_forced": False,
                        "decision": decision,
                    },
                )
            )
            self._append_agent_thought(
                pet=pet,
                city=city,
                trigger=f"owner_message_{decision}",
                scene=scene,
                status=self._status_for(now),
                timestamp=now,
            )
            steps.append(self._trace_step("agent_speech", outputs={"response_policy": owner_intent.response_policy}))
            self.storage.append_event(
                pet.pet_id,
                self._owner_message_event_title(decision),
                self._owner_message_event_detail(pet=pet, message=cleaned, decision=decision),
                timestamp=now,
            )
            if owner_intent.should_write_memory:
                self._remember_owner_message(
                    pet=pet,
                    message=cleaned,
                    decision=decision,
                    scene=scene,
                    city=city.name,
                    owner_intent=owner_intent,
                )
                steps.append(self._trace_step("memory_write", outputs={"kind": "owner_message", "intent": owner_intent.intent}))
            else:
                steps.append(self._trace_step("memory_write", status="skipped", outputs={"reason": owner_intent.response_policy}))
            latest = self.storage.list_thoughts(pet.pet_id, limit=1)[-1]
            response = OwnerMessageResponse(
                success=True,
                decision=decision,
                message=scene,
                thought=JourneyThought.model_validate(latest),
                updated_status=self.status(pet.pet_id),
                owner_intent=owner_intent,
            )
            self._save_trace(
                pet_id=pet.pet_id,
                operation="owner_message",
                started_at=trace_started,
                steps=steps,
                state_after={"decision": decision, "intent": owner_intent.intent, "should_affect_route": owner_intent.should_affect_route},
            )
            return response
        except Exception as exc:
            self._save_trace(pet_id=pet.pet_id, operation="owner_message", started_at=trace_started, steps=steps, error=exc)
            raise

    def record_communicator_reply(
        self,
        *,
        pet_id: str,
        trigger: str,
        scene: str,
        decision: str,
    ) -> JourneyThought:
        pet = self._pet(pet_id)
        now = utcnow()
        city = self._city_for_elapsed((now - pet.created_at).total_seconds(), now=now)
        self._append_agent_thought(
            pet=pet,
            city=city,
            trigger=trigger,
            scene=scene,
            status=self._status_for(now),
            timestamp=now,
        )
        self.storage.append_event(
            pet.pet_id,
            "TA 在手机里回应了你",
            scene,
            timestamp=now,
        )
        self._remember_safely(
            pet_id=pet.pet_id,
            kind="communicator_reply",
            title="手机回应",
            content=f"TA 在手机里回应：{scene}。决策：{decision}",
            salience=0.64,
            source="communicator_reply",
            metadata={"decision": decision},
        )
        latest = self.storage.list_thoughts(pet.pet_id, limit=1)[-1]
        return JourneyThought.model_validate(latest)

    def _city_for_elapsed(self, elapsed: float, now: datetime | None = None) -> JourneyCity:
        city = self.map_provider.city_for_elapsed(elapsed)
        return self.weather_provider.city_with_weather(city, now=now)

    def _append_agent_thought(
        self,
        pet: PetRecord,
        city: JourneyCity,
        trigger: str,
        scene: str,
        status: JourneyStatus | str,
        timestamp: datetime | None = None,
    ) -> None:
        speech = self.agent_brain.speak(
            AgentTurnContext(
                pet=pet,
                city=city,
                status=status,
                trigger=trigger,
                scene=scene,
            )
        )
        self.storage.append_thought(
            pet.pet_id,
            speech.animal_text,
            tone=speech.tone,
            timestamp=timestamp,
            animal_text=speech.animal_text,
            translation=speech.translation,
            language_style=speech.language_style,
            model=speech.model,
        )

    def _life_snapshot(
        self,
        *,
        pet: PetRecord,
        city: JourneyCity,
        plan: JourneyPlan,
        now: datetime,
        owner_signal: str | None = None,
    ) -> WorldSimulationSnapshot:
        snapshot = self.world_simulation_engine.snapshot(pet=pet, city=city, plan=plan, now=now)
        life_tick = self.pet_life_engine.tick(
            pet=pet,
            city=city,
            plan=plan,
            snapshot=snapshot,
            now=now,
            owner_signal=owner_signal,
        )
        return snapshot.model_copy(update={"life_tick": life_tick})

    def _journey_plan_for(self, pet: PetRecord, city: JourneyCity, now: datetime) -> JourneyPlan:
        local_day = now.astimezone().date().isoformat()
        key = (pet.pet_id, city.name, local_day, bool(self.settings.worldcup_demo_enabled))
        cached = self._journey_plan_cache.get(key)
        if cached:
            return cached
        plan = self.route_planner.build_journey_plan(pet, city, now)
        self._journey_plan_cache[key] = plan
        return plan

    def _pet(self, pet_id: str) -> PetRecord:
        pet = self.storage.get_pet(pet_id)
        if not pet:
            raise PetNotFoundError(pet_id)
        return pet

    def _empty_travel_bag(self, *, pet_id: str, quest_id: str | None, now: datetime) -> TravelBag:
        return TravelBag(
            id=self.storage.travel_bag_id(pet_id, quest_id),
            pet_id=pet_id,
            quest_id=quest_id,
            items=[],
            owner_message=None,
            pet_visible_note="这只小包还空着。出发前可以放一点小零食、护身符，或一句想让 TA 带着走的话。",
            updated_at=now,
        )

    def _travel_bag_note(self, items: list[TravelBagItem]) -> str:
        if not items:
            return "这只小包还空着。出发前可以放一点小零食、护身符，或一句想让 TA 带着走的话。"
        titles = "、".join(item.title for item in items[-4:])
        return f"我把 {titles} 收进小包里了。它们不会替我决定路线，但会在路上提醒我慢一点、记得回来。"

    def _remember_identity(self, pet: PetRecord) -> None:
        content = (
            f"{pet.name} 是一只 {pet.pet_type.value}。主人称呼：{pet.dna.owner_title}。"
            f"性格：{pet.dna.personality}。喜欢的地方：{', '.join(pet.dna.favorite_places)}。"
            f"爱做的事：{', '.join(pet.dna.hobby)}。常被记住的一句话：{pet.dna.catchphrase}。"
            f"声音风格：{pet.dna.voice_style}。"
        )
        self._remember_safely(
            pet_id=pet.pet_id,
            kind="identity",
            title=f"{pet.name} 的通讯 DNA",
            content=content,
            salience=0.95,
            source="onboarding",
            metadata={"pet_type": pet.pet_type.value, "photo_path": pet.photo_path or ""},
            memory_type="relationship",
            importance=0.96,
            emotional_valence=0.38,
            confidence=0.98,
            structured_payload={"favorite_places": pet.dna.favorite_places, "hobby": pet.dna.hobby},
        )

    def _remember_travel_bag(self, *, pet: PetRecord, bag: TravelBag, new_items: list[TravelBagItem]) -> None:
        if new_items:
            item_text = "、".join(
                f"{item.title}（{item.item_type.value}）" for item in new_items
            )
        else:
            item_text = "你留了一句路上的叮嘱"
        self._remember_safely(
            pet_id=pet.pet_id,
            kind="travel_bag",
            title=f"{pet.name} 的旅行小包",
            content=(
                f"你给 {pet.name} 准备了：{item_text}。"
                f"这些物品只影响旅途倾向和情绪，不直接控制目的地。"
                f"小包提示：{bag.pet_visible_note}"
            ),
            salience=0.84,
            source="travel_bag",
            metadata={
                "quest_id": bag.quest_id or "",
                "bag_id": bag.id,
                "item_count": len(bag.items),
                "influence_tags": [tag for item in bag.items for tag in item.influence_tags],
            },
            memory_type="preference",
            importance=0.84,
            emotional_valence=0.34,
            confidence=0.86,
            structured_payload={
                "quest_id": bag.quest_id or "",
                "influence_tags": [tag for item in bag.items for tag in item.influence_tags],
                "soft_influence_only": True,
            },
        )

    def _remember_souvenir(self, *, pet: PetRecord, souvenir: SouvenirItem) -> None:
        self._remember_safely(
            pet_id=pet.pet_id,
            kind="souvenir",
            title=souvenir.title,
            content=(
                f"{pet.name} 从 {souvenir.city} · {souvenir.place_name} 带回 {souvenir.title}。"
                f"故事：{souvenir.story}。TA 的话：{souvenir.pet_voice}"
            ),
            salience=0.82 if souvenir.rarity == "common" else 0.9,
            source="souvenir",
            metadata={
                "souvenir_id": souvenir.id,
                "quest_id": souvenir.quest_id or "",
                "item_type": souvenir.item_type.value,
                "city": souvenir.city,
                "place_name": souvenir.place_name,
                "rarity": souvenir.rarity,
                "bag_influence_tags": souvenir.bag_influence_tags,
            },
            memory_type="souvenir",
            importance=0.82 if souvenir.rarity == "common" else 0.9,
            emotional_valence=0.48,
            confidence=0.85,
            source_event_id=souvenir.source_photo_mission_id,
            structured_payload={
                "souvenir_id": souvenir.id,
                "quest_id": souvenir.quest_id or "",
                "city": souvenir.city,
                "place_name": souvenir.place_name,
                "bag_influence_tags": souvenir.bag_influence_tags,
            },
        )

    def _remember_feedback(self, pet: PetRecord, city: str, liked: bool, message: str) -> None:
        owner_signal = "收藏了这个攻略方向" if liked else "暂时略过了这个攻略方向"
        self._remember_safely(
            pet_id=pet.pet_id,
            kind="owner_preference",
            title=f"{city} 的主人反馈",
            content=(
                f"你{owner_signal}。这只是你的旅行参考偏好，"
                f"不会直接决定 {pet.name} 对地点的感受。系统反馈：{message}"
            ),
            salience=0.72,
            source="feedback",
            metadata={"city": city, "liked": liked},
            memory_type="preference",
            importance=0.72,
            emotional_valence=0.28 if liked else -0.08,
            confidence=0.78,
            structured_payload={"city": city, "liked": liked, "soft_route_bias_only": True},
        )

    def _remember_postcard(self, pet: PetRecord, postcard: Postcard, mission: PhotoMission | None = None) -> None:
        metadata: dict[str, object] = {"postcard_id": postcard.id, "image_url": postcard.image_url or ""}
        if mission:
            metadata.update(
                {
                    "photo_mission_id": mission.id,
                    "scene_anchor": mission.scene_anchor,
                    "camera_perspective": mission.camera_perspective.value,
                    "interaction_type": mission.interaction.interaction_type,
                }
            )
        self._remember_safely(
            pet_id=pet.pet_id,
            kind="postcard",
            title=f"{postcard.location} 的自拍/明信片",
            content=f"{pet.name} 从 {postcard.location} 发来内容：{postcard.text}",
            salience=0.86,
            source="postcard",
            metadata=metadata,
            memory_type="recent_episodic",
            importance=0.86,
            emotional_valence=0.42,
            confidence=0.82,
            source_event_id=mission.id if mission else None,
            structured_payload=metadata,
        )

    def _remember_safely(
        self,
        *,
        pet_id: str,
        kind: str,
        title: str,
        content: str,
        salience: float,
        source: str,
        metadata: dict[str, object] | None = None,
        memory_type: str = "episodic",
        importance: float | None = None,
        emotional_valence: float = 0.0,
        confidence: float = 1.0,
        source_event_id: str | None = None,
        structured_payload: dict[str, object] | None = None,
    ) -> None:
        try:
            self.memory_store.add_memory(
                pet_id=pet_id,
                kind=kind,
                title=title,
                content=content,
                salience=salience,
                source=source,
                metadata=metadata,
                memory_type=memory_type,
                importance=importance,
                emotional_valence=emotional_valence,
                confidence=confidence,
                source_event_id=source_event_id,
                structured_payload=structured_payload,
            )
        except Exception:
            return

    def _owner_message_decision(self, message: str, intent_hint: str | None = None) -> str:
        normalized = f"{intent_hint or ''} {message}".lower()
        travel_words = ("去", "看看", "想去", "咖啡", "海", "公园", "店", "球赛", "世界杯", "比赛", "攻略")
        care_words = ("想你", "晚安", "早安", "抱抱", "注意", "休息", "爱你")
        if any(word in normalized for word in care_words):
            return "comfort"
        if any(word in normalized for word in travel_words):
            score = sum(ord(ch) for ch in message) % 10
            if score in {0, 1, 2}:
                return "declined"
            if score in {3, 4}:
                return "remembered"
            return "accepted"
        return "remembered"

    def _owner_message_scene(
        self,
        pet: PetRecord,
        message: str,
        decision: str,
        owner_intent: OwnerIntentResult | None = None,
    ) -> str:
        owner = self._owner_reference(pet.dna.owner_title)
        if owner_intent and owner_intent.intent == "unsafe_grief":
            return (
                f"我听见{owner}说「{message}」。我会在这里陪你一小会儿，但我不是医生，也不能证明另一个世界。"
                "如果你现在可能伤害自己，请立刻联系身边可信的人或当地紧急电话。你不需要一个人扛过这一刻。"
            )
        if owner_intent and owner_intent.intent == "photo_request":
            return f"我听见{owner}说「{message}」。等当前位置适合拍照时，我会把这一刻发给你；路线还是按真实时间慢慢走。"
        if owner_intent and owner_intent.intent == "care_instruction":
            return f"我听见{owner}说「{message}」。我会把这句话当成小包里的叮嘱，累的时候慢一点，但不会突然改路。"
        if owner_intent and owner_intent.intent == "memory_share":
            return f"我听见{owner}说「{message}」。这段旧记忆我收好了，之后遇到相似的光和地方会更容易想起。"
        if decision == "accepted":
            return f"我听见{owner}说「{message}」。这句话我收好了，等路线和天气合适时，我自己靠近看看。"
        if decision == "declined":
            return f"我听见{owner}说「{message}」。今天我先不往那里走，我想按自己的节奏把眼前这段路走完。"
        if decision == "comfort":
            return f"我听见{owner}说「{message}」。这句话我收好了，像把一小块暖光放进手机里。"
        return f"我听见{owner}说「{message}」。我先记住它，不急着决定，下一段路我自己慢慢判断。"

    def _owner_message_event_title(self, decision: str) -> str:
        titles = {
            "accepted": "TA 收到一个旅行建议",
            "declined": "TA 温柔地保留了自己的路线",
            "comfort": "TA 收到了你的想念",
            "remembered": "TA 先记住了你的想法",
        }
        return titles.get(decision, "TA 收到一条讯息")

    def _owner_message_event_detail(self, *, pet: PetRecord, message: str, decision: str) -> str:
        response = {
            "accepted": "我会把这句建议先放进口袋里，等路线和天气合适时自己靠近看看。",
            "declined": "我先把这句话收好，但今天还是想按自己的节奏走完眼前这段路。",
            "comfort": "我把这句话收好了，像把一小块暖光放进手机里。",
            "remembered": "我先记住它，不急着决定，下一段路我会自己慢慢判断。",
        }.get(decision, "我收到了，会按自己的节奏慢慢回应。")
        return f"你发来：「{message}」。{response}"

    def _owner_reference(self, owner_title: str | None) -> str:
        clean = " ".join((owner_title or "").strip().split())
        if not clean:
            return "你"
        if clean in {"宝宝", "宝贝", "儿子", "女儿", "毛孩子", "家人", "朋友"}:
            return "你"
        return clean

    def _remember_owner_message(
        self,
        *,
        pet: PetRecord,
        message: str,
        decision: str,
        scene: str,
        city: str,
        owner_intent: OwnerIntentResult | None = None,
    ) -> None:
        memory_type = "owner_intent"
        importance = 0.78 if decision in {"accepted", "comfort"} else 0.66
        emotional_valence = 0.25 if decision in {"accepted", "comfort"} else 0.05
        if owner_intent and owner_intent.intent in {"comfort", "care_instruction", "memory_share"}:
            memory_type = "relationship"
            emotional_valence = 0.42
        elif owner_intent and owner_intent.intent == "travel_suggestion":
            memory_type = "preference"
        self._remember_safely(
            pet_id=pet.pet_id,
            kind="owner_message",
            title="你的讯息",
            content=(
                f"你发来：{message}。当前城市：{city}。{pet.name} 的回应：{scene}。"
                f"自主回应状态：{decision}"
            ),
            salience=importance,
            source="owner_message",
            metadata={"decision": decision, "city": city, "intent": owner_intent.intent if owner_intent else ""},
            memory_type=memory_type,
            importance=importance,
            emotional_valence=emotional_valence,
            confidence=owner_intent.strength if owner_intent else 0.75,
            structured_payload=owner_intent.model_dump(mode="json") if owner_intent else {},
        )

    def _remember_travel_quest(self, *, pet: PetRecord, quest: TravelQuest, city: str) -> None:
        guide_title = quest.guide.title if quest.guide else f"去 {quest.destination} 的攻略"
        self._remember_safely(
            pet_id=pet.pet_id,
            kind="travel_quest",
            title=guide_title,
            content=(
                f"你提出：{quest.owner_message}。"
                f"{pet.name} 的决定：{quest.autonomy_decision}。"
                f"当前阶段：{quest.current_phase_message}。"
                f"目的地：{quest.destination}。"
            ),
            salience=0.88,
            source="travel_quest",
            metadata={
                "quest_id": quest.id,
                "status": quest.status.value,
                "quest_type": quest.quest_type.value,
                "city": city,
            },
            memory_type="preference",
            importance=0.88,
            emotional_valence=0.32,
            confidence=0.82,
            structured_payload={
                "quest_id": quest.id,
                "destination": quest.destination,
                "status": quest.status.value,
                "soft_influence_only": True,
            },
        )

    def _status_for(self, now: datetime) -> JourneyStatus:
        local_now = now.astimezone()
        minute_of_day = local_now.hour * 60 + local_now.minute
        if 0 <= minute_of_day < 420:
            return JourneyStatus.resting
        if 420 <= minute_of_day < 510:
            return JourneyStatus.staying
        if 510 <= minute_of_day < 570:
            return JourneyStatus.walking
        if 570 <= minute_of_day < 690:
            return JourneyStatus.staying
        if 690 <= minute_of_day < 750:
            return JourneyStatus.walking
        if 750 <= minute_of_day < 1_080:
            return JourneyStatus.staying
        if 1_080 <= minute_of_day < 1_140:
            return JourneyStatus.walking
        return JourneyStatus.resting

    def _wave(self, elapsed: float, period: float, amplitude: int) -> int:
        return int(sin(elapsed / period * pi * 2) * amplitude)

    def _clamp(self, value: int, lower: int, upper: int) -> int:
        return min(max(value, lower), upper)

    def _day_plan_kind(self, planned_time: str | None) -> str:
        if not planned_time or ":" not in planned_time:
            return "afternoon"
        try:
            hour = int(planned_time.split(":", 1)[0])
        except ValueError:
            return "afternoon"
        if hour < 11:
            return "morning"
        if hour < 14:
            return "noon"
        if hour < 18:
            return "afternoon"
        return "evening"

    def _stop_detail(self, stop) -> str:
        details = [stop.detail]
        if stop.photo_candidate:
            details.append("我会把这里的光记下来")
        if stop.postcard_candidate:
            details.append("我会把这里写成一封小信")
        return " · ".join(details)
