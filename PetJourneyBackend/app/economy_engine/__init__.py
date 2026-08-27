"""经济引擎包（架构审计 P1-2：economy_engine.py 625 行 > 400 建包）。

历史导入面保持不变：from app.economy_engine import PetEconomyEngine / EconomyConflictError / item_value。
"""

from .engine import EconomyConflictError, PetEconomyEngine
from .values import item_value

__all__ = ["PetEconomyEngine", "EconomyConflictError", "item_value"]
