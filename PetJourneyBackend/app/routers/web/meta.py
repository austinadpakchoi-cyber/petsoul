"""平台元信息：契约版本、服务器时间、能力清单、已应用迁移（公开，无用户数据）；运行状态（只给本机或带管理令牌的人）。"""

from __future__ import annotations

import hmac

from fastapi import Request

from ...config import BASE_DIR
from ...schemas.web.common import AuthMethod, Capability, CapabilityStatus, WebErrorCode, WebMeta
from ...schemas.web.ops import FrontendHint, OpsStatus, OutboxHealth, PetRuntimeStatus, ProviderHealth, ProviderState, RuntimeDueItem, WorldRunnerStatus
from ...utils import parse_dt, utcnow
from ...web_platform import WEB_BACKEND_VERSION, WebAPIError
from ...web_platform.lease import lease_status
from ...web_runtime.heartbeat_policy import HeartbeatPolicy, evaluate
from ...web_runtime.reasons import silence_of
from ...web_providers.readiness import amap_ready, google_state, image_ready, llm_ready
from ._shared import cap, web_of, web_router

router = web_router("platform")


def capabilities(settings) -> list[Capability]:
    return [
        cap("platform.meta", "platform", CapabilityStatus.available),
        cap("platform.idempotency", "platform", CapabilityStatus.available),
        cap("platform.tasks", "platform", CapabilityStatus.available,
            f"世界任务：{_runner_note(settings)}；同一时刻只有一个进程推进世界（数据库租约），状态见 /ops/status"),
    ]


def _runner_note(settings) -> str:
    runner = getattr(settings, "web_world_runner", "embedded")
    if runner == "off" or settings.web_world_tick_seconds <= 0:
        return "已关闭"
    return "由独立任务进程推进（python -m app.web_worker）" if runner == "worker" else f"API 进程内每 {settings.web_world_tick_seconds:g} 秒推进一次"


@router.get("/meta", response_model=WebMeta)
def web_meta(request: Request) -> WebMeta:
    from . import collect_capabilities  # 避免循环导入：聚合函数在包 __init__

    settings = request.app.state.settings
    methods = [AuthMethod.web_password, AuthMethod.apple_bearer] if settings.auth_secret else []
    return WebMeta(
        server_time=utcnow(),
        backend_version=WEB_BACKEND_VERSION,
        auth_methods_available=methods,
        capabilities=collect_capabilities(settings),
        applied_migrations=list(request.app.state.web_applied_migrations),
    )


LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
PROVIDERS = (("llm", "对话模型"), ("amap", "高德地点/路线"), ("amap_static", "高德静态底图"), ("google", "Google 地图"), ("image", "生图"))


def _allowed(request: Request) -> bool:
    """本机直连（开发、真实联调）可以看；经过反向代理（带 X-Forwarded-For）或 staging/production 必须带管理令牌。"""
    settings = request.app.state.settings
    token = settings.economy_admin_token
    given = request.headers.get("X-Admin-Token") or ""
    if token and given and hmac.compare_digest(given, token):
        return True
    host = request.client.host if request.client else ""
    proxied = bool(request.headers.get("X-Forwarded-For") or request.headers.get("X-Real-IP"))
    return host in LOCAL_HOSTS and not proxied and settings.web_environment not in ("staging", "production")


def _display(path) -> str:
    try:
        return str(path.resolve().relative_to(BASE_DIR.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _configured(settings, provider: str) -> bool:
    return {"llm": llm_ready(settings), "amap": amap_ready(settings), "amap_static": amap_ready(settings), "google": google_state(settings)[0] or bool(
        settings.web_providers_enabled and settings.google_maps_api_key), "image": image_ready(settings)}[provider]


@router.get("/ops/status", response_model=OpsStatus)
def ops_status(request: Request) -> OpsStatus:
    """真实联调/部署时看的运行状态：用的哪份配置与数据、供应商是“已配置”还是“真的调通过”、世界任务有没有在跑、能力清单、前端怎么连。"""
    from . import collect_capabilities

    if not _allowed(request):
        raise WebAPIError(WebErrorCode.forbidden, "运行状态只给本机或带管理令牌的请求。", 403, details={"reason": "ops_only"})
    settings = request.app.state.settings
    storage = request.app.state.storage
    web = web_of(request)
    with storage.connect() as conn:
        health = {r["provider"]: r for r in conn.execute("SELECT * FROM web_provider_health").fetchall()}
    usage = web.providers.meter.snapshot() if web.providers.meter is not None else {}
    caps = web.providers.meter.caps if web.providers.meter is not None else {}
    providers = []
    for key, label in PROVIDERS:
        row = health.get(key)
        success = parse_dt(row["last_success_at"]) if row and row["last_success_at"] else None
        failure = parse_dt(row["last_failure_at"]) if row and row["last_failure_at"] else None
        if not settings.web_providers_enabled:
            state = ProviderState.disabled
        elif not _configured(settings, key):
            state = ProviderState.not_configured
        elif failure and (success is None or failure > success):
            state = ProviderState.failing
        elif success:
            state = ProviderState.verified
        else:
            state = ProviderState.configured
        providers.append(ProviderHealth(provider=key, label=label, state=state, last_success_at=success, last_failure_at=failure,
                                        last_error=row["last_error"] if row and state is ProviderState.failing else None,
                                        calls_today=int((usage.get(key) or {}).get("calls", 0)), daily_cap=caps.get(key)))
    def lane(name: str, ticker) -> WorldRunnerStatus:
        lease = lease_status(storage, name) or {}
        return WorldRunnerStatus(runner=settings.web_world_runner if settings.web_world_tick_seconds > 0 else "off", interval_seconds=settings.web_world_tick_seconds,
                                 running_here=ticker.running, lease_alive=bool(lease.get("alive")), lease_holder_role=lease.get("holder_role"),
                                 lease_pid=lease.get("pid"), last_tick_at=lease.get("last_tick_at"), last_ok_at=lease.get("last_ok_at"),
                                 last_error=lease.get("last_error"), ticks=int(lease.get("ticks") or 0))

    world = lane("world", web.ticker).model_copy(update={"due_lag_seconds": web.journeys.due_lag_seconds()})  # 世界线：结算与确定性下游
    cognition = lane("cognition", web.cognition)  # 认知线：可能调模型的表达与回复（卡住不影响世界线）
    migrations = list(request.app.state.web_applied_migrations)
    live = settings.web_environment in ("real-local", "staging", "production")
    frontend = FrontendHint(data_mode="live", api_base="/api/v1/web", dev_proxy_target=str(settings.public_base_url),
                            note=("前端用 live 模式连这个后端（vite --mode live，PETSOUL_DEV_API_TARGET 指向上面的地址）；fixture 模式是演示数据，不连后端。"
                                  if not live else "真实环境：前端必须是 live 模式；不要用 fixture 模式验证真实体验。"))
    return OpsStatus(environment=settings.web_environment, server_time=utcnow(), backend_version=WEB_BACKEND_VERSION, database=_display(settings.database_path),
                     media_dir=_display(settings.web_private_media_dir), sqlite_wal=bool(settings.sqlite_wal), providers_enabled=settings.web_providers_enabled,
                     providers=providers, world=world, applied_migrations=len(migrations), last_migration=migrations[-1] if migrations else None,
                     capabilities=collect_capabilities(settings), frontend=frontend, cognition=cognition, tasks=web.illustrations.tasks.task_health(),
                     outbox=[OutboxHealth(consumer=name, **counts) for name, counts in sorted(web.journeys.outbox.stats(utcnow()).items())])


def _reason_text(decision, row: dict) -> str | None:
    """安静原因取枚举的取值（asleep / quiet / budget_exhausted……），不是 Python 的枚举名。"""
    reason = decision.silence_reason or silence_of(decision) or row.get("silence_reason")
    return getattr(reason, "value", reason) if reason else None


@router.get("/ops/runtime/{pet_id}", response_model=PetRuntimeStatus)
def pet_runtime(pet_id: str, request: Request) -> PetRuntimeStatus:
    """一只宠物此刻的运行详情：在做什么、下次什么时候看、为什么安静、有哪些到期事项。

    只读：按当前事实立刻评估一次心跳，但不执行、不记录、不调模型。只给本机或带管理令牌的请求，不含正文与密钥。
    """
    if not _allowed(request):
        raise WebAPIError(WebErrorCode.forbidden, "运行状态只给本机或带管理令牌的请求。", 403, details={"reason": "ops_only"})
    web = web_of(request)
    projector = getattr(web, "projector", None)
    if projector is None:
        raise WebAPIError(WebErrorCode.not_configured, "这个环境没有启用运行投影。", 503, details={"capability": "ops.runtime"})
    if web.pets.profile(pet_id) is None:
        raise WebAPIError(WebErrorCode.not_found, "没有这只宠物。", 404, details={"reason": "pet_not_found"})
    now = utcnow()
    state = projector.state(pet_id, now)
    facts = projector.facts(pet_id, now)
    row = projector.runtime.row(pet_id)
    decision = evaluate(state, (), HeartbeatPolicy(), now, facts=facts)
    activity = state.primary_activity
    return PetRuntimeStatus(
        pet_id=pet_id, as_of=state.as_of, realm_id=state.realm_id, household_id=state.household_id, timezone=state.timezone,
        region_id=state.region_id, scene_ref=state.scene_ref,
        activity_kind=activity.kind if activity else "unknown", activity_ref=activity.ref if activity else None,
        activity_ends_at=activity.ends_at if activity else None, interruptible=bool(activity.interruptible) if activity else True,
        sleep_window=[f"{t:%H:%M}" for t in state.sleep_window] if state.sleep_window else [],
        versions={"runtime": state.versions.runtime_epoch, "activity": state.versions.activity_epoch, "dna": state.versions.dna_version,
                  "privacy": state.versions.privacy_epoch, "membership": state.versions.membership_epoch, "itinerary": state.versions.itinerary_version},
        due_items=[RuntimeDueItem(ref=item.ref, kind=item.kind.value, due_at=item.due_at, commitment=item.commitment) for item in facts.due_items],
        next_check_at=decision.next_check_at,
        next_review_at=parse_dt(row["next_review_at"]) if row.get("next_review_at") else None,
        silence_reason=_reason_text(decision, row),
        last_evaluated_at=parse_dt(row["last_evaluated_at"]) if row.get("last_evaluated_at") else None,
        last_decision_at=parse_dt(row["last_decision_at"]) if row.get("last_decision_at") else None,
        last_decision_by=row.get("last_decision_by"), maintenance=bool(row.get("maintenance")),
        heartbeat_action=decision.action.value, heartbeat_reasons=list(decision.reason_codes),
        cognition_enabled=facts.cognition.enabled, brain_mode=getattr(request.app.state.settings, "web_brain_mode", "off"))
