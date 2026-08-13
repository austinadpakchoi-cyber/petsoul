"""地图 Provider 子包门面——保持 from app.providers.map_providers import X 历史导入面。"""

from .amap import AMapWebMapProvider
from .google import GoogleMapsMapProvider
from .hybrid import HybridMapProvider
from .mock import MockMapProvider
from .protocols import MapProvider
from .remote import RemoteMapProvider

__all__ = [
    "MapProvider",
    "MockMapProvider",
    "RemoteMapProvider",
    "AMapWebMapProvider",
    "GoogleMapsMapProvider",
    "HybridMapProvider",
]
