"""宠物生活模拟引擎：tick + 决策 mixin 聚合 + 门面 re-export。

历史导入面保持不变：
    from app.pet_life_engine import (
        PetLifeSimulationEngine,
        build_pet_life_simulation_engine,
    )
"""

from .facade import PetLifeSimulationEngine
from .factory import build_pet_life_simulation_engine

__all__ = [
    "PetLifeSimulationEngine",
    "build_pet_life_simulation_engine",
]
