"""举报队列与公开内容的下架 / 恢复 / 不处理。

只处理**公开**内容（星球圈动态与评论）。私聊、私人叮嘱不在举报范围，也取不到正文。
下架只改可见性，举报记录、原文与审计依据都保留，不做硬删除。
"""

from __future__ import annotations

from fastapi import Depends, Request

from ...schemas.admin import ModerationRequest, ReportClaimRequest
from ...web_admin.identity import AdminPrincipal
from ...web_admin.permissions import Permission
from ...web_admin.social import people
from ._shared import admin_of, admin_router, context, needs, trace_read

router = admin_router("moderation")


@router.get("/reports")
def reports(request: Request, only_open: bool = True, limit: int = 50,
            principal: AdminPrincipal = Depends(needs(Permission.REPORT_READ))) -> dict:
    services = admin_of(request)
    rows = services.overview.reports(only_open=only_open, limit=limit)
    # 关系上下文：被举报的是谁、两人之间有没有拉黑、这个人被举报过几次、被下架过几次、举报人一共举报过几次（只给计数）
    with services.social.storage.connect() as conn:
        reporters = people(conn, [row["reporter_user_id"] for row in rows])
        for row in rows:
            row["reporter_name"] = reporters.get(row["reporter_user_id"])  # 举报人写名字，不只给编号
            row["context"] = services.social.report_context(conn, row["reporter_user_id"], row["target_kind"], row["target_id"])
    for row in rows:  # 认领是谁的：后台只按员工号判「是不是我」，不把别人的员工号当权限依据
        claim = row.get("claim")
        if claim is not None:
            claim["mine"] = claim.pop("staff_id") == principal.staff.staff_id
    trace_read(request, principal, Permission.REPORT_READ, "report.list", "queue", "reports", count=len(rows),
               only_open=only_open)
    return {"reports": rows, "only_open": only_open,
            "note": "只展示举报目标的公开内容；私聊与私人叮嘱不进这个队列。"}


@router.get("/moderation/preview")
def preview(request: Request, target_kind: str, target_id: str,
            principal: AdminPrincipal = Depends(needs(Permission.REPORT_ACTION))) -> dict:
    return admin_of(request).commands.moderation_preview(target_kind, target_id)


@router.post("/moderation")
def moderate(body: ModerationRequest, request: Request,
             principal: AdminPrincipal = Depends(needs(Permission.REPORT_ACTION, write=True))) -> dict:
    services = admin_of(request)
    return services.commands.moderate(context(request, principal), report_id=body.report_id, target_kind=body.target_kind,
                                      target_id=body.target_id, decision=body.decision, reason=body.reason)


@router.post("/reports/claim")
def claim(body: ReportClaimRequest, request: Request,
          principal: AdminPrincipal = Depends(needs(Permission.REPORT_ACTION, write=True))) -> dict:
    """认领这条被举报的内容（30 分钟，自己再点一次＝续期）。别人认领着就 409，并说清是谁、到几点。"""
    return admin_of(request).moderation.claim(context(request, principal), body.target_kind, body.target_id)


@router.post("/reports/release")
def release(body: ReportClaimRequest, request: Request,
            principal: AdminPrincipal = Depends(needs(Permission.REPORT_ACTION, write=True))) -> dict:
    return admin_of(request).moderation.release(context(request, principal), body.target_kind, body.target_id)
