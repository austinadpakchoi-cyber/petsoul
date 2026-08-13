"""旅行任务引擎门面：任务流 + 计划 mixin 聚合。"""

from .planning import PetTravelQuestPlanningMixin
from .quest_flow import PetTravelQuestFlowMixin


class PetTravelQuestEngine(
    PetTravelQuestFlowMixin,
    PetTravelQuestPlanningMixin,
):
    provider_name = "mock-pet-travel-quest-engine"
