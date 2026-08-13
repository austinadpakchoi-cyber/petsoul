"""交通班次数据模型：搜索请求与候选班次。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..schemas import PlaceSignal, TravelMode
from ..storage import PetRecord


@dataclass(frozen=True, slots=True)
class TransportScheduleRequest:
    pet: PetRecord
    mode: TravelMode
    origin: PlaceSignal
    destination: PlaceSignal
    depart_after: datetime
    now: datetime
    context: str


@dataclass(frozen=True, slots=True)
class TransportScheduleCandidate:
    mode: TravelMode
    carrier: str | None
    service_number: str
    origin_name: str
    destination_name: str
    scheduled_departure: datetime
    scheduled_arrival: datetime
    terminal_or_platform: str | None = None
    source_urls: tuple[str, ...] = ()
    confidence: str = "medium"
    search_query: str | None = None
    notes: str | None = None
    reality_level: str = "web_reference_schedule"
    is_simulated: bool = True
