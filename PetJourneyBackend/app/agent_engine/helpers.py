"""旅程引擎核心 helper：城市/宠物/状态解析、计划缓存、念头落库、生命快照。

这些无下划线业务前缀的 `_` 方法被各场景编排 mixin 密集复用，集中于此
避免在多个场景文件里重复，也避免场景 mixin 之间互相引用。
"""

from __future__ import annotations

from datetime import datetime, timezone
from math import pi, sin

from ..agent_brain import AgentTurnContext
from ..providers import JourneyCity
from ..schemas import (
    JourneyPlan,
    JourneyStatus,
    TravelBag,
    TravelBagItem,
    WorldSimulationSnapshot,
)
from ..storage import PetRecord
from .exceptions import PetNotFoundError


class JourneyEngineHelpersMixin:
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
        if speech.content_intent in {"moment", "postcard"}:
            self._pending_content_intents[pet.pet_id] = {
                "intent": speech.content_intent,
                "scene": scene,
                "translation": speech.translation,
                "created_at": (timestamp or datetime.now(tz=timezone.utc)).isoformat(),
            }

    def consume_content_intent(self, pet_id: str) -> dict[str, object] | None:
        """大脑的分享提议只保留两小时;发布与否仍由 communicator 的频控规则终审。"""
        payload = self._pending_content_intents.pop(pet_id, None)
        if not payload:
            return None
        try:
            created = datetime.fromisoformat(str(payload.get("created_at")))
            age = (datetime.now(tz=timezone.utc) - created).total_seconds()
        except (TypeError, ValueError):
            return payload
        return payload if age <= 7_200 else None

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
