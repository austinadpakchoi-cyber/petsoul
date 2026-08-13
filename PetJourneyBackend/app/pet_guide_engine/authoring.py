"""PetGuideEngine 攻略作者 mixin：生成宠物攻略主流程。"""

from __future__ import annotations

from datetime import datetime

from ..schemas import (
    JourneyPlan,
    PetAuthoredGuide,
    PetGuideSelectedPlace,
    PetGuideStop,
    TravelGuideResearchProvider,
)
from ..storage import PetRecord


class PetGuideAuthoringMixin:
    _guide_cache_ttl_seconds = 30 * 60
    _guide_cache: dict[tuple[str, str, str], tuple[datetime, PetAuthoredGuide]] = {}

    def _cached_guide(self, cache_key: tuple[str, str, str], now: datetime) -> PetAuthoredGuide | None:
        entry = self._guide_cache.get(cache_key)
        if not entry:
            return None
        cached_at, guide = entry
        if (now - cached_at).total_seconds() > self._guide_cache_ttl_seconds:
            self._guide_cache.pop(cache_key, None)
            return None
        return guide.model_copy(deep=True)

    def build_pet_guide(self, pet: PetRecord, plan: JourneyPlan, now: datetime) -> PetAuthoredGuide:
        cache_key = (pet.pet_id, plan.city, now.astimezone().date().isoformat())
        cached = self._cached_guide(cache_key, now)
        if cached is not None:
            return cached

        self.last_remote_call_succeeded = False
        self.last_remote_error = ""
        guide: PetAuthoredGuide | None = None
        if self.settings.llm_provider == "openai" and self.settings.openai_api_key:
            try:
                data, model = self._remote_pet_guide(pet, plan)
                self.last_remote_call_succeeded = True
                guide = self._guide_from_model_data(pet, plan, now, data, model)
            except Exception as exc:
                self.last_remote_error = self._redact_error(str(exc))
        if guide is None:
            guide = self._fallback_pet_guide(pet, plan, now)
        guide = self._attach_orchestration_metadata(guide=guide, plan=plan)
        guide = self._maybe_rewrite_with_doubao_voice(guide=guide, pet=pet, plan=plan)
        self._guide_cache[cache_key] = (now, guide)
        return guide.model_copy(deep=True)
    def _remote_pet_guide(self, pet: PetRecord, plan: JourneyPlan) -> tuple[dict[str, object], str]:
        payload = self._chat_payload(pet, plan)
        response = self._post_json("/chat/completions", payload)
        return self._extract_json_object(response), str(response.get("model") or self.settings.agent_deep_model)
    def _guide_from_model_data(
        self,
        pet: PetRecord,
        plan: JourneyPlan,
        now: datetime,
        data: dict[str, object],
        model: str,
    ) -> PetAuthoredGuide:
        source_places = {place.id: place for place in plan.places}
        source_by_name = {place.name: place for place in plan.places}
        guide_stops: list[PetGuideStop] = []
        raw_stops = data.get("guide_stops")
        if isinstance(raw_stops, list):
            for index, item in enumerate(raw_stops):
                if not isinstance(item, dict):
                    continue
                place_id = str(item.get("place_id") or "").strip()
                name = str(item.get("name") or "").strip()
                place = source_places.get(place_id) or source_by_name.get(name)
                if not place:
                    continue
                role = self._place_role(place)
                if not self._is_visible_core_place(place, role=role):
                    continue
                guide_stops.append(
                    self._guide_stop(
                        place=place,
                        index=index,
                        role=role,
                        planned_time=self._planned_time_for_place(plan, place, str(item.get("planned_time") or "").strip() or None),
                        dwell_minutes=self._dwell_minutes_for_place(plan, place, self._int_or_default(item.get("dwell_minutes"), 45)),
                        pet_reason=self._clean_pet_voice(str(item.get("pet_reason") or place.activity_hint).strip()),
                        owner_tip=self._clean_owner_tip(str(item.get("owner_tip") or place.detail_hint).strip()),
                    )
                )

        if not guide_stops:
            return self._fallback_pet_guide(pet, plan, now)

        guide = PetAuthoredGuide(
            pet_id=pet.pet_id,
            city=plan.city,
            generated_at=now,
            provider="openai-compatible-pet-guide-brain",
            model=model,
            title=str(data.get("title") or f"{pet.name} 的{plan.city}小攻略").strip(),
            animal_text=self._animal_text(pet),
            translation=str(data.get("translation") or self._fallback_translation(pet, plan, guide_stops)).strip(),
            language_style=self._language_style(pet.pet_type),
            route_theme=str(data.get("route_theme") or "慢慢玩，认真停留").strip(),
            mood=str(data.get("mood") or "好奇").strip(),
            guide_stops=guide_stops,
            scheduled_transport=plan.scheduled_transport,
            source_places_count=len(guide_stops),
        )
        return self._with_place_intelligence(guide=guide, pet=pet, plan=plan)
    def _fallback_pet_guide(self, pet: PetRecord, plan: JourneyPlan, now: datetime) -> PetAuthoredGuide:
        source_stops = self._visible_source_stops(plan)
        stops = [
            self._guide_stop(
                place=self._place_for_stop(plan, stop),
                index=index,
                role=self._place_role(self._place_for_stop(plan, stop)),
                planned_time=stop.planned_time,
                dwell_minutes=stop.dwell_minutes,
                pet_reason=self._clean_pet_voice(stop.detail),
                owner_tip=self._clean_owner_tip(self._place_for_stop(plan, stop).guide_reason or self._place_for_stop(plan, stop).detail_hint),
            )
            for index, stop in enumerate(source_stops)
        ]
        guide = PetAuthoredGuide(
            pet_id=pet.pet_id,
            city=plan.city,
            generated_at=now,
            provider="mock-pet-guide-brain",
            model=self.settings.agent_deep_model,
            title=self._fallback_title(pet, plan),
            animal_text=self._animal_text(pet),
            translation=self._fallback_translation(pet, plan, stops),
            language_style=self._language_style(pet.pet_type),
            route_theme=self._fallback_route_theme(plan),
            mood="安静又好奇",
            guide_stops=stops,
            scheduled_transport=plan.scheduled_transport,
            source_places_count=len(stops),
        )
        return self._with_place_intelligence(guide=guide, pet=pet, plan=plan)
    def _with_place_intelligence(self, *, guide: PetAuthoredGuide, pet: PetRecord, plan: JourneyPlan) -> PetAuthoredGuide:
        selected: list[PetGuideSelectedPlace] = []
        for stop in guide.guide_stops:
            if not stop.is_user_visible:
                continue
            place = next((candidate for candidate in plan.places if candidate.id == stop.place_id or candidate.name == stop.name), None)
            if not place:
                continue
            score = self._place_score(pet=pet, plan=plan, place=place)
            selected.append(
                PetGuideSelectedPlace(
                    place_id=place.id,
                    name=place.name,
                    category=place.category,
                    city=place.city,
                    score=score,
                    why_pet_likes_it=self._why_pet_likes_place(pet=pet, place=place, score=score),
                    why_owner_may_care=self._why_owner_may_care(place),
                    photo_potential=self._photo_potential_text(place, score),
                    crowd_risk=self._crowd_risk_text(place, score),
                )
            )
        if not selected:
            return guide.model_copy(
                update={
                    "guide_theme": "safe local walk",
                    "pet_first_person_guide": "我会先在附近慢慢走，不急着把自己交给不确定的路线。",
                    "quality_score": 0.0,
                    "is_replicable_route": False,
                    "quality_notes": ["没有足够可靠的核心停靠点"],
                }
            )
        quality_score, is_replicable, quality_notes = self._guide_quality(guide, selected)
        return guide.model_copy(
            update={
                "guide_theme": self._guide_theme(guide, selected),
                "selected_places": selected,
                "why_pet_likes_it": [item.why_pet_likes_it for item in selected],
                "why_owner_may_care": [item.why_owner_may_care for item in selected],
                "photo_potential": [item.photo_potential for item in selected],
                "crowd_risk": [item.crowd_risk for item in selected],
                "pet_first_person_guide": self._pet_first_person_guide(guide, selected),
                "quality_score": quality_score,
                "is_replicable_route": is_replicable,
                "quality_notes": quality_notes,
            }
        )
    def _attach_orchestration_metadata(self, *, guide: PetAuthoredGuide, plan: JourneyPlan) -> PetAuthoredGuide:
        provider = (
            TravelGuideResearchProvider.doubao_social
            if self._is_china_city(plan.city)
            else TravelGuideResearchProvider.openai_web_search
        )
        return guide.model_copy(
            update={
                "orchestration_roles": self.orchestration_policy.role_summaries(),
                "quality_gate_rules": self.orchestration_policy.quality_gate_rules(city=plan.city),
                "voice_provider": self.orchestration_policy.voice_provider(self.settings),
                "critic_provider": self.orchestration_policy.critic_provider(
                    self.settings,
                    quality_score=guide.quality_score,
                ),
                "fact_provider_priority": self.orchestration_policy.fact_provider_priority(
                    destination=plan.city,
                    provider=provider,
                ),
            }
        )
    def _maybe_rewrite_with_doubao_voice(
        self,
        *,
        guide: PetAuthoredGuide,
        pet: PetRecord,
        plan: JourneyPlan,
    ) -> PetAuthoredGuide:
        if not self.settings.doubao_api_key:
            return guide
        try:
            payload = self._doubao_voice_payload(guide=guide, pet=pet, plan=plan)
            response = self._post_doubao_json("/responses", payload)
            data = self._extract_json_object(response)
            rewritten = self._guide_with_voice_data(guide=guide, pet=pet, data=data)
            return rewritten.model_copy(
                update={
                    "provider": f"{guide.provider}+doubao-pet-voice",
                    "model": f"{guide.model}|{self.settings.doubao_guide_model}",
                    "voice_provider": "doubao_pet_voice",
                }
            )
        except Exception as exc:
            self.last_remote_error = self._redact_error(str(exc))
            return guide
    def _guide_with_voice_data(
        self,
        *,
        guide: PetAuthoredGuide,
        pet: PetRecord,
        data: dict[str, object],
    ) -> PetAuthoredGuide:
        stop_updates: dict[str, dict[str, str]] = {}
        raw_stop_voices = data.get("stop_voices")
        if isinstance(raw_stop_voices, list):
            for item in raw_stop_voices:
                if not isinstance(item, dict):
                    continue
                place_id = str(item.get("place_id") or "").strip()
                if not place_id:
                    continue
                stop_updates[place_id] = {
                    "pet_reason": self._clean_pet_voice(str(item.get("pet_reason") or "")),
                    "owner_tip": self._clean_owner_tip(str(item.get("owner_tip") or "")),
                }
        updated_stops: list[PetGuideStop] = []
        for stop in guide.guide_stops:
            update = stop_updates.get(stop.place_id) or {}
            updated_stops.append(
                stop.model_copy(
                    update={
                        key: value
                        for key, value in update.items()
                        if value and not self._contains_forbidden_voice(value)
                    }
                )
            )
        title = self._clean_owner_tip(str(data.get("title") or guide.title)) or guide.title
        translation = self._clean_pet_voice(str(data.get("translation") or guide.translation)) or guide.translation
        route_theme = self._clean_owner_tip(str(data.get("route_theme") or guide.route_theme)) or guide.route_theme
        mood = self._clean_owner_tip(str(data.get("mood") or guide.mood)) or guide.mood
        first_person = self._clean_pet_voice(str(data.get("pet_first_person_guide") or guide.pet_first_person_guide or ""))
        return guide.model_copy(
            update={
                "title": title,
                "translation": translation,
                "route_theme": route_theme,
                "mood": mood,
                "guide_stops": updated_stops,
                "pet_first_person_guide": first_person or guide.pet_first_person_guide,
            }
        )
