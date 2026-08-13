"""世界模拟引擎工厂。"""

from __future__ import annotations

from ..config import Settings
from .facade import WorldSimulationEngine


def build_world_simulation_engine(settings: Settings) -> WorldSimulationEngine:
    return WorldSimulationEngine(settings)
