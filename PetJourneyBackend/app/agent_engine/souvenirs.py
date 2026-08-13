"""纪念品编排：赛后带回来的小东西的生成、配图与收集。"""

from __future__ import annotations

from ..schemas import CollectSouvenirsResponse, SouvenirItem
from ..storage import PetRecord, utcnow


class SouvenirsMixin:
    def list_souvenirs(self, pet_id: str, limit: int = 50) -> list[SouvenirItem]:
        self._pet(pet_id)
        return self.storage.list_souvenirs(pet_id, limit=limit)

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
