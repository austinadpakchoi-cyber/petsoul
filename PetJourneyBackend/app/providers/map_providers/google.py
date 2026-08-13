"""Google Maps Provider：places_nearby 检索 + 兜底合并。"""

from __future__ import annotations

from ..catalog import JourneyCity
from ...config import Settings
from ...google_maps_services import GoogleMapsServiceClient
from ...schemas import PlaceSignal
from .mock import MockMapProvider


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
