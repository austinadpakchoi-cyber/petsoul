from __future__ import annotations

from datetime import datetime

from .providers import JourneyCity, MapProvider
from .schemas import PlaceSignal, StreetRankItem, StreetRankResponse
from .storage import PetRecord


class PetStreetRankEngine:
    provider_name = "petsoul-street-rank-engine"

    def __init__(self, map_provider: MapProvider):
        self.map_provider = map_provider

    def rank(self, *, pet: PetRecord, city: JourneyCity, theme: str, weather: str, now: datetime) -> StreetRankResponse:
        places = self._places_for_theme(city, theme)
        items = [
            self._rank_item(index=index, pet=pet, place=place, theme=theme, weather=weather)
            for index, place in enumerate(places[:10], start=1)
        ]
        return StreetRankResponse(
            pet_id=pet.pet_id,
            city=city.name,
            theme=theme,
            generated_at=now,
            provider=self.provider_name,
            weather=weather,
            items=items,
            source_notes=[
                "高德开放平台暂未提供公开的扫街榜 API。",
                "当前榜单由 PetSoul 基于高德 POI 2.0、综合权重排序、评分、照片、距离、营业信息、天气和宠物 DNA 生成。",
                "用户可以参考榜单复刻路线，但宠物是否喜欢某个地点由 agent 自己决定。",
            ],
        )

    def _places_for_theme(self, city: JourneyCity, theme: str) -> list[PlaceSignal]:
        themed = getattr(self.map_provider, "places_for_theme", None)
        if callable(themed):
            return themed(city, theme, 10)
        return self.map_provider.places_for_city(city)

    def _rank_item(
        self,
        *,
        index: int,
        pet: PetRecord,
        place: PlaceSignal,
        theme: str,
        weather: str,
    ) -> StreetRankItem:
        rank_score = self._rank_score(place, theme, weather, pet)
        return StreetRankItem(
            rank=index,
            place=place,
            rank_score=rank_score,
            reason=self._reason(place, theme, weather),
            pet_action=self._pet_action(pet, place, theme),
            owner_tip=self._owner_tip(place, theme),
            weather_note=self._weather_note(place, weather),
        )

    def _rank_score(self, place: PlaceSignal, theme: str, weather: str, pet: PetRecord) -> float:
        score = place.guide_score or 50.0
        if place.rating is not None:
            score += max(0, min(10, (place.rating - 4.0) * 10))
        if place.photo_url:
            score += 5
        if place.distance_meters is not None and place.distance_meters <= 1200:
            score += 4
        text = " ".join([place.name, place.category, place.detail_hint, place.guide_reason or "", pet.dna.personality])
        normalized = theme.lower()
        if normalized in {"coffee", "cafe", "咖啡", "甜品"} and place.category == "cafe":
            score += 8
        if normalized in {"night", "late", "深夜", "夜间"} and place.category in {"netcafe", "shop", "food"}:
            score += 7
        if normalized in {"photo", "selfie", "拍照", "照片"} and place.photo_url:
            score += 7
        if normalized in {"rain", "rainy", "雨天", "躲雨"} and place.category in {"cafe", "shop", "netcafe"}:
            score += 8
        if any(token in text for token in pet.dna.favorite_places):
            score += 4
        if any(token in weather for token in ("雨", "阴", "雷")) and place.category in {"cafe", "shop", "netcafe"}:
            score += 5
        return round(score, 1)

    def _reason(self, place: PlaceSignal, theme: str, weather: str) -> str:
        reason = place.guide_reason or place.detail_hint
        if any(token in weather for token in ("雨", "阴", "雷")) and place.category in {"cafe", "shop", "netcafe"}:
            return f"{reason}；现在天气是{weather}，更适合室内或半室内停留。"
        if theme in {"photo", "selfie", "拍照", "照片"} and place.photo_url:
            return f"{reason}；有地点照片参考，适合生成 TA 发回来的场景照。"
        return reason

    def _pet_action(self, pet: PetRecord, place: PlaceSignal, theme: str) -> str:
        if place.category == "cafe":
            return f"{pet.name} 会进店找靠窗的位置坐下，点一杯店里的特色咖啡或当季饮品，再慢慢看街上的人经过。"
        if place.category == "netcafe":
            return f"{pet.name} 会被屏幕光吸引，戴上耳机安静坐一会儿。"
        if place.category == "food":
            return f"{pet.name} 会在店里看菜单，点一份招牌菜或当地小吃，吃完再继续走。"
        if place.category == "shop":
            return f"{pet.name} 会走进去挑一个小补给，把这里记成今天的生活点。"
        if place.category == "park":
            return f"{pet.name} 会在这里放慢脚步，晒太阳、看风，也恢复一点精力。"
        return f"{pet.name} 会先靠近看看，再自己决定要不要停留。"

    def _owner_tip(self, place: PlaceSignal, theme: str) -> str:
        if place.rating is not None:
            return f"给主人参考：高德评分 {place.rating:.1f}，适合作为以后复刻路线的候选点。"
        if place.distance_meters is not None:
            return f"给主人参考：距离当前位置约 {place.distance_meters} 米，可以放进短路线。"
        return "给主人参考：这是 TA 的候选停留点，不是用户命令。"

    def _weather_note(self, place: PlaceSignal, weather: str) -> str:
        if any(token in weather for token in ("雨", "雷")):
            return "天气不稳定，TA 会更倾向找能躲雨、有光、声音不太冲的地方。"
        if "晴" in weather:
            return "天气适合户外短暂停留，但 TA 仍然会自己选择节奏。"
        return f"当前天气：{weather}。"
