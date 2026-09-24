"""平台运营后台（`/api/v1/admin`）。组合根在 `app/main.py` 里调用 `install_admin_platform`。

边界（这三条是这个包存在的理由，改动前先读）：
1. **不复制第二套真相。** 读走既有表与既有投影；写走既有领域命令、既有事务与既有账本。
   这里只新增 admin_* 表：员工身份、审计、平台处置状态、运营内容版本。
2. **员工与玩家是两套身份。** 两套 cookie、两张会话表、两条解析路径。玩家身份（含家庭管理员）
   到平台权限**没有任何映射**——不是"检查得严"，是根本没有那条路。
3. **查询不推进世界、不调模型。** 后台的读接口只读既有事实并按当前事实评估一次心跳
   （与 `/ops/runtime` 同一个纯函数）。合法访问会写审计，那是审计，不是业务写入。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI

from ..storage import JourneyStorage
from .assets import AdminAssets
from .audit import AuditLog
from .batches import AdminBatchGrants
from .belongings import AdminBelongings
from .commands import AdminCommands
from .config import AdminSettings, load_admin_settings
from .content import AdminContent
from .diagnosis import AdminDiagnosis
from .directory import AdminDirectory
from .economy_checks import AdminEconomyChecks
from .enforcement import FrozenAccounts, guard_authenticate, guard_provider_meter, guard_session_check
from .errors import AdminAPIError, AdminErrorCode, install_admin_errors
from .identity import AdminIdentityService
from .moderation import AdminModeration
from .overview import AdminOverview
from .pet_runtime import AdminPetRuntime
from .relay_receipts import AdminRelayReceipts
from .pricing import AdminPricing
from .residents import AdminResidents
from .reversals import AdminReversals
from .social import AdminSocial
from .switches import SwitchStore
from .system import AdminSystem

logger = logging.getLogger("petsoul.admin")
ADMIN_BACKEND_VERSION = "admin-0.1.0"


@dataclass
class AdminServices:
    settings: AdminSettings
    identity: AdminIdentityService
    audit: AuditLog
    directory: AdminDirectory
    diagnosis: AdminDiagnosis
    overview: AdminOverview
    switches: SwitchStore
    content: AdminContent
    commands: AdminCommands
    frozen: FrozenAccounts
    configured: bool           # auth_secret 是否可用；不可用时登录接口如实回 503，不用假会话顶替
    assets: AdminAssets
    batches: "AdminBatchGrants"
    pricing: AdminPricing      # 平台调用价格表（只追加）与费用估算
    economy_checks: AdminEconomyChecks  # 游戏经济只读对账
    reversals: AdminReversals  # 冲正后台补偿
    moderation: AdminModeration  # 举报认领与处理回执
    belongings: AdminBelongings  # 宠物的东西与家里的东西（只读，不含正文）
    system: AdminSystem          # 系统运行：投递、执行者、任务线、迁移、供应商、开关、备份
    social: AdminSocial          # 社交与举报关联（只给公开范围里的摘要与关系事实）
    residents: AdminResidents    # 待领养居民名单
    pet_runtime: AdminPetRuntime  # 宠物运行总览（心跳 / 大脑 / 钱袋子）与暂停
    relay: AdminRelayReceipts     # 经中转站的逐次调用回执：幂等导入与按日汇总（ADM-COST-01）
    tables_ready: bool         # 1500–1580 迁移是否已应用


def _tables_ready(storage: JourneyStorage) -> bool:
    names = ("admin_staff", "admin_sessions", "admin_audit", "admin_account_flags", "admin_switches",
             "admin_content_items", "admin_content_revisions", "admin_content_publications",
             "admin_grant_batches", "admin_grant_batch_items", "admin_assets", "admin_provider_prices", "admin_report_claims", "admin_pet_maintenance", "admin_relay_receipts")
    with storage.connect() as conn:
        found = conn.execute(
            f"SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ({','.join('?' for _ in names)})", names
        ).fetchone()[0]
    return found == len(names)


def _mount_once(app: FastAPI, router) -> None:
    """挂一个路由；它的路径已经**全部**挂在应用上（标准入口登记过）就跳过，不重复挂。

    **它只防「整组已挂」，不防「半挂」**（Q 2026-09-24 指出）：只挂上一部分路径时，这里会把整组再挂一遍，已挂的那几条就重复了。
    今天安全，是因为标准入口 `WEB_ROUTER_MODULES` 总是整个路由器一起 `include`，不会出现半挂状态。
    哪天有人改成按单条路由挂、或把一个路由器拆成分批注册，这里要改成按「路径＋方法」逐条判、只补缺的。
    """
    mounted = {getattr(route, "path", None) for route in app.routes}
    if not {route.path for route in router.routes} <= mounted:
        app.include_router(router)


def install_admin_platform(app: FastAPI, *, storage: JourneyStorage, settings) -> AdminServices:
    """在 `app.state.web` 装配好之后调用。装配 + 装错误处理 + 装执行点 + 挂路由。"""
    admin_settings = load_admin_settings(getattr(settings, "web_environment", "dev"), bool(getattr(settings, "web_cookie_secure", True)))
    web = app.state.web
    auth_secret = getattr(settings, "auth_secret", None) or ""
    audit = AuditLog(storage)
    switches = SwitchStore(storage)
    frozen = FrozenAccounts(storage)
    content = AdminContent(storage)
    diagnosis = AdminDiagnosis(storage, web)
    pricing = AdminPricing(storage, audit, app.state.web_idempotency)
    economy_checks = AdminEconomyChecks(storage)
    overview = AdminOverview(storage, web, settings, pricing=pricing, economy_checks=economy_checks)
    commands = AdminCommands(storage, web, audit, switches, frozen, app.state.web_idempotency)
    services = AdminServices(
        settings=admin_settings,
        identity=AdminIdentityService(storage, auth_secret=auth_secret, settings=admin_settings),
        audit=audit,
        directory=AdminDirectory(storage),
        diagnosis=diagnosis,
        overview=overview,
        switches=switches,
        content=content,
        commands=commands,
        assets=AdminAssets(storage, audit,
                           root=Path(getattr(settings, "database_path", ".")).parent / "admin-assets",
                           private_media_root=Path(getattr(settings, "web_private_media_dir", "."))),
        batches=AdminBatchGrants(storage, web, audit, frozen, app.state.web_idempotency),
        pricing=pricing,
        economy_checks=economy_checks,
        reversals=AdminReversals(storage, web, audit, app.state.web_idempotency),
        moderation=AdminModeration(storage, audit),
        belongings=AdminBelongings(storage),
        system=AdminSystem(storage, switches=switches, environment=overview.environment),
        social=AdminSocial(storage),
        residents=AdminResidents(storage),
        pet_runtime=AdminPetRuntime(storage, settings, commands, audit),
        relay=AdminRelayReceipts(storage, commands, audit),
        frozen=frozen,
        configured=bool(auth_secret),
        tables_ready=_tables_ready(storage),
    )
    app.state.admin = services

    install_admin_errors(app)

    # ---- 执行点：让后台的处置真正落到玩家侧（只在组合根装饰，见 enforcement.py）----
    previous_check = getattr(app.state, "web_session_revocation_check", None)
    if previous_check is not None:
        app.state.web_session_revocation_check = guard_session_check(previous_check, frozen)
    web.identity.authenticate = guard_authenticate(web.identity.authenticate, frozen)  # type: ignore[method-assign]
    guard_provider_meter(getattr(getattr(web, "providers", None), "meter", None), switches)

    # ---- 内置目录的运营发布覆盖层（冒险模板 / 作物 / 打工岗位；见 app/content_overlay.py）----
    from ..content_overlay import set_resolver
    set_resolver(content.live)

    from ..routers.admin import ADMIN_ROUTERS
    from ..routers.web.announcements import router as announcements_router
    from ..routers.web.report_outcomes import router as report_outcomes_router
    for router in ADMIN_ROUTERS:
        app.include_router(router)
    # 两个玩家侧入口（公告 /api/v1/web/announcements、举报人看处理结果 /api/v1/web/reports/mine）的正式归宿是
    # routers/web 的 WEB_ROUTER_MODULES（共享入口，归 I）：只有登记在那里，/meta 的能力表才收得到它们声明的能力
    # （Q 2026-09-24 报：platform.announcements / platform.public_assets / social.report_outcomes 前端查不到）。
    # 登记之前由这里挂；登记之后这里自动跳过，免得同一路径挂两遍——两边不必同时改。
    _mount_once(app, announcements_router)
    _mount_once(app, report_outcomes_router)

    if not services.tables_ready:
        logger.warning("admin tables missing: 迁移 1500–1580 尚未全部应用，后台接口会如实回 NOT_CONFIGURED")
    return services


__all__ = ["AdminAPIError", "AdminErrorCode", "AdminServices", "ADMIN_BACKEND_VERSION", "install_admin_platform"]
