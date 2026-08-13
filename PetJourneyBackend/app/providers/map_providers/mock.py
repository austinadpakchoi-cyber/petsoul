"""Mock 地图 Provider：城市目录 + 安全地点目录的本地实现。"""

from __future__ import annotations

from ..catalog import CITIES, SAFE_PLACE_CATALOG, JourneyCity
from ...schemas import PlaceSignal


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
