"""APIRouter 集合：每个资源域一个文件。

按领域拆分原 ``main.py`` 中的 72 个端点，main.py 只负责装配依赖并挂载这些
router。
"""

from __future__ import annotations

from . import (
    auth,
    communicator,
    economy,
    geo,
    health,
    memories,
    notifications,
    pets,
    scheduler,
    travel,
    world,
)

ALL_ROUTERS = (
    health.router,
    scheduler.router,
    auth.router,
    pets.router,
    memories.router,
    travel.router,
    economy.router,
    communicator.router,
    notifications.router,
    geo.router,
    world.router,
)

__all__ = ["ALL_ROUTERS"]
