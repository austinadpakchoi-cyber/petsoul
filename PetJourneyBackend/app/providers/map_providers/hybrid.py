"""混合地图 Provider：中国城市走高德，其余走 Google。"""

from __future__ import annotations

from ..catalog import JourneyCity, is_china_city
from ...config import Settings
from ...google_maps_services import GoogleMapsServiceClient
from ...schemas import PlaceSignal
from .amap import AMapWebMapProvider
from .google import GoogleMapsMapProvider


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
