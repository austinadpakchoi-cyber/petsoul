"""网页 API 路由注册（/api/v1/web）。框架窗口维护的共享入口。

每个模块一个路由文件，文件内：``router`` + ``capabilities(settings)``。
模块作者只改自己的文件；新增文件需共享入口维护者在此登记（通过日志提出）。
"""

from __future__ import annotations

from ...schemas.web.common import Capability
from . import (
    collection,
    communicator,
    companion_media,
    credentials,
    driving,
    farm,
    food,
    home,
    households,
    identity,
    journey,
    life,
    meta,
    pets,
    public,
    reception,
    social,
    transport,
)

WEB_ROUTER_MODULES = (
    meta,
    public,
    identity,
    households,
    pets,
    reception,
    home,
    farm,
    journey,
    transport,
    companion_media,
    food,
    social,
    communicator,
    collection,
    credentials,
    driving,
    life,
)
WEB_ROUTERS = tuple(module.router for module in WEB_ROUTER_MODULES)


def collect_capabilities(settings) -> list[Capability]:
    collected: list[Capability] = []
    for module in WEB_ROUTER_MODULES:
        collected.extend(module.capabilities(settings))
    return sorted(collected, key=lambda item: item.key)


__all__ = ["WEB_ROUTERS", "WEB_ROUTER_MODULES", "collect_capabilities"]
