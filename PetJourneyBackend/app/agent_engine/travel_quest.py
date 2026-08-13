"""旅行攻略编排：愿望→攻略→出发准备→赛后下一步的完整生命周期。"""

from __future__ import annotations

from ..schemas import (
    TravelQuest,
    TravelQuestDecisionRequest,
    TravelWishRequest,
)
from ..storage import utcnow
from .exceptions import TravelQuestNotFoundError


class TravelQuestMixin:
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
