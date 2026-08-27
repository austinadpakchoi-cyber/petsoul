"""交通现实性工厂（架构审计 P1-2 包化）。"""

from __future__ import annotations

from ..config import Settings
from ..transport_schedule import build_transport_schedule_provider
from .mock import MockTransportRealityProvider
from .protocol import TransportRealityProvider

def build_transport_reality_provider(settings: Settings | None = None) -> TransportRealityProvider:
    return MockTransportRealityProvider(build_transport_schedule_provider(settings))
