"""交通班次 Provider 工厂：按配置选择真实网页检索或 Mock 实现。"""

from __future__ import annotations

from ..config import Settings
from .mock_provider import MockTransportScheduleProvider
from .openai_provider import OpenAIWebSearchTransportScheduleProvider
from .protocols import TransportScheduleProvider


def build_transport_schedule_provider(settings: Settings | None = None) -> TransportScheduleProvider:
    if settings and (
        settings.transport_schedule_provider == "openai" or settings.transport_web_search_enabled
    ):
        return OpenAIWebSearchTransportScheduleProvider(settings)
    return MockTransportScheduleProvider()
