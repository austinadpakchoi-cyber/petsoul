"""平行交通网页领域（R0：服务边界 + 时间线纯函数；不改 transport_schedule / transport_reality /
route_planner / world_simulation 旧引擎，后续通过适配层接入）。"""

from .service import TransportService
from .timeline import (
    derive_service_number,
    effective_arrival,
    effective_departure,
    leg_progress,
    position_along,
    remaining,
    schedule_after_leg,
    world_service_key,
)

__all__ = [
    "TransportService",
    "derive_service_number",
    "effective_arrival",
    "effective_departure",
    "leg_progress",
    "position_along",
    "remaining",
    "schedule_after_leg",
    "world_service_key",
]
