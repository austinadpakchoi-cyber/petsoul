from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from urllib import error, parse, request
from typing import Protocol

from .config import Settings
from .google_maps_services import GoogleMapsServiceClient
from .schemas import CityPosition, PlaceSignal


@dataclass(frozen=True, slots=True)
class JourneyCity:
    name: str
    lat: float
    lng: float
    weather: str
    phrases: tuple[str, ...]
    thoughts: tuple[str, ...]

    @property
    def position(self) -> CityPosition:
        return CityPosition(city=self.name, lat=self.lat, lng=self.lng)


CITIES: tuple[JourneyCity, ...] = (
    JourneyCity(
        name="厦门",
        lat=24.4798,
        lng=118.0894,
        weather="海风很轻",
        phrases=("在海边慢慢散步", "停在一条有花香的小巷", "听见远处的浪声，心情很安静"),
        thoughts=(
            "这里的风很轻，我走得很慢，像以前等你跟上来那样。",
            "刚刚在一小片草地边坐了一会儿，风从耳朵旁边慢慢过去。",
            "我今天没有走太远，只是在一个能看见海的地方晒了会儿太阳。",
        ),
    ),
    JourneyCity(
        name="京都",
        lat=35.0116,
        lng=135.7681,
        weather="薄云和木香",
        phrases=("坐在安静的屋檐下", "沿着石板路观察行人", "在午后的光里休息"),
        thoughts=(
            "这里很安静，连脚步声都像被轻轻收好了。",
            "我找到一条窄窄的路，路边有一盏小灯，我觉得你会喜欢。",
            "今天我学会了慢一点，好像慢一点就能把想念放得更稳。",
        ),
    ),
    JourneyCity(
        name="雷克雅未克",
        lat=64.1466,
        lng=-21.9426,
        weather="冷空气里有星光",
        phrases=("在远处看见很亮的天", "把脚印留在安静的雪边", "休息在一间暖暖的小屋旁"),
        thoughts=(
            "这里的夜很长，可是天上有光，我没有害怕。",
            "我把鼻子贴近雪地，世界安静得像一封还没写完的信。",
            "如果你也在这里，我会把最暖的位置让给你。",
        ),
    ),
)


SAFE_PLACE_CATALOG: dict[str, list[tuple[str, str, str, float, float, str, str]]] = {
    "厦门": [
        ("huweishan-walkway", "狐尾山 / 山海健康步道", "park", 24.4874, 118.0847, "在狐尾山的风里慢慢醒来，看见厦门从高处亮起来", "高处、绿意和城市边界都很清楚，适合作为一日路线的开场。"),
        ("bashi-kaihe-food", "八市 / 开禾路老街", "food", 24.4579, 118.0739, "走进八市和开禾路的人间烟火里，看摊位、听声音、选一口本地味道", "老城市场和本地小吃让路线有厦门记忆点，适合作为早午间核心停靠。"),
        ("shapowei-daxue-road", "沙坡尾 / 大学路", "place", 24.4386, 118.0930, "在沙坡尾和大学路慢慢逛，听海风钻进巷子里", "老港、巷子、小店和海风都有画面感，适合照片、明信片和慢逛。"),
        ("yanwu-bridge-view", "演武大桥观景平台", "park", 24.4328, 118.0968, "在演武大桥旁边看海面和路上的光", "这里能把厦门的桥、海和城市轮廓放进一张照片里。"),
        ("baicheng-beach-ring-road", "环岛路 / 白城沙滩", "park", 24.4319, 118.1036, "下午沿环岛路靠近白城沙滩，把海风记进手机", "海边和环岛路是厦门很强的城市标签，适合作为下午的核心照片点。"),
        ("bailuzhou-yundang-lake", "白鹭洲 / 筼筜湖", "park", 24.4772, 118.0961, "傍晚在白鹭洲和筼筜湖边慢下来，写一封小小的信", "傍晚湖面、城市灯和安静步道适合作为当天收束与明信片候选点。"),
        ("zhongshan-road-cafe-window", "中山路骑楼咖啡窗口", "cafe", 24.4570, 118.0806, "在骑楼边的小咖啡窗口喝一杯店里的特色饮品", "这是可选休息点，不抢主线，只在 TA 需要补给或躲雨时出现。"),
        ("local-supply-stop", "老城补给小店", "shop", 24.4592, 118.0786, "在老城小店里挑一件路上用得上的小东西", "隐藏补给点，不作为核心攻略站。"),
    ],
    "京都": [
        ("nishiki-food", "锦市场小食铺", "food", 35.0051, 135.7648, "在锦市场小食铺里点了一份摊位招牌小吃", "窄街、木色招牌和本地食物都适合写进攻略。"),
        ("sanjo-coffee", "三条咖啡窗口", "cafe", 35.0095, 135.7667, "在咖啡窗口旁边的小桌喝了一杯店里的推荐饮品", "这里适合短暂停靠，不会让路线变成景点打卡表。"),
        ("shijo-convenience", "四条便利店", "shop", 35.0038, 135.7596, "在便利店里绕了一圈，挑了小补给", "灯光和街声稳定，适合表达 TA 在城市里认真生活。"),
        ("kawaramachi-netcafe", "河原町安静网咖", "netcafe", 35.0064, 135.7690, "在网咖角落听见很轻的键盘声", "室内停留点，适合长时间待着，不会一直机械移动。"),
        ("gion-flower", "祇园花店橱窗", "flower", 35.0034, 135.7752, "在花店橱窗前看了很久的叶子", "街面安静，适合作为明信片候选点。"),
    ],
    "雷克雅未克": [
        ("laugavegur-food", "Laugavegur 小食铺", "food", 64.1452, -21.9298, "在小食铺里点了一份当地热汤和面包", "寒冷城市里的热气和灯光，适合做温柔停靠点。"),
        ("downtown-coffee", "市中心咖啡窗口", "cafe", 64.1462, -21.9317, "在咖啡窗口旁边喝了一杯店里的招牌咖啡", "短暂停靠点，适合写小卡片。"),
        ("harpa-convenience", "Harpa 附近便利店", "shop", 64.1490, -21.9321, "在便利店里选了一样小补给", "靠近城市建筑和步行街，不会落到海面。"),
        ("warm-game-room", "暖灯游戏小店", "netcafe", 64.1441, -21.9266, "在屏幕光旁边安静待了一会儿", "室内长停留点，符合电子宠物走走停停的节奏。"),
        ("rainbow-flower", "彩虹街花店橱窗", "flower", 64.1428, -21.9279, "在花店橱窗前看了很久的叶子", "色彩和街面都适合生成地点感强的照片。"),
    ],
}


class MapProvider(Protocol):
    provider_name: str

    def city_for_elapsed(self, elapsed_seconds: float) -> JourneyCity:
        ...

    def places_for_city(self, city: JourneyCity) -> list[PlaceSignal]:
        ...


class MockMapProvider:
    provider_name = "mock-map-provider"

    def city_for_elapsed(self, elapsed_seconds: float) -> JourneyCity:
        index = max(0, int(elapsed_seconds // 172_800)) % len(CITIES)
        return CITIES[index]

    def places_for_city(self, city: JourneyCity) -> list[PlaceSignal]:
        places = SAFE_PLACE_CATALOG.get(city.name) or self._compact_fallback_places(city)
        return [
            PlaceSignal(
                id=f"{city.name}-{place_id}",
                name=name,
                category=category,
                city=city.name,
                lat=lat,
                lng=lng,
                activity_hint=activity,
                detail_hint=detail,
                source=self.provider_name,
            )
            for place_id, name, category, lat, lng, activity, detail in places
        ]

    def _compact_fallback_places(self, city: JourneyCity) -> list[tuple[str, str, str, float, float, str, str]]:
        # Tiny offsets keep unknown-city demos close to the city anchor. Known cities use
        # SAFE_PLACE_CATALOG so coastal demos do not drift into water.
        offsets = [
            ("street-food", "街角小食铺", "food", 0.0012, -0.0010, "在街角小食铺里点了一份招牌小吃", "短暂停留点，适合本地生活感的小卡片。"),
            ("coffee-window", "咖啡窗口", "cafe", -0.0008, 0.0014, "在咖啡窗口旁的小桌喝了一杯店里的推荐饮品", "适合安静等待，不像热门景点那样拥挤。"),
            ("convenience", "便利店", "shop", 0.0015, 0.0010, "在便利店里挑了一个小补给", "灯光稳定、声音熟悉，适合走走停停。"),
            ("quiet-netcafe", "安静网吧", "netcafe", -0.0013, -0.0015, "在网吧角落待了一会儿", "这不是景点，而是 TA 自己选择的停留点。"),
            ("flower-window", "花店橱窗", "flower", 0.0005, -0.0017, "在花店前停住，看了很久的叶子", "街面安静、气味柔和，适合作为中途停留。"),
        ]
        return [
            (place_id, name, category, city.lat + lat_offset, city.lng + lng_offset, activity, detail)
            for place_id, name, category, lat_offset, lng_offset, activity, detail in offsets
        ]


class RemoteMapProvider:
    provider_name = "remote-map-provider-placeholder"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.fallback = MockMapProvider()

    def city_for_elapsed(self, elapsed_seconds: float) -> JourneyCity:
        return self.fallback.city_for_elapsed(elapsed_seconds)

    def places_for_city(self, city: JourneyCity) -> list[PlaceSignal]:
        # Future hook:
        # - China: use AMAP nearby/search/route APIs.
        # - Overseas: use Google Maps Places/Directions APIs.
        # Keep returning mock data until the corresponding keys and contracts are supplied.
        return self.fallback.places_for_city(city)


class AMapWebMapProvider:
    provider_name = "amap-web-map-provider"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.fallback = MockMapProvider()

    def city_for_elapsed(self, elapsed_seconds: float) -> JourneyCity:
        return self.fallback.city_for_elapsed(elapsed_seconds)

    def places_for_city(self, city: JourneyCity) -> list[PlaceSignal]:
        if not self.settings.amap_api_key:
            return self.fallback.places_for_city(city)

        try:
            places = self._fetch_places_around(city, limit=12)
        except Exception:
            return self.fallback.places_for_city(city)

        if len(places) < 8:
            existing_names = {place.name for place in places}
            fallback_places = [
                place.model_copy(update={"source": self.provider_name})
                for place in self.fallback.places_for_city(city)
                if place.name not in existing_names
            ]
            places = [*places, *fallback_places]
        return places[:12]

    def places_for_theme(self, city: JourneyCity, theme: str, limit: int = 10) -> list[PlaceSignal]:
        if not self.settings.amap_api_key:
            return self.fallback.places_for_city(city)
        try:
            places = self._fetch_places_around(
                city,
                types=self._types_for_theme(theme),
                radius=6000,
                page_size=30,
                limit=limit,
            )
        except Exception:
            return self.fallback.places_for_city(city)[:limit]
        return places[:limit] or self.fallback.places_for_city(city)[:limit]

    def _fetch_places_around(
        self,
        city: JourneyCity,
        *,
        types: list[str] | None = None,
        radius: int = 3500,
        page_size: int = 25,
        limit: int = 5,
    ) -> list[PlaceSignal]:
        types = types or [
            "050000",  # food
            "050500",  # cafe/tea
            "060000",  # shopping
            "080000",  # sports/leisure
            "080300",  # entertainment
            "110000",  # scenic
            "141200",  # internet cafe
            "150900",  # convenience store
        ]
        payload = self._get_json(
            "/v5/place/around",
            {
                "location": f"{city.lng},{city.lat}",
                "radius": str(radius),
                "region": city.name,
                "page_size": str(page_size),
                "page_num": "1",
                "show_fields": "business,photos",
                "sortrule": "weight",
                "types": "|".join(types),
            },
        )
        pois = payload.get("pois")
        if not isinstance(pois, list):
            return []

        places: list[PlaceSignal] = []
        seen_categories: set[str] = set()
        seen_names: set[str] = set()
        for poi in pois:
            if not isinstance(poi, dict):
                continue
            place = self._poi_to_place(city, poi)
            if place is None or place.name in seen_names:
                continue
            if not self._is_relevant_poi(place):
                continue
            places.append(place)
            seen_names.add(place.name)
            seen_categories.add(place.category)
            if len(places) >= max(limit * 2, 10) and len(seen_categories) >= 3:
                break
        return sorted(places, key=lambda item: item.guide_score or 0, reverse=True)[:limit]

    def _types_for_theme(self, theme: str) -> list[str]:
        normalized = theme.strip().lower()
        if normalized in {"coffee", "cafe", "咖啡", "甜品"}:
            return ["050500", "050700", "050800", "050900"]
        if normalized in {"night", "late", "深夜", "夜间"}:
            return ["050000", "050500", "060000", "080300", "141200", "150900"]
        if normalized in {"photo", "selfie", "拍照", "照片"}:
            return ["050500", "080000", "110000", "060000", "141200"]
        if normalized in {"rain", "rainy", "雨天", "躲雨"}:
            return ["050500", "060000", "080300", "141200", "150900"]
        if normalized in {"local", "street", "扫街", "小吃", "烟火"}:
            return ["050000", "050500", "060000", "150900"]
        return ["050000", "050500", "060000", "080000", "080300", "110000", "141200", "150900"]

    def _poi_to_place(self, city: JourneyCity, poi: dict[str, object]) -> PlaceSignal | None:
        name = poi.get("name")
        location = poi.get("location")
        if not isinstance(name, str) or not isinstance(location, str):
            return None
        lng, lat = self._parse_location(location)
        if lng is None or lat is None:
            return None

        type_text = str(poi.get("type") or "")
        category = self._category_for(name, type_text)
        business = poi.get("business")
        if not isinstance(business, dict):
            business = {}
        photos = poi.get("photos")
        if not isinstance(photos, list):
            photos = []
        first_photo = photos[0] if photos and isinstance(photos[0], dict) else {}
        rating = self._to_float(business.get("rating"))
        distance = self._to_int(poi.get("distance"))
        business_area = self._clean_optional_string(business.get("business_area"))
        cost = self._clean_optional_string(business.get("cost"))
        photo_url = self._clean_optional_string(first_photo.get("url"))
        guide_score = self._guide_score(
            category=category,
            rating=rating,
            distance_meters=distance,
            has_photo=bool(photo_url),
            business=business,
            name=name,
            type_text=type_text,
        )
        guide_reason = self._guide_reason(name, category, rating, distance, photo_url)
        return PlaceSignal(
            id=f"amap-{poi.get('id') or sanitize_place_id(name)}",
            name=name,
            category=category,
            city=city.name,
            lat=lat,
            lng=lng,
            activity_hint=self._activity_hint(name, category),
            detail_hint=self._detail_hint(name, category),
            source=self.provider_name,
            rating=rating,
            cost=cost,
            photo_url=photo_url,
            business_area=business_area,
            distance_meters=distance,
            guide_score=guide_score,
            guide_reason=guide_reason,
            raw={
                "provider": "amap",
                "type": type_text,
                "typecode": poi.get("typecode"),
                "address": poi.get("address"),
                "tag": business.get("tag"),
                "keytag": business.get("keytag"),
                "rectag": business.get("rectag"),
                "opentime_today": business.get("opentime_today"),
                "opentime_week": business.get("opentime_week"),
            },
        )

    def _get_json(self, path: str, params: dict[str, str]) -> dict[str, object]:
        query = parse.urlencode({**params, "key": self.settings.amap_api_key})
        url = f"https://restapi.amap.com{path}?{query}"
        req = request.Request(url, method="GET", headers={"Accept": "application/json"})
        try:
            with request.urlopen(req, timeout=self.settings.map_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"amap request failed: {exc.code} {detail}") from exc

        if str(payload.get("status")) != "1":
            info = payload.get("info") or "unknown amap error"
            raise RuntimeError(f"amap request failed: {info}")
        return payload

    def _parse_location(self, location: str) -> tuple[float | None, float | None]:
        parts = location.split(",", 1)
        if len(parts) != 2:
            return None, None
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            return None, None

    def _category_for(self, name: str, type_text: str) -> str:
        text = f"{name} {type_text}"
        if any(token in text for token in ("网吧", "网咖", "电竞")):
            return "netcafe"
        if any(token in text for token in ("咖啡", "茶", "饮品", "早茶", "茶楼", "茶餐厅", "点心", "面包", "烘焙")):
            return "cafe"
        if any(token in text for token in ("便利", "超市", "商场", "购物")):
            return "shop"
        if any(token in text for token in ("公园", "风景", "景点", "广场")):
            return "park"
        if any(token in text for token in ("餐饮", "小吃", "饭店", "餐厅")):
            return "food"
        return "place"

    def _is_relevant_poi(self, place: PlaceSignal) -> bool:
        text = f"{place.name} {place.raw.get('type') or ''}"
        blocked_tokens = (
            "停车场",
            "学校",
            "小学",
            "中学",
            "大学",
            "幼儿园",
            "培训",
            "医院",
            "诊所",
            "药房",
            "银行",
            "ATM",
            "政府",
            "派出所",
            "公安",
            "写字楼",
            "住宅",
            "小区",
            "公寓",
            "加油站",
            "厕所",
        )
        if any(token in text for token in blocked_tokens):
            return False
        return place.category in {"food", "cafe", "shop", "park", "netcafe"}

    def _activity_hint(self, name: str, category: str) -> str:
        hints = {
            "netcafe": f"在 {name} 的屏幕光里安静待了一会儿",
            "cafe": f"在 {name} 靠窗坐下喝一杯店里的特色咖啡",
            "shop": f"走进 {name} 挑了一个小小的补给品",
            "park": f"在 {name} 找到一小块可以玩一会儿的地方",
            "food": f"在 {name} 看了菜单，点了一份招牌餐食",
        }
        return hints.get(category, f"路过 {name} 时停下来认真看了看")

    def _detail_hint(self, name: str, category: str) -> str:
        hints = {
            "netcafe": "适合生成一张带屏幕光、键盘声和陪伴感的自拍。",
            "cafe": "短暂停留点，不像景点那样拥挤，适合写小卡片。",
            "shop": "本地生活感强，适合让 TA 看见真实城市细节。",
            "park": "适合散步、玩一会儿、停留和恢复精力。",
            "food": "这里有真实的本地味道，TA 可以进店看菜单，选择店里有代表性的菜或小吃。",
        }
        return hints.get(category, f"{name} 是附近真实可抵达的地点，可作为旅程中的短暂停留点。")

    def _guide_score(
        self,
        *,
        category: str,
        rating: float | None,
        distance_meters: int | None,
        has_photo: bool,
        business: dict[object, object],
        name: str,
        type_text: str,
    ) -> float:
        score = 50.0
        category_bonus = {
            "cafe": 18.0,
            "netcafe": 18.0,
            "food": 14.0,
            "park": 12.0,
            "shop": 8.0,
        }
        score += category_bonus.get(category, 0)
        if rating is not None:
            score += max(0.0, min(25.0, (rating - 3.0) * 12.5))
        if distance_meters is not None:
            if distance_meters <= 800:
                score += 8
            elif distance_meters <= 1800:
                score += 5
            elif distance_meters <= 3200:
                score += 2
        if has_photo:
            score += 8

        text = " ".join(
            str(value)
            for value in [
                name,
                type_text,
                business.get("tag"),
                business.get("keytag"),
                business.get("rectag"),
            ]
            if value
        )
        if any(token in text for token in ("安静", "咖啡", "甜品", "茶", "公园", "花", "书", "电竞", "网咖", "宠物")):
            score += 8
        if any(token in text for token in ("酒吧", "KTV", "夜总会", "棋牌", "洗浴")):
            score -= 16
        return round(score, 1)

    def _guide_reason(
        self,
        name: str,
        category: str,
        rating: float | None,
        distance_meters: int | None,
        photo_url: str | None,
    ) -> str:
        parts = [self._detail_hint(name, category)]
        if rating is not None:
            parts.append(f"高德评分 {rating:.1f}")
        if distance_meters is not None:
            parts.append(f"距离约 {distance_meters} 米")
        if photo_url:
            parts.append("有可用于明信片参考的地点照片")
        return "；".join(parts)

    def _to_float(self, value: object) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _to_int(self, value: object) -> int | None:
        try:
            if value is None or value == "":
                return None
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def _clean_optional_string(self, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value or None


class GoogleMapsMapProvider:
    provider_name = "google-maps-map-provider"

    def __init__(self, settings: Settings, google_client: GoogleMapsServiceClient | None = None):
        self.settings = settings
        self.google_client = google_client or GoogleMapsServiceClient(settings)
        self.fallback = MockMapProvider()

    def city_for_elapsed(self, elapsed_seconds: float) -> JourneyCity:
        return self.fallback.city_for_elapsed(elapsed_seconds)

    def places_for_city(self, city: JourneyCity) -> list[PlaceSignal]:
        if not self.google_client.configured:
            return self.fallback.places_for_city(city)
        try:
            places = self.google_client.places_nearby(
                city_name=city.name,
                lat=city.lat,
                lng=city.lng,
                theme="street",
                limit=12,
            )
        except Exception:
            places = []
        return self._merged_with_fallback(city, places, limit=12)

    def places_for_theme(self, city: JourneyCity, theme: str, limit: int = 10) -> list[PlaceSignal]:
        if not self.google_client.configured:
            return self.fallback.places_for_city(city)[:limit]
        try:
            places = self.google_client.places_nearby(
                city_name=city.name,
                lat=city.lat,
                lng=city.lng,
                theme=theme,
                radius=6000,
                limit=limit,
            )
        except Exception:
            places = []
        return self._merged_with_fallback(city, places, limit=limit)

    def _merged_with_fallback(self, city: JourneyCity, places: list[PlaceSignal], limit: int) -> list[PlaceSignal]:
        if len(places) >= limit:
            return places[:limit]
        existing_names = {place.name for place in places}
        fallback_places = [
            place.model_copy(update={"source": self.provider_name})
            for place in self.fallback.places_for_city(city)
            if place.name not in existing_names
        ]
        return [*places, *fallback_places][:limit]


class HybridMapProvider:
    provider_name = "hybrid-amap-google-map-provider"

    def __init__(
        self,
        settings: Settings,
        google_client: GoogleMapsServiceClient | None = None,
    ):
        self.amap_provider = AMapWebMapProvider(settings)
        self.google_provider = GoogleMapsMapProvider(settings, google_client=google_client)

    def city_for_elapsed(self, elapsed_seconds: float) -> JourneyCity:
        return self.amap_provider.city_for_elapsed(elapsed_seconds)

    def places_for_city(self, city: JourneyCity) -> list[PlaceSignal]:
        if is_china_city(city):
            return self.amap_provider.places_for_city(city)
        return self.google_provider.places_for_city(city)

    def places_for_theme(self, city: JourneyCity, theme: str, limit: int = 10) -> list[PlaceSignal]:
        if is_china_city(city):
            return self.amap_provider.places_for_theme(city, theme, limit=limit)
        return self.google_provider.places_for_theme(city, theme, limit=limit)


class CompanionContentProvider(Protocol):
    provider_name: str

    def postcard_text(self, pet_name: str, city: JourneyCity) -> str:
        ...


class MockCompanionContentProvider:
    provider_name = "mock-companion-content"

    def postcard_text(self, pet_name: str, city: JourneyCity) -> str:
        return (
            f"今天我在 {city.name}。这里{city.weather}，我把最安静的一小段路寄给你。"
            f"你不用急着回复，我只是想让你知道，我在好好走。"
        )


class RemoteCompanionContentProvider:
    provider_name = "remote-ai-placeholder"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.fallback = MockCompanionContentProvider()

    def postcard_text(self, pet_name: str, city: JourneyCity) -> str:
        # Future hook for Doubao/OpenAI/other model providers.
        return self.fallback.postcard_text(pet_name, city)


def build_map_provider(settings: Settings, google_client: GoogleMapsServiceClient | None = None) -> MapProvider:
    if settings.amap_api_key and settings.google_maps_api_key:
        return HybridMapProvider(settings, google_client=google_client)
    if settings.map_provider == "google" and settings.google_maps_api_key:
        return GoogleMapsMapProvider(settings, google_client=google_client)
    if settings.map_provider == "amap" and settings.amap_api_key:
        return AMapWebMapProvider(settings)
    if settings.provider_mode == "remote":
        if settings.google_maps_api_key:
            return GoogleMapsMapProvider(settings, google_client=google_client)
        if settings.amap_api_key:
            return AMapWebMapProvider(settings)
        return RemoteMapProvider(settings)
    return MockMapProvider()


def build_content_provider(settings: Settings) -> CompanionContentProvider:
    if settings.provider_mode == "remote":
        return RemoteCompanionContentProvider(settings)
    return MockCompanionContentProvider()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sanitize_place_id(name: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in name).strip("-") or "place"


def is_china_city(city: JourneyCity) -> bool:
    return city.name in {"厦门", "北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "南京", "武汉", "西安"}
