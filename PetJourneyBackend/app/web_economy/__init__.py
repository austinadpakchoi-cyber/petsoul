"""统一物资与账本的网页适配层（唯一游戏币口径 travel_coin）。"""

from .adapter import InsufficientFunds, WebEconomy
from .inventory import WebInventory

__all__ = ["InsufficientFunds", "WebEconomy", "WebInventory"]
