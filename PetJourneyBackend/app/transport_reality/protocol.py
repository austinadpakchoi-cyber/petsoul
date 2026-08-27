"""交通现实性协议（架构审计 P1-2 包化）。"""

from __future__ import annotations

from datetime import datetime

from typing import Protocol

from ..schemas import JourneyPlan

class TransportRealityProvider(Protocol):
    provider_name: str

    def local_life_legs(
        self,
        pet: PetRecord,
        city: JourneyCity,
        places: list[PlaceSignal],
        now: datetime,
    ) -> list[ScheduledTransportLeg]:
        ...

    def worldcup_legs(
        self,
        pet: PetRecord,
        origin: PlaceSignal,
        airport: PlaceSignal,
        cafe: PlaceSignal,
        stadium: PlaceSignal,
        now: datetime,
    ) -> list[ScheduledTransportLeg]:
        ...
