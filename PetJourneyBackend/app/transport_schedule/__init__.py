"""交通班次：按真实公开班次时间线生成行程段。

包优先于同名模块，门面 re-export 保持历史导入面：
    from app.transport_schedule import (
        TransportScheduleRequest,
        TransportScheduleCandidate,
        TransportScheduleProvider,
        MockTransportScheduleProvider,
        OpenAIWebSearchTransportScheduleProvider,
        build_transport_schedule_provider,
    )
"""

from .factory import build_transport_schedule_provider
from .mock_provider import MockTransportScheduleProvider
from .models import TransportScheduleCandidate, TransportScheduleRequest
from .openai_provider import OpenAIWebSearchTransportScheduleProvider
from .protocols import TransportScheduleProvider

__all__ = [
    "TransportScheduleRequest",
    "TransportScheduleCandidate",
    "TransportScheduleProvider",
    "MockTransportScheduleProvider",
    "OpenAIWebSearchTransportScheduleProvider",
    "build_transport_schedule_provider",
]
