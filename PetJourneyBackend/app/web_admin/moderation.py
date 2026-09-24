"""举报认领与处理回执（方案 §3「社区审核与客服：举报分派……回复处理结果」）。

**认领**：按被举报的内容（target）记，同一时刻最多一位审核员；认领 30 分钟后自动过期，过期之后别人可以接手。
认领了的内容，别人不能下架 / 恢复 / 记为不处理（`AdminCommands.moderate` 在同一个写事务里核）；处理完认领自动结束。

**回执**：举报人只看自己的举报与结果，措辞固定：没处理是「已收到」，处理后只有三种结局——不含员工身份、不含内部处理原因、不含被举报内容本身。
结局按「这条举报提交之后，这条内容上最近一次处理」算，和后台队列判断「是否已处理」是同一个口径。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from ..web_platform.uow import unit_of_work
from .audit import AuditLog
from .commands import ActorContext
from .errors import AdminAPIError, AdminErrorCode
from .permissions import Permission

CLAIM_TTL = timedelta(minutes=30)
TARGET_KINDS = ("post", "comment")

# 举报人看到的结局（码 → 默认措辞）。玩家端可以按码换成自己的文案，但不能多给信息。
OUTCOMES = {
    None: ("received", "已收到，运营同学会尽快查看。"),
    "takedown": ("content_removed", "已处理：这条内容已不再公开展示。"),
    "dismiss": ("no_violation_found", "已处理：查看后没有发现需要处理的问题。"),
    "restore": ("content_restored", "已处理：复核后这条内容恢复公开展示。"),
}


def active_claim(conn: sqlite3.Connection, target_kind: str, target_id: str, now: datetime) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT c.staff_id, c.claimed_at, c.expires_at, s.username FROM admin_report_claims c "
        "LEFT JOIN admin_staff s ON s.staff_id = c.staff_id WHERE c.target_kind = ? AND c.target_id = ?",
        (target_kind, target_id)).fetchone()
    if row is None or parse_dt(row["expires_at"]) <= now:
        return None
    return {"staff_id": row["staff_id"], "username": row["username"], "claimed_at": parse_dt(row["claimed_at"]),
            "expires_at": parse_dt(row["expires_at"])}


def claimed_by_other(claim: dict[str, Any]) -> AdminAPIError:
    until = claim["expires_at"].strftime("%H:%M UTC")
    return AdminAPIError(AdminErrorCode.conflict, f"这条内容由 {claim['username'] or claim['staff_id']} 认领处理中（到 {until}）。",
                         409, details={"reason": "claimed_by_other", "claimed_by": claim["username"],
                                       "expires_at": iso(claim["expires_at"])})


class AdminModeration:
    def __init__(self, storage: JourneyStorage, audit: AuditLog) -> None:
        self.storage = storage
        self.audit = audit

    def _check_target(self, target_kind: str, target_id: str) -> None:
        if target_kind not in TARGET_KINDS:
            raise AdminAPIError.validation("只支持处理公开动态（post）与评论（comment）。", field="target_kind")
        with self.storage.connect() as conn:
            if conn.execute("SELECT 1 FROM web_reports WHERE target_kind = ? AND target_id = ?", (target_kind, target_id)).fetchone() is None:
                raise AdminAPIError.not_found("这条被举报的内容")

    def claim(self, ctx: ActorContext, target_kind: str, target_id: str) -> dict[str, Any]:
        """认领；自己再认领一次＝续期。别人认领着就 409（说清是谁、到几点）；过期的可以接手，审计里记下接手了谁的。"""
        self._check_target(target_kind, target_id)
        now = utcnow()
        with unit_of_work(self.storage) as conn:
            current = active_claim(conn, target_kind, target_id, now)
            if current is not None and current["staff_id"] != ctx.staff_id:
                raise claimed_by_other(current)
            previous = conn.execute("SELECT staff_id FROM admin_report_claims WHERE target_kind = ? AND target_id = ?",
                                    (target_kind, target_id)).fetchone()
            expires = now + CLAIM_TTL
            conn.execute(
                "INSERT INTO admin_report_claims (target_kind, target_id, staff_id, claimed_at, expires_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(target_kind, target_id) DO UPDATE SET staff_id = excluded.staff_id, claimed_at = excluded.claimed_at, "
                "expires_at = excluded.expires_at", (target_kind, target_id, ctx.staff_id, iso(now), iso(expires)))
            took_over = previous["staff_id"] if previous and previous["staff_id"] != ctx.staff_id else None
            outcome = "renewed" if current is not None else ("took_over_expired" if took_over else "claimed")
            self.audit.record_in(conn, action="report.claim", status="succeeded", outcome=outcome,
                                 permission=Permission.REPORT_ACTION.value, actor_staff_id=ctx.staff_id,
                                 actor_username=ctx.username, target_kind=target_kind, target_id=target_id,
                                 reason=None, operation_id=ctx.operation_id, request_id=ctx.request_id,
                                 changes={"expires_at": iso(expires), "took_over_from": took_over})
        return {"target_kind": target_kind, "target_id": target_id, "claimed_by": ctx.username, "expires_at": expires,
                "outcome": outcome, "note": f"认领到 {expires.strftime('%H:%M')} UTC；处理完会自动结束，走开了过期后别人可以接手。"}

    def release(self, ctx: ActorContext, target_kind: str, target_id: str) -> dict[str, Any]:
        """放弃认领：只有认领人自己能放；已经过期或没人认领的，放不放都一样（如实回 released=false）。"""
        now = utcnow()
        with unit_of_work(self.storage) as conn:
            current = active_claim(conn, target_kind, target_id, now)
            if current is not None and current["staff_id"] != ctx.staff_id:
                raise claimed_by_other(current)
            released = conn.execute("DELETE FROM admin_report_claims WHERE target_kind = ? AND target_id = ?",
                                    (target_kind, target_id)).rowcount > 0 and current is not None
            self.audit.record_in(conn, action="report.release", status="succeeded", outcome="released" if released else "nothing_to_release",
                                 permission=Permission.REPORT_ACTION.value, actor_staff_id=ctx.staff_id,
                                 actor_username=ctx.username, target_kind=target_kind, target_id=target_id,
                                 reason=None, operation_id=ctx.operation_id, request_id=ctx.request_id, changes=None)
        return {"target_kind": target_kind, "target_id": target_id, "released": released}

    # ---- 举报人看的回执（玩家侧只读）----
    def reporter_outcomes(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.storage.connect() as conn:
            reports = conn.execute("SELECT report_id, target_kind, target_id, reason, created_at FROM web_reports "
                                   "WHERE reporter_user_id = ? ORDER BY created_at DESC LIMIT ?",
                                   (user_id, max(1, min(100, limit)))).fetchall()
            out = []
            for report in reports:
                action = conn.execute(
                    "SELECT decision, created_at FROM admin_report_actions WHERE target_kind = ? AND target_id = ? AND created_at >= ? "
                    "ORDER BY created_at DESC, rowid DESC LIMIT 1",
                    (report["target_kind"], report["target_id"], report["created_at"])).fetchone()
                code, message = OUTCOMES[action["decision"] if action else None]
                out.append({"report_id": report["report_id"], "target_kind": report["target_kind"],
                            "target_id": report["target_id"], "reason": report["reason"],
                            "created_at": parse_dt(report["created_at"]),
                            "status": "resolved" if action else "received", "outcome": code,
                            "resolved_at": parse_dt(action["created_at"]) if action else None, "message": message})
        return out
