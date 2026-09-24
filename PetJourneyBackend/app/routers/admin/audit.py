"""审计查询：谁、凭哪条权限、对什么、为什么、结果。仅追加，后台没有任何删改入口。"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from fastapi import Depends, Request

from ...web_admin.identity import AdminPrincipal
from ...web_admin.permissions import Permission
from ._shared import admin_of, admin_router, needs

router = admin_router("audit")


@router.get("/audit")
def query(request: Request, actor: str | None = None, action: str | None = None, target_kind: str | None = None,
          target_id: str | None = None, status: str | None = None, since: datetime | None = None,
          limit: int = 50, offset: int = 0,
          principal: AdminPrincipal = Depends(needs(Permission.AUDIT_READ))) -> dict:
    entries, total = admin_of(request).audit.query(actor=actor, action=action, target_kind=target_kind,
                                                   target_id=target_id, status=status, since=since,
                                                   limit=limit, offset=offset)
    return {"entries": [asdict(e) for e in entries], "total": total, "limit": limit, "offset": offset,
            "note": "审计仅追加（数据库触发器挡住 UPDATE / DELETE）。同一个 SQLite 文件内的触发器不是防篡改证明，"
                    "要不可抵赖需要独立留存与异地备份。"}
