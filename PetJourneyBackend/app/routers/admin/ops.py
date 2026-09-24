"""运营首页、运行健康、两本独立账目、受控开关。全部是只读，唯一的写是开关那一条。"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import Depends, Request

from ...schemas.admin import SwitchRequest
from ...web_admin.errors import AdminAPIError
from ...web_admin.identity import AdminPrincipal
from ...web_admin.permissions import Permission
from ._shared import admin_of, admin_router, context, needs

router = admin_router("ops")


@router.get("/overview")
def overview(request: Request, principal: AdminPrincipal = Depends(needs(Permission.OPS_READ))) -> dict:
    """首页优先给"需要处理的问题"，每个数字带来源；没有来源的显示为未接入，不填 0。"""
    services = admin_of(request)
    metrics = [asdict(m) for m in services.overview.metrics()]
    attention = [m for m in metrics if m["key"] in
                 ("tasks.overdue", "tasks.failed", "photos.failed", "reports.open", "calls.unknown", "accounts.frozen",
                  "economy.mismatch", "pets.paused", "pets.thinking_stuck", "pets.heartbeat_late")
                 and (m["value"] or 0) > 0]
    return {
        "environment": services.overview.environment(),
        "metrics": metrics,
        "attention": attention,
        "runtime": services.overview.runtime_health(),
        "switches": [asdict(s) for s in services.switches.all()],
        "read_only_note": "这个页面只读既有事实：不推进世界、不发起任何模型或生图调用。",
    }


@router.get("/providers/usage")
def provider_usage(request: Request, principal: AdminPrincipal = Depends(needs(Permission.PROVIDER_READ))) -> dict:
    return admin_of(request).overview.provider_usage()


@router.get("/pets/{pet_id}/calls")
def pet_calls(pet_id: str, request: Request, limit: int = 50,
              principal: AdminPrincipal = Depends(needs(Permission.PROVIDER_READ))) -> dict:
    """单只宠物的平台调用账。和 `/economy/ledger?pet_id=` 是两本账，权限也分开（provider.read / economy.read）。"""
    services = admin_of(request)
    if services.directory.pet_brief(pet_id) is None:
        raise AdminAPIError.not_found("这只宠物")
    return services.overview.pet_calls(pet_id, limit=limit)


@router.get("/economy/ledger")
def economy_ledger(request: Request, pet_id: str | None = None, user_id: str | None = None, limit: int = 50,
                   principal: AdminPrincipal = Depends(needs(Permission.ECONOMY_READ))) -> dict:
    return admin_of(request).overview.economy_ledger(pet_id=pet_id, user_id=user_id, limit=limit)


@router.get("/economy/checks")
def economy_checks(request: Request, principal: AdminPrincipal = Depends(needs(Permission.ECONOMY_READ))) -> dict:
    """游戏经济只读对账（判据与 PetEconomyEngine.rebuild_derived_state 同口径）。只报不修，没有任何写。"""
    return admin_of(request).economy_checks.run()


@router.get("/switches")
def switches(request: Request, principal: AdminPrincipal = Depends(needs(Permission.OPS_READ))) -> dict:
    return {"switches": [asdict(s) for s in admin_of(request).switches.all()]}


@router.post("/switches/ai_calls")
def set_ai_calls(body: SwitchRequest, request: Request,
                 principal: AdminPrincipal = Depends(needs(Permission.PROVIDER_PAUSE, write=True))) -> dict:
    services = admin_of(request)
    return services.commands.set_ai_calls(context(request, principal), state=body.state, reason=body.reason,
                                          expected_version=body.expected_version)
