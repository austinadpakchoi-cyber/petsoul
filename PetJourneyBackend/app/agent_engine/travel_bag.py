"""旅行小包编排：读取与打包主人为宠物准备的随身物品。"""

from __future__ import annotations

import uuid

from ..schemas import TravelBag, TravelBagItem, TravelBagPackRequest
from ..storage import utcnow


class TravelBagMixin:
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
