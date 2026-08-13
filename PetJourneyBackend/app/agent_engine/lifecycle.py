"""生命周期编排：初始旅程建立、状态/推进、日程、位置、路线与宠物攻略。"""

from __future__ import annotations

from ..providers import JourneyCity
from ..route_planner import adapt_journey_plan_to_route_plan
from ..schemas import (
    AgentState,
    AgentStatus,
    CityPosition,
    DayPlan,
    DayPlanItem,
    JourneyEvent,
    JourneyPlan,
    JourneyRoutePlan,
    JourneyThought,
    PetAuthoredGuide,
    Postcard,
)
from ..storage import PetRecord, utcnow
from .exceptions import PetNotFoundError


class LifecycleMixin:
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
        steps: list = []
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
        steps: list = []
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
        # 位置必须与世界快照同源：飞行/移动中返回当前活动坐标，避免与其他模块各说各话
        try:
            snapshot = self.world_snapshot(pet_id)
            activity = snapshot.current_activity
            return CityPosition(
                city=activity.city or snapshot.city,
                lat=activity.lat,
                lng=activity.lng,
            )
        except PetNotFoundError:
            raise
        except Exception:
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
