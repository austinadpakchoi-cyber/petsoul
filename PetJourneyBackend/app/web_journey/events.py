"""世界事件与下游协议：结算登记的事实按 outbox 投递给各下游（家庭来信、动态、收藏、证件、朋友、攻略）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from .repository import JourneyRecord, VisitRecord


@dataclass
class WorldEvent:
    journey: JourneyRecord
    key: str
    kind: str
    occurred_at: datetime
    pet_name: str
    visit: VisitRecord | None = None
    data: dict = field(default_factory=dict)

    @property
    def source_event_id(self) -> str:
        return f"{self.journey.journey_id}:{self.key}"


class WorldEventSink(Protocol):
    def on_world_event(self, event: WorldEvent) -> None: ...
