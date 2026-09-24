"""批量游戏补偿：能力状态 → 影响预览 → 提交 → 审批（另一个人）→ 执行。

额度没配置时**每一个**入口都回 503 NOT_CONFIGURED（连预览都不给），
因为"能算出要发多少钱"本身就已经是在用这项能力了。
"""

from __future__ import annotations

from fastapi import Depends, Request

from ...schemas.admin import BatchDecisionRequest, BatchExecuteRequest, BatchPreviewRequest, BatchSubmitRequest
from ...web_admin.identity import AdminPrincipal
from ...web_admin.permissions import Permission
from ._shared import admin_of, admin_router, context, needs

router = admin_router("batches")


@router.get("/economy/batches/capability")
def capability(request: Request, principal: AdminPrincipal = Depends(needs(Permission.ECONOMY_READ))) -> dict:
    """额度配了没有、上限是多少。**没配就如实说关着**，不显示一个假的默认额度。"""
    return admin_of(request).batches.capability()


@router.get("/economy/batches")
def list_batches(request: Request, limit: int = 50,
                 principal: AdminPrincipal = Depends(needs(Permission.ECONOMY_READ))) -> dict:
    services = admin_of(request)
    return {"batches": services.batches.list_batches(limit), "capability": services.batches.capability()}


@router.get("/economy/batches/{batch_id}")
def batch_detail(batch_id: str, request: Request,
                 principal: AdminPrincipal = Depends(needs(Permission.ECONOMY_READ))) -> dict:
    return admin_of(request).batches.get(batch_id)


@router.post("/economy/batches/preview")
def preview(body: BatchPreviewRequest, request: Request,
            principal: AdminPrincipal = Depends(needs(Permission.ECONOMY_GRANT_BATCH, write=True))) -> dict:
    """纯读：算影响，不写任何东西。放 POST 是因为名单可能很长，不该塞进查询串。"""
    return admin_of(request).batches.preview(body.pet_ids, body.amount_per_pet, body.player_note)


@router.post("/economy/batches", status_code=201)
def submit(body: BatchSubmitRequest, request: Request,
           principal: AdminPrincipal = Depends(needs(Permission.ECONOMY_GRANT_BATCH, write=True))) -> dict:
    services = admin_of(request)
    return services.batches.submit(context(request, principal), title=body.title, reason=body.reason,
                                   amount_per_pet=body.amount_per_pet, pet_ids=body.pet_ids, player_note=body.player_note)


@router.post("/economy/batches/{batch_id}/decision")
def decide(batch_id: str, body: BatchDecisionRequest, request: Request,
           principal: AdminPrincipal = Depends(needs(Permission.ECONOMY_APPROVE, write=True))) -> dict:
    services = admin_of(request)
    return services.batches.decide(context(request, principal), batch_id, approve=body.approve,
                                   note=body.note, expected_version=body.expected_version)


@router.post("/economy/batches/{batch_id}/execute")
def execute(batch_id: str, body: BatchExecuteRequest, request: Request,
            principal: AdminPrincipal = Depends(needs(Permission.ECONOMY_GRANT_BATCH, write=True))) -> dict:
    services = admin_of(request)
    return services.batches.execute(context(request, principal), batch_id, expected_version=body.expected_version,
                                    note=body.note)
