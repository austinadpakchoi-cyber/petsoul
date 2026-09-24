"""宠物运行总览、暂停与恢复、每天生了多少张图（第九批）。

- 总览只读已记下的事实，不评估心跳、不推进世界、不调模型；钱袋子要 economy.read，AI 用量要 provider.read，各段各给。
- 暂停 / 恢复有权限、原因、版本、幂等与审计；在各条运行线都认暂停之前不开放（见 web_admin/pet_runtime.py 的 PAUSE_OPEN）。
"""

from __future__ import annotations

from fastapi import Depends, Request

from ...schemas.admin import PetPauseRequest
from ...utils import utcnow
from ...web_admin.identity import AdminPrincipal
from ...web_admin.permissions import Permission
from ...web_admin.usage_daily import image_days
from ._shared import admin_of, admin_router, context, needs, trace_read

router = admin_router("runtime")


@router.get("/pets-runtime")
def pets_runtime(request: Request, pet_id: str | None = None,
                 principal: AdminPrincipal = Depends(needs(Permission.PET_READ))) -> dict:
    wallets = principal.has(Permission.ECONOMY_READ)
    usage = principal.has(Permission.PROVIDER_READ)
    result = admin_of(request).pet_runtime.overview(wallets=wallets, usage=usage, pet_id=pet_id)
    trace_read(request, principal, Permission.PET_READ, "pet.runtime_list", "pet" if pet_id else "pets", pet_id or "all",
               count=len(result["pets"]),
               sections=["runtime"] + (["wallets"] if wallets else []) + (["usage"] if usage else []))
    return result


@router.get("/pets/{pet_id}/pause/preview")
def pause_preview(pet_id: str, request: Request, principal: AdminPrincipal = Depends(needs(Permission.PET_MAINTAIN))) -> dict:
    return admin_of(request).pet_runtime.pause_preview(pet_id)


@router.post("/pets/{pet_id}/pause")
def set_pause(pet_id: str, body: PetPauseRequest, request: Request,
              principal: AdminPrincipal = Depends(needs(Permission.PET_MAINTAIN, write=True))) -> dict:
    return admin_of(request).pet_runtime.set_paused(context(request, principal), pet_id, paused=body.paused, reason=body.reason,
                                                    expected_version=body.expected_version)


@router.get("/usage/images-daily")
def images_daily(request: Request, days: int = 30, principal: AdminPrincipal = Depends(needs(Permission.PROVIDER_READ))) -> dict:
    """平台用量（不是个人数据），和平台成本页一样不写访问审计。"""
    services = admin_of(request)
    return image_days(services.pet_runtime.storage, services.pet_runtime.settings, utcnow(), days=max(1, min(int(days), 90)))
