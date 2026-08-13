"""反馈编排：主人对攻略方向的收藏/略过。"""

from __future__ import annotations

from ..schemas import FeedbackResponse
from ..storage import utcnow


class FeedbackMixin:
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
