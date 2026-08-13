"""宠物生活模拟引擎工厂。"""

from __future__ import annotations

from ..config import Settings
from ..memory_store import MemoryStore
from .facade import PetLifeSimulationEngine


def build_pet_life_simulation_engine(settings: Settings, memory_store: MemoryStore) -> PetLifeSimulationEngine:
    return PetLifeSimulationEngine(settings, memory_store)
