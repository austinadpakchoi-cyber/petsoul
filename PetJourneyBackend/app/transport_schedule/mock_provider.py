"""Mock 交通班次 Provider（默认，不发起真实网络请求）。"""

from __future__ import annotations

from .models import TransportScheduleCandidate, TransportScheduleRequest


class MockTransportScheduleProvider:
    provider_name = "mock-transport-schedule-provider"

    def best_candidate(self, search: TransportScheduleRequest) -> TransportScheduleCandidate | None:
        return None

    def best_itinerary(self, search: TransportScheduleRequest) -> list[TransportScheduleCandidate]:
        return []
