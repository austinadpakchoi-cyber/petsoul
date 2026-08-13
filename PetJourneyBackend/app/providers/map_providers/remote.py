"""Remote 地图 Provider：占位实现，未配置密钥时回退 Mock。"""

from __future__ import annotations

from ..catalog import JourneyCity
from ...config import Settings
from ...schemas import PlaceSignal
from .mock import MockMapProvider


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
