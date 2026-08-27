"""Google 路线结果模型（架构审计 P1-2 包化）。"""

from __future__ import annotations

from dataclasses import dataclass, field

@dataclass(frozen=True)
class GoogleRouteResult:
    distance_meters: int | None
    duration_seconds: int | None
    polyline: str | None
    provider: str
