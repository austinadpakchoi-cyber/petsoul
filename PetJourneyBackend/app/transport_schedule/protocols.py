"""交通班次 Provider 协议。"""

from __future__ import annotations

from typing import Protocol

from .models import TransportScheduleCandidate, TransportScheduleRequest


class TransportScheduleProvider(Protocol):
    provider_name: str

    def best_candidate(self, search: TransportScheduleRequest) -> TransportScheduleCandidate | None:
        ...

    def best_itinerary(self, search: TransportScheduleRequest) -> list[TransportScheduleCandidate]:
        ...
