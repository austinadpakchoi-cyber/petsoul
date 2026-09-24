"""管理端路由注册（`/api/v1/admin`）。由 `app/web_admin/install_admin_platform` 挂载，不进玩家侧 WEB_ROUTERS。"""

from __future__ import annotations

from . import assets, audit, auth, batches, content, costs, glossary, moderation, ops, reversals, runtime, users, world

ADMIN_ROUTER_MODULES = (auth, glossary, ops, users, world, runtime, moderation, content, assets, batches, reversals, costs, audit)
ADMIN_ROUTERS = tuple(module.router for module in ADMIN_ROUTER_MODULES)

__all__ = ["ADMIN_ROUTERS", "ADMIN_ROUTER_MODULES"]
