"""宠物生活模拟 tick mixin：记忆检索、意图选择与行动提议。"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from ..city_timezones import local_wall_time
from ..config import Settings
from ..meal_rules import is_place_plausible_at
from ..memory_store import MemoryStore
from ..pet_energy import NearbyNeedResolver, NearbyNeedSuggestion, PetEnergyModel
from ..providers import JourneyCity
from ..schemas import (
    JourneyPlan,
    LifeTickResult,
    MemoryRecord,
    PetIntent,
    PetNeedState,
    PlaceSignal,
    TravelMode,
    WorldAction,
    WorldActivity,
    WorldObservation,
    WorldSimulationSnapshot,
)
from ..storage import PetRecord


class PetLifeTickMixin:
    def __init__(self, settings: Settings, memory_store: MemoryStore):
        self.settings = settings
        self.memory_store = memory_store
        self.energy_model = PetEnergyModel()
        self.nearby_need_resolver = NearbyNeedResolver()
    def tick(
        self,
        *,
        pet: PetRecord,
        city: JourneyCity,
        plan: JourneyPlan,
        snapshot: WorldSimulationSnapshot,
        now: datetime,
        owner_signal: str | None = None,
    ) -> LifeTickResult:
        activity = snapshot.current_activity
        memories = self._retrieve_memories(pet=pet, activity=activity, city=city)
        nearby_places = self._nearby_places(activity, plan.places)
        need_state = self._need_state(snapshot=snapshot, pet=pet, now=now)
        nearby_need = self.nearby_need_resolver.resolve(
            activity=activity,
            places=nearby_places,
            need_state=need_state,
        )
        observation = WorldObservation(
            pet_id=pet.pet_id,
            city=activity.city or city.name,
            weather=snapshot.weather,
            local_time=local_wall_time(now, activity.city or city.name),
            current_activity=activity,
            nearby_places=nearby_places,
            active_transport=snapshot.active_transport,
            constraints=[
                "行动必须落在当前路线、当前停留点或地图服务返回的附近 POI 上。",
                "长距离移动只能通过交通段表达，不能让宠物瞬移。",
                "主人消息是建议或陪伴信号，不直接控制 TA 的喜好。",
                "照片和明信片只能来自真实停留点或当前交通上下文。",
                "当体力、饥饿、口渴、困意或人流压力更高时，TA 可以临时搜索附近吃喝休息点，不必机械执行攻略。",
            ],
        )
        intent = self._choose_intent(
            pet=pet,
            observation=observation,
            memories=memories,
            need_state=need_state,
            nearby_need=nearby_need,
            owner_signal=owner_signal,
        )
        action = self._propose_action(
            intent=intent,
            activity=activity,
            plan=plan,
            need_state=need_state,
            nearby_need=nearby_need,
        )
        decision = self._resolve_action(action=action, activity=activity, plan=plan, now=now)
        if decision.adjusted:
            action = self._adjusted_action(action=action, activity=activity)
        summary = self._owner_visible_summary(pet=pet, action=action, decision=decision, activity=activity)
        visible_thought = self._visible_thought(
            pet=pet,
            intent=intent,
            action=action,
            activity=activity,
            memories=memories,
            owner_signal=owner_signal,
        )
        animation_hint = self._animation_hint(action=action, activity=activity)
        return LifeTickResult(
            pet_id=pet.pet_id,
            generated_at=now,
            provider=self.provider_name,
            observation=observation,
            retrieved_memories=memories,
            need_state=need_state,
            intent=intent,
            action=action.model_copy(update={"animation_hint": animation_hint}),
            decision=decision,
            owner_visible_summary=summary,
            visible_thought=visible_thought,
            animal_text_hint=self._animal_text_hint(pet=pet, action=action),
            animation_hint=animation_hint,
            should_notify_owner=self._should_notify_owner(action=action, activity=activity, memories=memories),
            next_tick_after_seconds=self._next_tick_after_seconds(action=action, activity=activity),
        )
    def _retrieve_memories(self, *, pet: PetRecord, activity: WorldActivity, city: JourneyCity) -> list[MemoryRecord]:
        query = " ".join(
            part
            for part in [
                pet.name,
                pet.dna.personality,
                city.name,
                activity.place_name,
                activity.title,
                activity.detail,
            ]
            if part
        )
        try:
            memories = self.memory_store.search_memories(pet.pet_id, query=query, limit=8)
            priority = {
                "relationship": 0,
                "place_affect": 1,
                "preference": 2,
                "recent_episodic": 3,
                "episodic": 4,
            }
            memories.sort(
                key=lambda memory: (
                    priority.get(memory.memory_type, 5),
                    -memory.importance,
                    -memory.salience,
                )
            )
            return memories[:5]
        except Exception:
            return []
    def _need_state(self, *, snapshot: WorldSimulationSnapshot, pet: PetRecord, now: datetime) -> PetNeedState:
        return self.energy_model.evaluate(snapshot=snapshot, pet=pet, now=now)
    def _choose_intent(
        self,
        *,
        pet: PetRecord,
        observation: WorldObservation,
        memories: list[MemoryRecord],
        need_state: PetNeedState,
        nearby_need: NearbyNeedSuggestion | None,
        owner_signal: str | None,
    ) -> PetIntent:
        activity = observation.current_activity
        memory_hint = memories[0].title if memories else None
        if activity.kind == "transport":
            return PetIntent(
                id=f"intent-{uuid4().hex[:10]}",
                kind="continue_transport",
                title="继续真实交通段",
                reason="这段路还没有走完，我会按真实时间慢慢靠近下一站。",
                confidence=0.94,
                suggested_place_name=activity.next_place_name or activity.place_name,
                owner_signal=owner_signal,
            )
        if nearby_need:
            suggested_place_name = nearby_need.place.name if nearby_need.place else activity.place_name
            return PetIntent(
                id=f"intent-{uuid4().hex[:10]}",
                kind=nearby_need.action_type,
                title=nearby_need.title,
                reason=nearby_need.reason,
                confidence=nearby_need.confidence,
                suggested_place_name=suggested_place_name,
                owner_signal=owner_signal,
            )
        if activity.can_generate_photo:
            return PetIntent(
                id=f"intent-{uuid4().hex[:10]}",
                kind="capture_memory",
                title="拍一张此刻照片",
                reason=f"{activity.place_name or activity.city} 的光和位置很清楚，我想把这一刻拍下来。",
                confidence=0.88,
                suggested_place_name=activity.place_name,
                owner_signal=owner_signal,
            )
        wants_snack = need_state.hunger >= 78 or self._has_any(activity, ("咖啡", "便利店", "餐", "饭", "茶", "小吃", "cafe"))
        snack_plausible = is_place_plausible_at(observation.local_time, activity.place_name or "")
        if wants_snack and snack_plausible:
            return PetIntent(
                id=f"intent-{uuid4().hex[:10]}",
                kind="snack_or_coffee",
                title="找一个能坐下吃喝的小地方",
                reason="我想找一个能坐下的地方，认真闻闻菜单和店里的味道。",
                confidence=0.81,
                suggested_place_name=activity.place_name,
                owner_signal=owner_signal,
            )
        if self._has_any(activity, ("网吧", "屏幕", "游戏", "电竞", "computer", "game")):
            return PetIntent(
                id=f"intent-{uuid4().hex[:10]}",
                kind="play",
                title="在屏幕光里玩一会儿",
                reason="这里的屏幕光和声音让我想停久一点。",
                confidence=0.83,
                suggested_place_name=activity.place_name,
                owner_signal=owner_signal,
            )
        if memory_hint:
            return PetIntent(
                id=f"intent-{uuid4().hex[:10]}",
                kind="memory_followup",
                title="沿着一条记忆慢慢靠近",
                reason=f"我想起了「{memory_hint}」，会让这点旧记忆轻轻影响今天的脚步。",
                confidence=0.74,
                suggested_place_name=activity.place_name,
                owner_signal=owner_signal,
            )
        return PetIntent(
            id=f"intent-{uuid4().hex[:10]}",
            kind="observe_world",
            title="观察附近的声音和气味",
            reason=f"{pet.name} 先按自己的节奏理解这个地方，再决定下一步。",
            confidence=0.68,
            suggested_place_name=activity.place_name,
            owner_signal=owner_signal,
        )
    def _propose_action(
        self,
        *,
        intent: PetIntent,
        activity: WorldActivity,
        plan: JourneyPlan,
        need_state: PetNeedState,
        nearby_need: NearbyNeedSuggestion | None,
    ) -> WorldAction:
        target_place = nearby_need.place if nearby_need and nearby_need.place else self._place_for_intent(intent, plan)
        target_lat = target_place.lat if target_place else activity.lat
        target_lng = target_place.lng if target_place else activity.lng
        target_name = target_place.name if target_place else activity.place_name
        distance_to_target = self._distance_meters((activity.lat, activity.lng), (target_lat, target_lng))
        mode = TravelMode.walk if nearby_need and target_place and distance_to_target > 120 else (activity.mode or TravelMode.stay)
        duration = self._action_duration_minutes(intent.kind, activity, need_state)
        if nearby_need:
            duration = nearby_need.duration_minutes
        return WorldAction(
            id=f"action-{uuid4().hex[:10]}",
            action_type=intent.kind,
            title=intent.title,
            detail=self._action_detail(intent=intent, activity=activity, plan=plan),
            mode=mode,
            place_name=target_name,
            lat=target_lat,
            lng=target_lng,
            duration_minutes=duration,
            animation_hint="observe",
            photo_opportunity=activity.can_generate_photo or intent.kind == "capture_memory",
            message_opportunity=activity.can_send_postcard
            or intent.kind in {"memory_followup", "observe_world", "rest_nearby", "drink_nearby", "eat_nearby", "quiet_nearby"},
        )
