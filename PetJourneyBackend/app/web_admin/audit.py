"""管理操作审计：仅追加，业务写入与审计在**同一个事务**里提交。

两个入口，用途不同，不要混：
- `record_in(conn, ...)`：调用方已经在写事务里（`unit_of_work` 或自己 BEGIN IMMEDIATE）。业务改动回滚，
  这条审计也一起回滚 —— "记了审计但业务没生效"和"业务生效了却没审计"都不会出现；
- `record(...)`：没有业务事务可挂靠时用（登录、被拒绝的请求、只读访问留痕）。自己开一条短事务。

写进去的东西：谁（staff_id / username）、凭哪条权限、对什么对象、为什么、结果、操作号、请求号、
脱敏后的变更摘要。**不记**口令、密钥、私聊正文、原始提示词；`redact` 负责把这些挡在门外。
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow

# 值一律不进审计的字段名（子串匹配，大小写不敏感）。
_FORBIDDEN = ("password", "secret", "token", "api_key", "apikey", "mfa", "prompt", "message_text", "note_text", "private")
_MAX_VALUE = 200


def redact(payload: Any) -> Any:
    """只保留可安全留痕的摘要：敏感键名换成 '[已省略]'，长文本截断，不做深拷贝以外的加工。"""
    if isinstance(payload, dict):
        cleaned: dict[str, Any] = {}
        for key, value in payload.items():
            if any(bad in str(key).lower() for bad in _FORBIDDEN):
                cleaned[str(key)] = "[已省略]"
            else:
                cleaned[str(key)] = redact(value)
        return cleaned
    if isinstance(payload, (list, tuple)):
        return [redact(item) for item in payload][:50]
    if isinstance(payload, str):
        return payload if len(payload) <= _MAX_VALUE else payload[:_MAX_VALUE] + "…"
    return payload


@dataclass(frozen=True, slots=True)
class AuditEntry:
    audit_id: str
    occurred_at: datetime
    actor_staff_id: str | None
    actor_username: str | None
    action: str
    permission: str | None
    target_kind: str | None
    target_id: str | None
    reason: str | None
    status: str
    outcome: str | None
    operation_id: str | None
    request_id: str | None
    changes: dict | None


class AuditLog:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage

    def record_in(self, conn: sqlite3.Connection, *, action: str, status: str, actor_staff_id: str | None = None,
                  actor_username: str | None = None, permission: str | None = None, target_kind: str | None = None,
                  target_id: str | None = None, reason: str | None = None, outcome: str | None = None,
                  operation_id: str | None = None, request_id: str | None = None, changes: Any = None,
                  now: datetime | None = None) -> str:
        audit_id = f"AU-{uuid.uuid4().hex[:16]}"
        conn.execute(
            "INSERT INTO admin_audit (audit_id, occurred_at, actor_staff_id, actor_username, action, permission, target_kind, target_id, "
            "reason, status, outcome, operation_id, request_id, changes_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (audit_id, iso(now or utcnow()), actor_staff_id, actor_username, action, permission, target_kind, target_id,
             (reason or None), status, outcome, operation_id, request_id,
             json.dumps(redact(changes), ensure_ascii=False) if changes is not None else None),
        )
        return audit_id

    def record(self, **kwargs) -> str:
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            return self.record_in(conn, **kwargs)

    def query(self, *, actor: str | None = None, action: str | None = None, target_kind: str | None = None,
              target_id: str | None = None, status: str | None = None, since: datetime | None = None,
              limit: int = 50, offset: int = 0) -> tuple[list[AuditEntry], int]:
        where: list[str] = []
        params: list[Any] = []
        if actor:
            where.append("(actor_staff_id = ? OR actor_username = ?)")
            params += [actor, actor]
        if action:
            where.append("action LIKE ?")
            params.append(f"{action}%")
        if target_kind:
            where.append("target_kind = ?")
            params.append(target_kind)
        if target_id:
            where.append("target_id = ?")
            params.append(target_id)
        if status:
            where.append("status = ?")
            params.append(status)
        if since:
            where.append("occurred_at >= ?")
            params.append(iso(since))
        clause = f" WHERE {' AND '.join(where)}" if where else ""
        with self.storage.connect() as conn:
            total = conn.execute(f"SELECT COUNT(*) AS n FROM admin_audit{clause}", params).fetchone()["n"]
            rows = conn.execute(
                f"SELECT * FROM admin_audit{clause} ORDER BY occurred_at DESC, rowid DESC LIMIT ? OFFSET ?",
                [*params, max(1, min(200, limit)), max(0, offset)],
            ).fetchall()
        return [_entry(row) for row in rows], int(total)

    def recent_for_target(self, target_kind: str, target_id: str, limit: int = 20) -> list[AuditEntry]:
        entries, _ = self.query(target_kind=target_kind, target_id=target_id, limit=limit)
        return entries


def _entry(row) -> AuditEntry:
    return AuditEntry(
        audit_id=row["audit_id"], occurred_at=parse_dt(row["occurred_at"]), actor_staff_id=row["actor_staff_id"],
        actor_username=row["actor_username"], action=row["action"], permission=row["permission"],
        target_kind=row["target_kind"], target_id=row["target_id"], reason=row["reason"], status=row["status"],
        outcome=row["outcome"], operation_id=row["operation_id"], request_id=row["request_id"],
        changes=json.loads(row["changes_json"]) if row["changes_json"] else None,
    )


def actions_of(entries: Iterable[AuditEntry]) -> list[str]:
    return sorted({entry.action for entry in entries})
