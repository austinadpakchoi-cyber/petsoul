"""宠物生活模拟引擎门面：tick + 决策 mixin 聚合。"""

from .decision import PetLifeDecisionMixin
from .tick import PetLifeTickMixin


class PetLifeSimulationEngine(
    PetLifeTickMixin,
    PetLifeDecisionMixin,
):
    provider_name = "petsoul-life-simulation-engine"
