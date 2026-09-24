"""冲正一笔后台补偿：影响预览 → 写原因与玩家说明 → 冲正。规则见 `app/web_admin/reversals.py`。

预览与执行都要 `economy.reverse`（默认只给经济负责人）；发补偿的经济运营没有这条权限。
"""

from __future__ import annotations

from fastapi import Depends, Request

from ...schemas.admin import ReversalRequest
from ...web_admin.identity import AdminPrincipal
from ...web_admin.permissions import Permission
from ._shared import admin_of, admin_router, context, needs

router = admin_router("reversals")


@router.get("/economy/reversals/preview")
def reversal_preview(request: Request, tx_id: str, player_note: str | None = None,
                     principal: AdminPrincipal = Depends(needs(Permission.ECONOMY_REVERSE))) -> dict:
    """纯读：原补偿是谁发的、为什么发的、现在余额够不够、玩家会看到什么。不写任何东西。"""
    return admin_of(request).reversals.preview(principal.staff.staff_id, tx_id, player_note)


@router.post("/economy/reversals")
def reverse(body: ReversalRequest, request: Request,
            principal: AdminPrincipal = Depends(needs(Permission.ECONOMY_REVERSE, write=True))) -> dict:
    return admin_of(request).reversals.reverse(context(request, principal), body.tx_id, reason=body.reason,
                                               player_note=body.player_note)
