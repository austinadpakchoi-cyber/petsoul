"""图文攻略轻量预览的行程计划（架构审计 P1-3 从 http_utils 迁入引擎层）。

只为「还没正式生成攻略」的宠物拼一份可展示的 JourneyPlan；正式攻略走
IllustratedGuideEngine 主链路。
"""

from __future__ import annotations

from ..agent_engine import JourneyEngine
from ..route_planner import TravelRoutePlanner
from ..schemas import JourneyPlan
from ..utils import utcnow


def lightweight_illustrated_guide_plan(
    engine: JourneyEngine,
    route_planner: TravelRoutePlanner,
    pet,
) -> JourneyPlan:
    now = utcnow()
    elapsed = (now - pet.created_at).total_seconds()
    city = engine._city_for_elapsed(elapsed, now=now)
    planner = getattr(route_planner, "fallback", route_planner)
    return planner.build_journey_plan(pet, city, now)
