"""路线规划器工厂（架构审计 P1-2 包化）。"""

from __future__ import annotations

from ..config import Settings
from ..google_maps_services import GoogleMapsServiceClient
from .mock import MockTravelRoutePlanner
from .remote import RemoteTravelRoutePlanner

def build_route_planner(
    settings: Settings,
    map_provider: MapProvider,
    transport_provider: TransportRealityProvider | None = None,
    amap_client: AMapWebServiceClient | None = None,
    google_client: GoogleMapsServiceClient | None = None,
) -> TravelRoutePlanner:
    transport_provider = transport_provider or build_transport_reality_provider()
    if settings.provider_mode == "remote" or settings.amap_api_key or settings.google_maps_api_key:
        return RemoteTravelRoutePlanner(settings, map_provider, transport_provider, amap_client, google_client)
    return MockTravelRoutePlanner(settings, map_provider, transport_provider)
