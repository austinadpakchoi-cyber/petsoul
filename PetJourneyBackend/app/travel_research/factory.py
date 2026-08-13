"""攻略研究引擎工厂。"""

from __future__ import annotations

from ..config import Settings
from .facade import TravelGuideResearchEngine


def build_travel_guide_research_engine(settings: Settings) -> TravelGuideResearchEngine:
    return TravelGuideResearchEngine(settings)
