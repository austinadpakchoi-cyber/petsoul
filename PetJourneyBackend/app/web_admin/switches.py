"""受控开关：目前只有一个 —— 是否允许**新增**付费调用。

语义严格限定：`ai_calls = paused` 只让还没发出的调用不再发出（供应商计量层直接拒绝，等同"到了上限"，
本地额度按 not_sent 退回）。它**不撤回在途调用**，**不改已经记下的用量和 unknown**，也**不影响游戏经济**。
恢复就是把开关改回 active，不补发任何被挡下的调用。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow

AI_CALLS = "ai_calls"
STATES = {AI_CALLS: ("active", "paused")}
DEFAULTS = {AI_CALLS: "active"}
CACHE_SECONDS = 1.0  # 供应商计量层每次调用都要问一次，给一个很短的缓存，避免每张图都打一次库


@dataclass(frozen=True, slots=True)
class SwitchState:
    key: str
    state: str
    reason: str | None
    version: int
    changed_at: datetime | None
    changed_by: str | None


class SwitchStore:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage
        self._cache: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> SwitchState:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM admin_switches WHERE switch_key = ?", (key,)).fetchone()
        if row is None:
            return SwitchState(key=key, state=DEFAULTS.get(key, "active"), reason=None, version=0, changed_at=None, changed_by=None)
        return SwitchState(key=row["switch_key"], state=row["state"], reason=row["reason"], version=int(row["version"]),
                           changed_at=parse_dt(row["changed_at"]), changed_by=row["changed_by"])

    def all(self) -> list[SwitchState]:
        return [self.get(key) for key in STATES]

    def state_cached(self, key: str) -> str:
        """给热路径（供应商计量）用：最多 1 秒的缓存。读不到库时按默认值放行，不把后台故障变成全站停摆。"""
        import time
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None and now - hit[0] < CACHE_SECONDS:
                return hit[1]
        try:
            state = self.get(key).state
        except Exception:  # noqa: BLE001 - 迁移未应用或库忙：按默认值，不影响玩家
            state = DEFAULTS.get(key, "active")
        with self._lock:
            self._cache[key] = (now, state)
        return state

    def set(self, key: str, state: str, *, reason: str, actor: str, expected_version: int | None,
            audit, audit_kwargs: dict[str, Any]) -> SwitchState:
        """改开关与写审计在同一个写事务里。expected_version 为 None 表示"当前还没有这条记录"。"""
        from .errors import AdminAPIError
        allowed = STATES.get(key)
        if allowed is None:
            raise AdminAPIError.not_found("这个开关")
        if state not in allowed:
            raise AdminAPIError.validation(f"{key} 只能是 {' / '.join(allowed)}。", field="state")
        now = iso(utcnow())
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT version, state FROM admin_switches WHERE switch_key = ?", (key,)).fetchone()
            current_version = int(row["version"]) if row else 0
            if expected_version is not None and expected_version != current_version:
                raise AdminAPIError.version_conflict(expected_version, current_version)
            conn.execute(
                "INSERT INTO admin_switches (switch_key, state, reason, version, changed_at, changed_by) VALUES (?, ?, ?, 1, ?, ?) "
                "ON CONFLICT(switch_key) DO UPDATE SET state = excluded.state, reason = excluded.reason, version = admin_switches.version + 1, "
                "changed_at = excluded.changed_at, changed_by = excluded.changed_by",
                (key, state, reason, now, actor),
            )
            new_version = int(conn.execute("SELECT version FROM admin_switches WHERE switch_key = ?", (key,)).fetchone()["version"])
            audit.record_in(conn, status="succeeded", outcome=state,
                            changes={"switch": key, "from": (row["state"] if row else DEFAULTS.get(key)), "to": state,
                                     "version": new_version}, **audit_kwargs)
        with self._lock:
            self._cache.pop(key, None)
        return self.get(key)
