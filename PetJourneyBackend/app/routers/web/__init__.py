"""网页 API 路由注册（/api/v1/web）。框架窗口维护的共享入口。

每个模块一个路由文件，文件内：``router`` + ``capabilities(settings)``。
模块作者只改自己的文件；新增文件需共享入口维护者在此登记（通过日志提出）。
"""

from __future__ import annotations

from ...schemas.web.common import Capability
from . import (
    announcements,
    character,
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
    map as map_module,
    meta,
    pets,
    public,
    reception,
    report_outcomes,
    social,
    transport,
    travel,
    world,
)

WEB_ROUTER_MODULES = (
    meta,
    public,
    identity,
    households,
    pets,
    character,
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
    map_module,  # 地图底图配置（CR-6C2B-MAP W0）；`map` 是内置名，导入时改名避免遮蔽
    world,       # 统一世界状态（CR-6C2B-MAP W1）：纯读聚合
    travel,      # 旅行心愿与计划（TRV-00 §23.4，I）：纯读
    # 运营后台的两个玩家侧入口：原先由 web_admin 直接 include_router，绕开了这里，/meta 的能力表收不到它们声明的能力
    # （Q 2026-09-24 报：platform.announcements / platform.public_assets / social.report_outcomes 前端查不到）。
    # 登记在这里之后，web_admin 的 `_mount_once` 按路径判断已挂、自动跳过，不会挂两遍。
    announcements,
    report_outcomes,
)
WEB_ROUTERS = tuple(module.router for module in WEB_ROUTER_MODULES)


def collect_capabilities(settings) -> list[Capability]:
    collected: list[Capability] = []
    for module in WEB_ROUTER_MODULES:
        collected.extend(module.capabilities(settings))
    return sorted(collected, key=lambda item: item.key)


__all__ = ["WEB_ROUTERS", "WEB_ROUTER_MODULES", "collect_capabilities"]
