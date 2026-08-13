"""旅行任务引擎工厂。"""

from __future__ import annotations

from ..config import Settings
from .facade import PetTravelQuestEngine
from ..travel_research import build_travel_guide_research_engine


def build_pet_travel_quest_engine(settings: Settings) -> PetTravelQuestEngine:
    return PetTravelQuestEngine(
        settings=settings,
        research_engine=build_travel_guide_research_engine(settings),
    )
