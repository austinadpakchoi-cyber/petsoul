"""生图 Provider 工厂。"""

from __future__ import annotations

from ..config import Settings
from .mock import MockImageProvider
from .openai import OpenAICompatibleImageProvider
from .protocols import ImageProvider
from .seedream import DoubaoSeedreamImageProvider


def build_image_provider(settings: Settings) -> ImageProvider:
    if settings.image_provider_type == "volcengine" and (settings.image_api_key or settings.doubao_api_key):
        return DoubaoSeedreamImageProvider(settings)
    if settings.image_api_key:
        return OpenAICompatibleImageProvider(settings)
    return MockImageProvider(settings)
