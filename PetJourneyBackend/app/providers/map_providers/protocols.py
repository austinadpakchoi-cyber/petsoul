"""地图 Provider 协议。"""

from __future__ import annotations

from typing import Protocol

from ..catalog import JourneyCity
from ...schemas import PlaceSignal


class MapProvider(Protocol):
    provider_name: str

    def city_for_elapsed(self, elapsed_seconds: float) -> JourneyCity:
        ...

    def places_for_city(self, city: JourneyCity) -> list[PlaceSignal]:
        ...
