from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import cos, pi, sqrt

from .city_timezones import local_wall_time
from .schemas import JourneyStatus, PetNeedState, PlaceSignal, TravelMode, WorldActivity, WorldSimulationSnapshot
from .storage import PetRecord


@dataclass(frozen=True, slots=True)
class NearbyNeedSuggestion:
    need_kind: str
    action_type: str
    title: str
    reason: str
    place: PlaceSignal | None
    confidence: float
    duration_minutes: int
    animation_hint: str


class PetEnergyModel:
    provider_name = "pet-energy-model"

    def evaluate(self, *, snapshot: WorldSimulationSnapshot, pet: PetRecord, now: datetime) -> PetNeedState:
        activity = snapshot.current_activity
        wall = local_wall_time(now, snapshot.city)
        minute = wall.hour * 60 + wall.minute
        heat_stress = self._heat_stress(weather=snapshot.weather, minute=minute, activity=activity)
        sensory_load = self._sensory_load(activity)
        movement_cost = self._movement_cost(activity)
        rest_recovery = self._rest_recovery(activity)

        energy = self._clamp(snapshot.energy - movement_cost - heat_stress // 5 - sensory_load // 8 + rest_recovery, 5, 99)
        hunger = self._clamp(self._meal_hunger(minute) + movement_cost // 2 + self._soft_wave(wall.minute, 9), 5, 99)
        thirst = self._clamp(38 + heat_stress + movement_cost + self._soft_wave(wall.minute + 7, 12), 5, 99)
        sleepiness = self._clamp(self._sleepiness(minute) + max(0, 42 - energy) + sensory_load // 8, 5, 99)
        comfort = self._clamp(
            self._base_comfort(pet) + rest_recovery // 2 - sensory_load // 3 - heat_stress // 4,
            5,
            99,
        )
        playfulness = self._clamp(54 + snapshot.curiosity // 5 - sleepiness // 5 - heat_stress // 8, 5, 99)
        return PetNeedState(
            energy=energy,
            hunger=hunger,
            thirst=thirst,
            sleepiness=sleepiness,
            sensory_load=sensory_load,
            heat_stress=heat_stress,
            social=self._clamp((72 if activity.can_send_postcard else 54) + self._soft_wave(wall.minute + 3, 7), 5, 99),
            curiosity=snapshot.curiosity,
            comfort=comfort,
            playfulness=playfulness,
            primary_need=self.primary_need(
                energy=energy,
                hunger=hunger,
                thirst=thirst,
                sleepiness=sleepiness,
                sensory_load=sensory_load,
                heat_stress=heat_stress,
            ),
        )

    def primary_need(
        self,
        *,
        energy: int,
        hunger: int,
        thirst: int,
        sleepiness: int,
        sensory_load: int,
        heat_stress: int,
    ) -> str:
        if sleepiness >= 78 or energy <= 28:
            return "rest"
        if thirst >= 78 or heat_stress >= 72:
            return "drink"
        if hunger >= 78:
            return "eat"
        if sensory_load >= 76:
            return "quiet"
        return "observe"

    def _movement_cost(self, activity: WorldActivity) -> int:
        if activity.kind == "movement":
            if activity.mode == TravelMode.walk:
                return 18
            if activity.mode in {TravelMode.drive, TravelMode.transit}:
                return 8
            return 5
        if activity.kind == "transport":
            return 7
        if activity.status == JourneyStatus.walking:
            return 14
        return 0

    def _rest_recovery(self, activity: WorldActivity) -> int:
        if activity.kind == "rest" or activity.status == JourneyStatus.resting:
            return 18
        text = self._activity_text(activity)
        if any(word in text for word in ("咖啡", "茶", "公园", "花店", "安静", "窗", "休息")):
            return 8
        return 0

    def _meal_hunger(self, minute: int) -> int:
        if 420 <= minute <= 560:
            return 68
        if 690 <= minute <= 820:
            return 90
        if 1_080 <= minute <= 1_230:
            return 88
        if 1_260 <= minute or minute <= 60:
            return 42
        return 48

    def _sleepiness(self, minute: int) -> int:
        if minute >= 1_380 or minute <= 390:
            return 92
        if 1_320 <= minute < 1_380:
            return 76
        if 780 <= minute <= 840:
            return 54
        return 26

    def _heat_stress(self, *, weather: str, minute: int, activity: WorldActivity) -> int:
        text = f"{weather} {self._activity_text(activity)}"
        score = 14
        if any(word in text for word in ("热", "晒", "太阳", "高温", "闷", "humid", "hot")):
            score += 35
        if any(word in text for word in ("雨", "雷", "雪", "冷", "风很大", "storm")):
            score += 16
        if 660 <= minute <= 930:
            score += 14
        if activity.kind == "movement" and activity.mode == TravelMode.walk:
            score += 12
        return self._clamp(score, 0, 99)

    def _sensory_load(self, activity: WorldActivity) -> int:
        text = self._activity_text(activity)
        score = 34
        if any(word in text for word in ("赛场", "人群", "排队", "热闹", "主路", "拥挤", "机场", "车站")):
            score += 34
        if any(word in text for word in ("网吧", "屏幕", "游戏", "电竞")):
            score += 14
        if any(word in text for word in ("公园", "花店", "安静", "海边", "咖啡", "靠窗", "小巷")):
            score -= 18
        return self._clamp(score, 0, 99)

    def _base_comfort(self, pet: PetRecord) -> int:
        text = f"{pet.dna.personality} {' '.join(pet.dna.favorite_places)}"
        if any(word in text for word in ("温柔", "黏", "安静", "慢")):
            return 78
        return 64

    def _activity_text(self, activity: WorldActivity) -> str:
        return " ".join([activity.title, activity.detail, activity.place_name or "", activity.city]).lower()

    def _soft_wave(self, value: int, amplitude: int) -> int:
        phase = (value % 60) / 60
        return int(round(amplitude * (0.5 - abs(phase - 0.5)) * 2))

    def _clamp(self, value: int, lower: int, upper: int) -> int:
        return max(lower, min(upper, value))


class NearbyNeedResolver:
    provider_name = "nearby-need-resolver"

    def resolve(
        self,
        *,
        activity: WorldActivity,
        places: list[PlaceSignal],
        need_state: PetNeedState,
    ) -> NearbyNeedSuggestion | None:
        if activity.kind == "transport":
            return None

        need_kind = need_state.primary_need
        if need_kind == "observe":
            return None

        nearby = self._nearby(activity, places)
        if need_kind == "rest":
            place = self._pick(nearby, ["cafe", "park", "flower", "netcafe", "shop"])
            return NearbyNeedSuggestion(
                need_kind="rest",
                action_type="rest_nearby",
                title="临时找个地方歇一下",
                reason="我有点累了，会先找附近能安静停下来的地方，让呼吸慢下来。",
                place=place,
                confidence=0.9,
                duration_minutes=45,
                animation_hint="sleep",
            )
        if need_kind == "drink":
            place = self._pick(nearby, ["cafe", "shop", "food"])
            return NearbyNeedSuggestion(
                need_kind="drink",
                action_type="drink_nearby",
                title="在附近找点喝的",
                reason="天气和脚步让我有点口渴，我会先在附近找点喝的，再继续往前。",
                place=place,
                confidence=0.86,
                duration_minutes=24,
                animation_hint="coffee_drink",
            )
        if need_kind == "eat":
            place = self._pick(nearby, ["food", "cafe", "shop"])
            return NearbyNeedSuggestion(
                need_kind="eat",
                action_type="eat_nearby",
                title="临时找附近吃一点",
                reason="我饿了，会看看附近真实店铺和本地味道，先认真吃一点。",
                place=place,
                confidence=0.86,
                duration_minutes=36,
                animation_hint="snack",
            )
        if need_kind == "quiet":
            place = self._pick(nearby, ["park", "flower", "cafe", "shop"])
            return NearbyNeedSuggestion(
                need_kind="quiet",
                action_type="quiet_nearby",
                title="躲开太吵的地方",
                reason="附近声音和人流有点满，我会找一处更安静的位置缓一缓。",
                place=place,
                confidence=0.82,
                duration_minutes=32,
                animation_hint="observe",
            )
        return None

    def _nearby(self, activity: WorldActivity, places: list[PlaceSignal]) -> list[PlaceSignal]:
        ranked = sorted(
            places,
            key=lambda place: self._distance_meters((activity.lat, activity.lng), (place.lat, place.lng)),
        )
        close = [place for place in ranked if self._distance_meters((activity.lat, activity.lng), (place.lat, place.lng)) <= 2_000]
        return close[:10] or ranked[:6]

    def _pick(self, places: list[PlaceSignal], categories: list[str]) -> PlaceSignal | None:
        candidates = [place for place in places if place.category in categories]
        if not candidates:
            candidates = places
        if not candidates:
            return None
        return sorted(
            candidates,
            key=lambda place: (
                categories.index(place.category) if place.category in categories else len(categories),
                -(place.guide_score or 0),
                place.distance_meters if place.distance_meters is not None else 999_999,
                place.name,
            ),
        )[0]

    def _distance_meters(self, start: tuple[float, float], end: tuple[float, float]) -> float:
        avg_lat = ((start[0] + end[0]) / 2) * pi / 180
        lat_meters = (end[0] - start[0]) * 111_320
        lng_meters = (end[1] - start[1]) * 111_320 * cos(avg_lat)
        return sqrt(lat_meters * lat_meters + lng_meters * lng_meters)
