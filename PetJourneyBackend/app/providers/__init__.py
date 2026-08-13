"""Provider 门面——保持 `from app.providers import X` 历史导入面不变。

拆分前所有 `from app.providers import ...` 的符号在此统一 re-export，
并保留 `build_map_provider` / `build_content_provider` 两个工厂函数。
"""

from __future__ import annotations

from ..config import Settings
from ..google_maps_services import GoogleMapsServiceClient
from .catalog import CITIES, SAFE_PLACE_CATALOG, JourneyCity, is_china_city
from .content_providers import (
    CompanionContentProvider,
    MockCompanionContentProvider,
    RemoteCompanionContentProvider,
)
from .map_providers import (
    AMapWebMapProvider,
    GoogleMapsMapProvider,
    HybridMapProvider,
    MapProvider,
    MockMapProvider,
    RemoteMapProvider,
)


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


__all__ = [
    "AMapWebMapProvider",
    "CITIES",
    "CompanionContentProvider",
    "GoogleMapsMapProvider",
    "HybridMapProvider",
    "JourneyCity",
    "MapProvider",
    "MockCompanionContentProvider",
    "MockMapProvider",
    "RemoteCompanionContentProvider",
    "RemoteMapProvider",
    "SAFE_PLACE_CATALOG",
    "build_content_provider",
    "build_map_provider",
    "is_china_city",
]
