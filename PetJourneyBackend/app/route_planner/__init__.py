"""路线规划包（架构审计 P1-2：route_planner.py 676 行 > 400 建包）。历史导入面不变。"""

from .mock import MockTravelRoutePlanner
from .remote import RemoteTravelRoutePlanner
from .protocol import TravelRoutePlanner, enforce_transport_reality, adapt_journey_plan_to_route_plan
from .factory import build_route_planner

__all__ = [
    "MockTravelRoutePlanner",
    "RemoteTravelRoutePlanner",
    "TravelRoutePlanner",
    "enforce_transport_reality",
    "adapt_journey_plan_to_route_plan",
    "build_route_planner",
]
