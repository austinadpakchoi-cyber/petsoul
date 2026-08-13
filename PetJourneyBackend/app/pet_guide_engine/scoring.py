"""PetGuideEngine 评分 mixin：地点打分、路线质量与可见性判定。"""

from __future__ import annotations

from ..schemas import (
    JourneyPlan,
    PetAuthoredGuide,
    PetGuideSelectedPlace,
    PetPlaceScore,
)
from ..storage import PetRecord

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


class PetGuideScoringMixin:
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
