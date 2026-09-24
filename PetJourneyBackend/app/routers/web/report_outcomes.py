"""玩家侧：举报人看自己的举报结果（/api/v1/web/reports/mine）。

这是运营后台「回复处理结果」的**消费端**（方案 §3 社区审核与客服）。只给举报人本人看自己提交过的举报；
措辞固定：还没处理是「已收到」，处理后只有三种结局（已下架 / 没有发现问题 / 复核后恢复）；
**不含**员工身份、内部处理原因，也不含被举报内容本身。
结局的算法与后台队列判断「是否已处理」同一个口径（见 `app/web_admin/moderation.py`）。

纯读：不写任何表、不推进世界、不调模型。后台的表没迁移好时如实回 503 NOT_CONFIGURED——
查不到处理记录不等于「还没处理」，不拿「已收到」顶上。

归属说明（与 announcements.py 相同，如实记）：本文件由运营后台窗口 adm1 新增，由 `install_admin_platform` 挂载，
尚未登记进 `app/routers/web/__init__.py`（共享入口，归 I）。响应 DTO 由 I 按本文件与 `reporter_outcomes` 的返回构造
补进了共享契约（`app/schemas/web/moderation.py` 的 `MyReports`，2026-09-24），这里挂上 `response_model`。
玩家端怎么展示这些回执，归玩家 UI 负责人。
"""

from __future__ import annotations

from fastapi import Depends, Request

from ...schemas.web.common import Capability, CapabilityStatus
from ...schemas.web.moderation import MyReports
from ...web_platform import WebAPIError, WebPrincipal, require_principal
from ._shared import cap, web_router

router = web_router("report_outcomes")


def capabilities(settings) -> list[Capability]:
    return [cap("social.report_outcomes", "web_admin", CapabilityStatus.available,
                "举报人查看自己举报的处理结果（固定措辞，不含员工身份与内部原因）")]


@router.get("/reports/mine", response_model=MyReports)
def my_reports(request: Request, principal: WebPrincipal = Depends(require_principal)) -> dict:
    admin = getattr(request.app.state, "admin", None)
    if admin is None or not admin.tables_ready:
        raise WebAPIError.capability_unavailable("social.report_outcomes", CapabilityStatus.not_configured)
    reports = admin.moderation.reporter_outcomes(principal.user_id)
    return {"reports": reports,
            "note": "这里只有你自己提交的举报。处理结果只说结局，不透露是谁处理的、内部怎么判断的。"}
