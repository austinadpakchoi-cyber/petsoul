"""交通现实性包（架构审计 P1-2：transport_reality.py 415 行 > 400 建包）。历史导入面不变。"""

from .protocol import TransportRealityProvider
from .mock import MockTransportRealityProvider
from .factory import build_transport_reality_provider

__all__ = [
    "TransportRealityProvider",
    "MockTransportRealityProvider",
    "build_transport_reality_provider",
]
