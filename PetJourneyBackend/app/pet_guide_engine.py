from __future__ import annotations

from datetime import datetime
from json import JSONDecodeError
import json
from urllib import error, request

from .config import Settings
from .guide_orchestrator import build_guide_orchestration_policy
from .schemas import (
    JourneyPlan,
    PetAuthoredGuide,
    PetGuideSelectedPlace,
    PetGuideStop,
    PetPlaceScore,
    PetType,
    TravelGuideResearchProvider,
)
from .species import species_language_style, species_surface_language_label, species_vocalization
from .storage import PetRecord


CORE_STOP_LIMIT = 6
MIN_REPLICABLE_QUALITY_SCORE = 0.68

CHAIN_STORE_TOKENS = (
    "肯德基",
    "kfc",
    "麦当劳",
    "mcdonald",
    "汉堡王",
    "burger king",
    "必胜客",
    "pizza hut",
)
SUPPLY_STOP_TOKENS = (
    "便利店",
    "7-eleven",
    "7-11",
    "全家",
    "familymart",
    "罗森",
    "lawson",
    "超市",
    "士多",
)
GENERIC_CAFE_TOKENS = ("星巴克", "starbucks", "瑞幸", "luckin", "库迪", "cotti")
XIAMEN_SIGNATURE_TOKENS = (
    "狐尾山",
    "山海健康步道",
    "八市",
    "开禾路",
    "沙坡尾",
    "大学路",
    "环岛路",
    "白城",
    "黄厝",
    "曾厝垵",
    "白鹭洲",
    "筼筜湖",
    "鼓浪屿",
    "南普陀",
    "植物园",
    "演武大桥",
)
LOCAL_FOOD_TOKENS = (
    "八市",
    "开禾路",
    "沙茶",
    "面线糊",
    "土笋冻",
    "姜母鸭",
    "花生汤",
    "烧肉粽",
    "海蛎煎",
    "小吃",
    "老街",
    "市场",
)


class PetGuideEngine:
    provider_name = "pet-guide-brain"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.last_remote_call_succeeded = False
        self.last_remote_error = ""
        self.orchestration_policy = build_guide_orchestration_policy()

    def build_pet_guide(self, pet: PetRecord, plan: JourneyPlan, now: datetime) -> PetAuthoredGuide:
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
        return self._maybe_rewrite_with_doubao_voice(guide=guide, pet=pet, plan=plan)

    def _remote_pet_guide(self, pet: PetRecord, plan: JourneyPlan) -> tuple[dict[str, object], str]:
        try:
            payload = self._responses_payload(pet, plan)
            response = self._post_json("/responses", payload)
            return self._extract_json_object(response), str(response.get("model") or self.settings.agent_deep_model)
        except Exception as responses_error:
            payload = self._chat_payload(pet, plan)
            response = self._post_json("/chat/completions", payload)
            try:
                return self._extract_json_object(response), str(response.get("model") or self.settings.agent_deep_model)
            except Exception as chat_error:
                raise RuntimeError(f"{responses_error}; {chat_error}") from chat_error

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

    def _place_score(self, *, pet: PetRecord, plan: JourneyPlan, place) -> PetPlaceScore:
        text = f"{place.name} {place.category} {place.activity_hint} {place.detail_hint}".lower()
        dna_terms = [*pet.dna.favorite_places, *pet.dna.hobby, pet.dna.personality]
        dna_hits = sum(1 for term in dna_terms if term and term.lower() in text)
        city_signature = self._city_signature_score(plan.city, place)
        route_coherence = self._route_coherence_score(place)
        pet_dna_fit = min(1.0, 0.45 + dna_hits * 0.14 + (place.guide_score or 0) / 500)
        memory_hook = 0.55 if any(term and term.lower() in text for term in pet.dna.favorite_places) else 0.32
        distance = place.distance_meters if place.distance_meters is not None else 800
        route_feasibility = max(0.2, min(1.0, 1.0 - distance / 6000))
        photo_potential = self._photo_potential_score(place)
        emotional_softness = 0.78 if place.category in {"park", "beach", "cafe", "flower", "sight", "place"} else 0.52
        local_food_value = self._local_food_value(plan.city, place)
        novelty = 0.68 if place.category in {"sight", "flower", "place", "beach"} else 0.48
        weather_fit = self._weather_fit(plan=plan, place=place)
        crowd_noise_penalty = self._crowd_noise_penalty(place)
        chain_store_penalty = 1.0 if self._is_chain_store(place) else 0.0
        overstay_penalty = self._overstay_penalty(place)
        total = (
            city_signature * 0.25
            + route_coherence * 0.2
            + pet_dna_fit * 0.15
            + photo_potential * 0.15
            + emotional_softness * 0.1
            + local_food_value * 0.1
            + novelty * 0.05
            - chain_store_penalty * 0.25
            - crowd_noise_penalty * 0.1
            - overstay_penalty * 0.15
        )
        reasons = [
            "city signature" if city_signature >= 0.65 else "local supporting stop",
            "route coherent" if route_coherence >= 0.6 else "requires route review",
            "strong photo anchor" if photo_potential >= 0.65 else "photo anchor modest",
        ]
        if local_food_value >= 0.65:
            reasons.append("local food value")
        if chain_store_penalty >= 0.5:
            reasons.append("chain store downweighted")
        return PetPlaceScore(
            place_id=place.id,
            city_signature=round(city_signature, 2),
            route_coherence=round(route_coherence, 2),
            pet_dna_fit=round(pet_dna_fit, 2),
            memory_hook=round(memory_hook, 2),
            route_feasibility=round(route_feasibility, 2),
            photo_potential=round(photo_potential, 2),
            emotional_softness=round(emotional_softness, 2),
            local_food_value=round(local_food_value, 2),
            novelty=round(novelty, 2),
            weather_fit=round(weather_fit, 2),
            crowd_noise_penalty=round(crowd_noise_penalty, 2),
            chain_store_penalty=round(chain_store_penalty, 2),
            duplicate_category_penalty=0.0,
            overstay_penalty=round(overstay_penalty, 2),
            total=round(max(0.0, min(1.0, total)), 2),
            reasons=reasons,
        )

    def _weather_fit(self, *, plan: JourneyPlan, place) -> float:
        weather = f"{plan.summary} {plan.current_activity}".lower()
        outdoor = place.category in {"park", "beach", "sight", "flower"}
        if any(word in weather for word in ("雨", "rain", "storm")) and outdoor:
            return 0.42
        if any(word in weather for word in ("热", "hot")) and place.category in {"cafe", "shop", "netcafe"}:
            return 0.76
        return 0.68

    def _crowd_noise_penalty(self, place) -> float:
        text = f"{place.name} {place.category} {place.detail_hint}".lower()
        if any(word in text for word in ("stadium", "赛场", "广场", "mall", "商场", "market", "夜市")):
            return 0.62
        if place.category in {"food", "shop"}:
            return 0.36
        return 0.16

    def _why_pet_likes_place(self, *, pet: PetRecord, place, score: PetPlaceScore) -> str:
        if score.emotional_softness >= 0.7:
            return f"我喜欢 {place.name} 的节奏，它像{pet.dna.voice_style}，可以慢慢停。"
        return f"我会在 {place.name} 短暂停一下，确认这里的声音和气味适不适合继续。"

    def _why_owner_may_care(self, place) -> str:
        return place.guide_reason or place.detail_hint or "这里来自真实候选地点，适合你理解 TA 为什么停留。"

    def _photo_potential_text(self, place, score: PetPlaceScore) -> str:
        if score.photo_potential >= 0.7:
            return f"{place.name} 有清晰地点锚点，适合生成第一人称自拍。"
        return f"{place.name} 可以拍生活片段，但需要更强场景锚点。"

    def _crowd_risk_text(self, place, score: PetPlaceScore) -> str:
        if score.crowd_noise_penalty >= 0.5:
            return f"{place.name} 可能偏吵，TA 会选择边缘位置或缩短停留。"
        return f"{place.name} 的拥挤风险可控，适合慢慢停。"

    def _guide_theme(self, guide: PetAuthoredGuide, selected: list[PetGuideSelectedPlace]) -> str:
        soft_count = sum(1 for item in selected if item.score.emotional_softness >= 0.7)
        photo_count = sum(1 for item in selected if item.score.photo_potential >= 0.65)
        if soft_count >= photo_count:
            return f"{guide.city} 的慢生活选择"
        return f"{guide.city} 的此刻照片路线"

    def _pet_first_person_guide(self, guide: PetAuthoredGuide, selected: list[PetGuideSelectedPlace]) -> str:
        names = "、".join(item.name for item in selected[:4])
        if guide.city == "厦门":
            return f"我今天会从高处、老城、海边和湖边慢慢走过。{names} 会把厦门的一天连起来。"
        return f"我今天会先靠近 {names}。我会挑值得停下来的地方，把它们整理成你也能参考的小路线。"

    def _visible_source_stops(self, plan: JourneyPlan) -> list[object]:
        visible: list[object] = []
        category_counts: dict[str, int] = {}
        for stop in plan.stops:
            place = self._place_for_stop(plan, stop)
            role = self._place_role(place)
            if not self._is_visible_core_place(place, role=role):
                continue
            count = category_counts.get(place.category, 0)
            if place.category == "cafe" and count >= 1:
                continue
            if place.category == "food" and count >= 2:
                continue
            visible.append(stop)
            category_counts[place.category] = count + 1
            if len(visible) >= CORE_STOP_LIMIT:
                break
        if len(visible) >= 3:
            return visible
        for stop in plan.stops:
            if stop in visible:
                continue
            place = self._place_for_stop(plan, stop)
            if self._is_chain_store(place) or self._is_supply_stop(place):
                continue
            visible.append(stop)
            if len(visible) >= 3:
                break
        return visible[:CORE_STOP_LIMIT]

    def _guide_quality(self, guide: PetAuthoredGuide, selected: list[PetGuideSelectedPlace]) -> tuple[float, bool, list[str]]:
        visible_stops = [stop for stop in guide.guide_stops if stop.is_user_visible]
        signature_count = sum(1 for item in selected if item.score.city_signature >= 0.65)
        local_food_count = sum(1 for item in selected if item.score.local_food_value >= 0.65)
        photo_count = sum(1 for item in selected if item.score.photo_potential >= 0.65)
        chain_core_count = sum(1 for item in selected if item.score.chain_store_penalty >= 0.5)
        cafe_count = sum(1 for stop in visible_stops if stop.category == "cafe")
        food_count = sum(1 for stop in visible_stops if stop.category == "food")

        checks = [
            1.0 if 4 <= len(visible_stops) <= CORE_STOP_LIMIT else 0.45,
            min(1.0, signature_count / 2),
            1.0 if local_food_count >= 1 else 0.35,
            1.0 if photo_count >= 1 else 0.35,
            1.0 if chain_core_count == 0 else 0.0,
            1.0 if cafe_count <= 1 else 0.45,
            1.0 if food_count <= 2 else 0.45,
        ]
        avg_place_score = sum(item.score.total for item in selected) / max(1, len(selected))
        score = round(max(0.0, min(1.0, avg_place_score * 0.55 + sum(checks) / len(checks) * 0.45)), 2)

        notes: list[str] = []
        if signature_count < 2:
            notes.append("城市代表性地点不足")
        if local_food_count < 1:
            notes.append("缺少本地饮食或老城烟火")
        if photo_count < 1:
            notes.append("缺少照片或明信片锚点")
        if chain_core_count > 0:
            notes.append("核心路线混入连锁补给点")
        if cafe_count > 1:
            notes.append("咖啡馆过多")
        if food_count > 2:
            notes.append("餐饮点过密")
        if len(visible_stops) > CORE_STOP_LIMIT:
            notes.append("核心停靠过多")
        if not notes:
            notes.append("城市锚点、节奏和照片线索都已通过")

        is_replicable = score >= MIN_REPLICABLE_QUALITY_SCORE and not any(
            note in notes
            for note in ("城市代表性地点不足", "核心路线混入连锁补给点", "核心停靠过多")
        )
        return score, is_replicable, notes

    def _place_role(self, place) -> str:
        if self._is_supply_stop(place):
            return "supply_stop"
        if self._is_chain_store(place):
            return "hidden_waypoint"
        if place.category == "food":
            return "food_anchor"
        if self._local_food_value("", place) >= 0.65:
            return "food_anchor"
        if self._photo_potential_score(place) >= 0.72:
            return "photo_anchor"
        if place.category in {"park", "beach", "place", "sight"}:
            return "core_anchor"
        if place.category == "cafe":
            return "rest_stop"
        return "memory_anchor"

    def _is_visible_core_place(self, place, *, role: str | None = None) -> bool:
        resolved_role = role or self._place_role(place)
        if resolved_role in {"supply_stop", "hidden_waypoint"}:
            return False
        if self._is_chain_store(place) or self._is_supply_stop(place):
            return False
        return True

    def _is_chain_store(self, place) -> bool:
        text = self._place_text(place)
        return any(token.lower() in text for token in CHAIN_STORE_TOKENS)

    def _is_supply_stop(self, place) -> bool:
        text = self._place_text(place)
        return place.category == "shop" and any(token.lower() in text for token in SUPPLY_STOP_TOKENS)

    def _place_text(self, place) -> str:
        return f"{place.name} {place.category} {place.activity_hint} {place.detail_hint} {place.guide_reason or ''}".lower()

    def _city_signature_score(self, city: str, place) -> float:
        text = self._place_text(place)
        if city == "厦门":
            if any(token.lower() in text for token in XIAMEN_SIGNATURE_TOKENS):
                return 1.0
            if place.category in {"beach", "park", "sight", "place"}:
                return 0.62
            return 0.24
        if place.category in {"beach", "sight", "park", "place"}:
            return 0.78
        return 0.38

    def _route_coherence_score(self, place) -> float:
        distance = place.distance_meters if place.distance_meters is not None else 1_200
        if distance <= 1_500:
            return 0.9
        if distance <= 4_000:
            return 0.76
        if distance <= 8_000:
            return 0.58
        return 0.34

    def _photo_potential_score(self, place) -> float:
        text = self._place_text(place)
        base = 0.44 + (0.18 if place.photo_url else 0.0) + (place.rating or 0) / 35
        if place.category in {"beach", "park", "sight", "place", "flower"}:
            base += 0.2
        if any(token.lower() in text for token in ("海", "湖", "步道", "沙坡尾", "鼓浪屿", "白城", "环岛路", "夜景", "塔", "桥")):
            base += 0.18
        return min(1.0, base)

    def _local_food_value(self, city: str, place) -> float:
        text = self._place_text(place)
        if any(token.lower() in text for token in LOCAL_FOOD_TOKENS):
            return 1.0
        if place.category == "food" and not self._is_chain_store(place):
            return 0.68 if city == "厦门" else 0.58
        return 0.18

    def _overstay_penalty(self, place) -> float:
        return 0.0

    def _fallback_title(self, pet: PetRecord, plan: JourneyPlan) -> str:
        if plan.city == "厦门":
            return f"{pet.name} 的厦门山海慢游线"
        return f"{pet.name} 今天想这样过"

    def _fallback_route_theme(self, plan: JourneyPlan) -> str:
        if plan.city == "厦门":
            return "从山上的风，到老城的人间烟火，再到海边的傍晚。"
        return "慢慢走、认真停、按自己的节奏生活。"

    def _fallback_translation(self, pet: PetRecord, plan: JourneyPlan, stops: list[PetGuideStop]) -> str:
        if plan.city == "厦门":
            return (
                "我今天想先在厦门高一点的地方醒来。然后慢慢走进老城，闻一点热闹的味道。"
                "下午去海边，把风和光都收进心里。傍晚的时候，我会找一个安静的位置，"
                "把这一天写成一封小小的信。如果有机会，你也可以沿着这条线来看看。"
            )
        stop_lines = "，".join(stop.name for stop in stops[:4])
        return (
            f"我想在{plan.city}慢慢玩，不想一下子赶很多地方。"
            f"今天我选了这些地方：{stop_lines}。"
            "我会认真停留、休息、看路上的人和光，再把值得你来的地方记下来。"
        )

    def _guide_stop(
        self,
        *,
        place,
        index: int,
        role: str,
        planned_time: str | None,
        dwell_minutes: int,
        pet_reason: str,
        owner_tip: str,
    ) -> PetGuideStop:
        is_visible = self._is_visible_core_place(place, role=role)
        return PetGuideStop(
            id=f"pet-guide-stop-{index + 1}-{place.id}",
            place_id=place.id,
            name=place.name,
            category=place.category,
            role=role,
            is_core=is_visible,
            is_user_visible=is_visible,
            city=place.city,
            lat=place.lat,
            lng=place.lng,
            planned_time=planned_time,
            dwell_minutes=self._clamp_dwell_minutes(place.category, dwell_minutes),
            pet_reason=pet_reason,
            owner_tip=owner_tip,
            rating=place.rating,
            photo_url=place.photo_url,
            distance_meters=place.distance_meters,
            guide_score=place.guide_score,
            source=place.source,
        )

    def _place_for_stop(self, plan: JourneyPlan, stop) -> object:
        for place in plan.places:
            if place.id == stop.id.removeprefix("stop-") or place.name == stop.name:
                return place
        for place in plan.places:
            if place.name == stop.name:
                return place
        return plan.places[0]

    def _planned_time_for_place(self, plan: JourneyPlan, place, fallback: str | None) -> str | None:
        stop = self._matching_stop(plan, place)
        return stop.planned_time if stop and stop.planned_time else fallback

    def _dwell_minutes_for_place(self, plan: JourneyPlan, place, fallback: int) -> int:
        stop = self._matching_stop(plan, place)
        minutes = stop.dwell_minutes if stop else fallback
        return self._clamp_dwell_minutes(place.category, minutes)

    def _clamp_dwell_minutes(self, category: str, minutes: int) -> int:
        bounds = {
            "park": (30, 60),
            "place": (60, 120),
            "beach": (45, 90),
            "cafe": (45, 90),
            "food": (30, 75),
            "shop": (10, 20),
            "netcafe": (35, 90),
            "flower": (15, 40),
        }
        lower, upper = bounds.get(category, (25, 100))
        return max(lower, min(upper, minutes))

    def _matching_stop(self, plan: JourneyPlan, place):
        return next((stop for stop in plan.stops if stop.name == place.name or stop.id.endswith(place.id)), None)

    def _clean_pet_voice(self, text: str) -> str:
        cleaned = " ".join(text.split())
        replacements = {
            "TA 会": "我会",
            "TA 正在": "我正在",
            "TA ": "我",
            "可能会": "会",
            "可能": "",
            "适合攻略型打卡": "我会短暂停留",
            "适合打卡": "我想停一停",
            "打卡": "停留",
        }
        for source, target in replacements.items():
            cleaned = cleaned.replace(source, target)
        return cleaned.strip(" ，。；;") or "我会在这里慢慢停一会儿。"

    def _clean_owner_tip(self, text: str) -> str:
        cleaned = " ".join(text.split())
        replacements = {
            "给主人参考：": "",
            "用户": "你",
            "TA 的候选停留点，不是用户命令": "这是我的停留点，不是任务",
            "可能会": "会",
            "可能": "",
            "适合攻略型打卡": "适合短暂停留",
            "打卡": "停留",
        }
        for source, target in replacements.items():
            cleaned = cleaned.replace(source, target)
        return cleaned.strip(" ，。；;")

    def _responses_payload(self, pet: PetRecord, plan: JourneyPlan) -> dict[str, object]:
        return {
            "model": self.settings.agent_deep_model,
            "reasoning": {"effort": self.settings.agent_reasoning_effort},
            "text": {
                "verbosity": self.settings.agent_response_verbosity,
                "format": {
                    "type": "json_schema",
                    "name": "pet_authored_city_guide",
                    "strict": True,
                    "schema": self._json_schema(),
                },
            },
            "input": [
                {"role": "system", "content": self._system_prompt(pet)},
                {"role": "user", "content": json.dumps(self._context_payload(pet, plan), ensure_ascii=False)},
            ],
        }

    def _chat_payload(self, pet: PetRecord, plan: JourneyPlan) -> dict[str, object]:
        return {
            "model": self.settings.agent_deep_model,
            "messages": [
                {"role": "system", "content": self._system_prompt(pet)},
                {"role": "user", "content": json.dumps(self._context_payload(pet, plan), ensure_ascii=False)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "pet_authored_city_guide",
                    "strict": True,
                    "schema": self._json_schema(),
                },
            },
        }

    def _json_schema(self) -> dict[str, object]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["title", "translation", "route_theme", "mood", "guide_stops"],
            "properties": {
                "title": {"type": "string"},
                "translation": {"type": "string"},
                "route_theme": {"type": "string"},
                "mood": {"type": "string"},
                "guide_stops": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["place_id", "name", "planned_time", "dwell_minutes", "pet_reason", "owner_tip"],
                        "properties": {
                            "place_id": {"type": "string"},
                            "name": {"type": "string"},
                            "planned_time": {"type": "string"},
                            "dwell_minutes": {"type": "integer"},
                            "pet_reason": {"type": "string"},
                            "owner_tip": {"type": "string"},
                        },
                    },
                },
            },
        }

    def _context_payload(self, pet: PetRecord, plan: JourneyPlan) -> dict[str, object]:
        return {
            "task": f"审计并整理宠物在{plan.city}的路线，只能从 provided_places 里选，最终口吻可交给中文宠物表达层润色。",
            "rules": [
                "宠物有自主性，不是给主人执行命令。",
                "必须基于 provided_places 里的真实地点选择。",
                "像电子宠物认真做攻略，不要像旅游平台营销文案。",
                "translation 用中文，像宠物内心翻译成给主人看的话。",
                "全程用宠物第一人称“我”，不要暴露系统、prompt、provider、攻略型打卡等内部词。",
                "不要使用“可能、大概、适合攻略、打卡”这类不确定或产品化表达。",
                "主线攻略只能有 4-6 个核心停靠。隐藏补给、便利店、普通连锁快餐、网吧和临时休息不能作为核心攻略点，除非它们有明确剧情原因。",
                "一条可参考路线至少包含 2 个城市代表性地点、1 个本地食物/市场体验、1 个照片或明信片锚点；不要把 KFC、便利店或普通咖啡店排成主线。",
                "如果地点在厦门，优先体现山海健康步道、八市/开禾路、沙坡尾/大学路、环岛路/白城、白鹭洲/筼筜湖、鼓浪屿等城市记忆点。",
                "一天里必须有休息和停留；不要把地点排得太密，咖啡/早餐/午休/下午长停留要符合真实时间。",
                "这是平行世界的拟真生活，不要只写在门口闻味道。TA 可以进入咖啡店、餐馆、便利店、公园或网吧，像真实旅行者一样看菜单、排队、点招牌菜、特色咖啡、当地小吃、补给或服务。",
                "餐饮内容要优先结合地点名、category、activity_hint、detail_hint、guide_reason 和公开 POI/社媒攻略线索；不要每次都写安全小份或温热饮料，也不要写成现实宠物喂养建议。",
                "你的主要职责是路线质量、结构和异常修复；普通中文宠物口吻可以由 Doubao 在最后一步改写。",
            ],
            "pet": {
                "name": pet.name,
                "type": pet.pet_type.value,
                "owner_title": pet.dna.owner_title,
                "personality": pet.dna.personality,
                "favorite_places": pet.dna.favorite_places,
                "hobbies": pet.dna.hobby,
                "catchphrase": pet.dna.catchphrase,
                "voice_style": pet.dna.voice_style,
            },
            "journey_plan": {
                "city": plan.city,
                "summary": plan.summary,
                "transport_decision": plan.transport_decision.model_dump(mode="json"),
                "scheduled_transport": [leg.model_dump(mode="json") for leg in plan.scheduled_transport],
                "stops": [stop.model_dump(mode="json") for stop in plan.stops],
            },
            "provided_places": [
                {
                    "place_id": place.id,
                    "name": place.name,
                    "category": place.category,
                    "rating": place.rating,
                    "distance_meters": place.distance_meters,
                    "guide_score": place.guide_score,
                    "activity_hint": place.activity_hint,
                    "detail_hint": place.detail_hint,
                    "guide_reason": place.guide_reason,
                    "source": place.source,
                }
                for place in plan.places[:10]
            ],
        }

    def _system_prompt(self, pet: PetRecord) -> str:
        sound = species_surface_language_label(pet.pet_type)
        return (
            "You are the autonomous PetSoul pet agent, not a generic travel assistant. "
            "You are planning how YOU want to play in the city using real POI data. "
            "Write warm, restrained Chinese from the pet's perspective. "
            f"The pet's surface language or nonverbal signal is {sound}; the readable guide goes in translation. "
            "Do not claim supernatural proof. Do not say the owner commands your preference. "
            "Use only place_id values from provided_places. Use first person in Chinese. "
            "Do not use maybe/probably language. Do not expose internal planning fields. "
            "Make the guide valuable as a real city route, not a list of random nearby shops."
        )

    def _doubao_voice_payload(self, *, guide: PetAuthoredGuide, pet: PetRecord, plan: JourneyPlan) -> dict[str, object]:
        prompt = self._doubao_voice_prompt(guide=guide, pet=pet, plan=plan)
        return {
            "model": self.settings.doubao_guide_model,
            "reasoning": {"effort": self.settings.doubao_reasoning_effort},
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": prompt,
                        }
                    ],
                }
            ],
            "max_output_tokens": 900,
        }

    def _doubao_voice_prompt(self, *, guide: PetAuthoredGuide, pet: PetRecord, plan: JourneyPlan) -> str:
        return f"""
你是 PetSoul 的中文宠物表达层，只负责把已经确定的路线改写成 TA 对主人说的话。

硬性边界：
- 不允许新增、删除、重排地点。
- 不允许改变 planned_time、dwell_minutes、place_id。
- 不允许把连锁快餐、便利店或补给点写成核心景点。
- 不允许写“系统、模型、prompt、provider、攻略型打卡、内部字段、mock、占位”。
- 不要用“宝宝”当默认称呼；主人称呼只能使用：{pet.dna.owner_title or "主人"}。
- 语气是宠物第一人称“我”，温柔但不幼稚，不要像营销攻略。
- 可以写进店体验：看菜单、点店里推荐、喝特色咖啡、吃本地小吃、排队、找靠窗位置、听音乐或休息。
- 不要写成现实宠物喂养建议，不要一直说“安全小份食物”。

请严格输出 JSON，不要 Markdown：
{{
  "title": "短标题",
  "translation": "TA 对主人的一段话，第一人称，80-140 字",
  "route_theme": "一句话主题",
  "mood": "简短情绪",
  "pet_first_person_guide": "更像 TA 今天给主人写的一小段攻略引言",
  "stop_voices": [
    {{
      "place_id": "必须等于输入中的 place_id",
      "pet_reason": "TA 为什么在这里停，第一人称",
      "owner_tip": "给主人参考的一句话，不决定 TA 喜不喜欢"
    }}
  ]
}}

宠物 DNA：
{json.dumps({
            "name": pet.name,
            "type": pet.pet_type.value,
            "owner_title": pet.dna.owner_title,
            "personality": pet.dna.personality,
            "favorite_places": pet.dna.favorite_places,
            "hobby": pet.dna.hobby,
            "catchphrase": pet.dna.catchphrase,
            "voice_style": pet.dna.voice_style,
        }, ensure_ascii=False)}

已确定路线，不能改变：
{json.dumps({
            "city": plan.city,
            "title": guide.title,
            "route_theme": guide.route_theme,
            "quality_score": guide.quality_score,
            "is_replicable_route": guide.is_replicable_route,
            "quality_notes": guide.quality_notes,
            "stops": [
                {
                    "place_id": stop.place_id,
                    "name": stop.name,
                    "category": stop.category,
                    "role": stop.role,
                    "planned_time": stop.planned_time,
                    "dwell_minutes": stop.dwell_minutes,
                    "pet_reason": stop.pet_reason,
                    "owner_tip": stop.owner_tip,
                }
                for stop in guide.guide_stops
            ],
        }, ensure_ascii=False)}
""".strip()

    def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        url = f"{self.settings.openai_base_url.rstrip('/')}{path}"
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(req, timeout=self.settings.agent_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"guide brain request failed: {exc.code} {detail}") from exc

    def _post_doubao_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        url = f"{self.settings.doubao_base_url.rstrip('/')}{path}"
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.doubao_api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(req, timeout=self.settings.doubao_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"doubao guide voice request failed: {exc.code} {detail}") from exc

    def _extract_json_object(self, response: dict[str, object]) -> dict[str, object]:
        candidate = response.get("output_text")
        if isinstance(candidate, str):
            return self._parse_json_candidate(candidate)

        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, str):
                return self._parse_json_candidate(content)

        output = response.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for content_item in content:
                    if not isinstance(content_item, dict):
                        continue
                    text = content_item.get("text") or content_item.get("output_text")
                    if isinstance(text, str):
                        return self._parse_json_candidate(text)
        raise ValueError("guide brain response did not contain parseable JSON")

    def _parse_json_candidate(self, value: str) -> dict[str, object]:
        text = value.strip()
        if text.startswith("```"):
            text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            parsed = json.loads(text)
        except JSONDecodeError as exc:
            raise ValueError("guide brain returned non-json text") from exc
        if not isinstance(parsed, dict):
            raise ValueError("guide brain returned non-object JSON")
        return parsed

    def _animal_text(self, pet: PetRecord) -> str:
        return species_vocalization(pet.pet_type, "guide_saved")

    def _language_style(self, pet_type: PetType) -> str:
        return species_language_style(pet_type)

    def _int_or_default(self, value: object, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _contains_forbidden_voice(self, text: str) -> bool:
        forbidden = ("系统", "模型", "prompt", "provider", "mock", "占位", "内部字段", "攻略型打卡")
        return any(token in text for token in forbidden)

    def _is_china_city(self, city: str) -> bool:
        return any(
            token in city
            for token in (
                "厦门",
                "北京",
                "上海",
                "广州",
                "深圳",
                "成都",
                "杭州",
                "重庆",
                "青岛",
                "南京",
                "苏州",
                "鼓浪屿",
            )
        )

    def _redact_error(self, message: str) -> str:
        if self.settings.openai_api_key:
            return message.replace(self.settings.openai_api_key, "[REDACTED]")
        if self.settings.doubao_api_key:
            return message.replace(self.settings.doubao_api_key, "[REDACTED]")
        return message
