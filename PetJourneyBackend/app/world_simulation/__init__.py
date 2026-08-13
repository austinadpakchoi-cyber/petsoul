"""世界模拟引擎：快照 + 时间线 mixin 聚合 + 门面 re-export。

历史导入面保持不变：
    from app.world_simulation import (
        WorldSimulationEngine,
        build_world_simulation_engine,
    )
"""

from .facade import WorldSimulationEngine
from .factory import build_world_simulation_engine

__all__ = [
    "WorldSimulationEngine",
    "build_world_simulation_engine",
]
