"""伴生内容 Provider：明信片文案协议 + Mock/Remote 实现。

将原 providers.py 尾部 CompanionContentProvider 相关类独立成文件。
"""

from __future__ import annotations

from typing import Protocol

from ..config import Settings
from .catalog import JourneyCity


class CompanionContentProvider(Protocol):
    provider_name: str

    def postcard_text(self, pet_name: str, city: JourneyCity) -> str:
        ...


class MockCompanionContentProvider:
    provider_name = "mock-companion-content"

    def postcard_text(self, pet_name: str, city: JourneyCity) -> str:
        return (
            f"今天我在 {city.name}。这里{city.weather}，我把最安静的一小段路寄给你。"
            f"你不用急着回复，我只是想让你知道，我在好好走。"
        )


class RemoteCompanionContentProvider:
    provider_name = "remote-ai-placeholder"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.fallback = MockCompanionContentProvider()

    def postcard_text(self, pet_name: str, city: JourneyCity) -> str:
        # Future hook for Doubao/OpenAI/other model providers.
        return self.fallback.postcard_text(pet_name, city)
