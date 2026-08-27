"""Google Maps 服务工厂（架构审计 P1-2 包化）。"""

from __future__ import annotations

from ..config import Settings
from .client import GoogleMapsServiceClient

def build_google_maps_service(settings: Settings) -> GoogleMapsServiceClient:
    return GoogleMapsServiceClient(settings)
