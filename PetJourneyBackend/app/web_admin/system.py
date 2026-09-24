"""系统运行（方案 §3「系统运营：看环境/版本、任务线、到期延迟、供应商健康、限额、开关与备份状态」）。

只读既有表，不推进世界、不重试任何东西、不改任何状态：
- **事件投递**（`web_outbox`）：按去处看待投递多少、最老的一条等了多久、正在反复失败的是哪几条；
- **后台执行者**（`web_worker_leases`）：世界推进 / AI 思考两条线现在谁在跑、最后一次心跳、最后一次成功与错误；
- **任务线**（`web_tasks`）：按种类与状态计数、到期还没执行的有多少、最近的失败；
- **迁移版本**（`web_schema_migrations`）：一共应用了多少条、最新是哪几条；
- **供应商健康**（`web_provider_health`）与 **AI 新增调用开关**；
- **备份**：这套环境里没有可读的备份记录，就如实说「未接入」，**不显示「正常」**。

「API 在线」不代表执行者正常（方案原话）：所以执行者单列，租约过期就标出来。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from ..storage import JourneyStorage
from .lanes import LANE_NAMES, lane_state, runner_configured
from ..utils import parse_dt, utcnow

RECENT_LIMIT = 10


def _dt(value: str | None) -> datetime | None:
    return parse_dt(value) if value else None


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row] | None:
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return None  # 表还不在：查不了 ≠ 没有


class AdminSystem:
    def __init__(self, storage: JourneyStorage, *, switches, environment) -> None:
        self.storage = storage
        self.switches = switches
        self.environment = environment  # 可调用：返回环境与版本（与运营首页同一个来源）

    def status(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or utcnow()
        env = self.environment()
        configured = runner_configured(env.get("world_runner"), env.get("world_tick_seconds"))
        with self.storage.connect() as conn:
            return {
                "as_of": now,
                "environment": env,
                "world_configured": configured,
                "outbox": self._outbox(conn, now),
                "workers": self._workers(conn, now, configured),
                "tasks": self._tasks(conn, now),
                "migrations": self._migrations(conn),
                "providers": self._providers(conn),
                "switches": [{"key": s.key, "state": s.state, "reason": s.reason, "changed_at": s.changed_at,
                              "changed_by": s.changed_by} for s in self.switches.all()],
                "backups": {"available": False,
                            "note": "这套环境没有可读的备份记录，备份状态还没有接入。这里不显示「正常」——没有来源就是未知。"},
            }

    def _outbox(self, conn, now: datetime) -> dict[str, Any] | None:
        grouped = _rows(conn, "SELECT consumer, status, COUNT(*) AS n, MIN(created_at) AS oldest FROM web_outbox GROUP BY consumer, status")
        if grouped is None:
            return None
        consumers: dict[str, dict[str, Any]] = {}
        for row in grouped:
            entry = consumers.setdefault(row["consumer"], {"consumer": row["consumer"], "pending": 0, "delivered": 0, "dead_letter": 0,
                                                          "other": 0, "oldest_pending_at": None})
            if row["status"] == "pending":
                entry["pending"] = int(row["n"])
                entry["oldest_pending_at"] = _dt(row["oldest"])
            elif row["status"] == "delivered":
                entry["delivered"] = int(row["n"])
            elif row["status"] == "dead_letter":  # 试满次数、已放弃：不会再自动投递，要单独看见
                entry["dead_letter"] = int(row["n"])
            else:
                entry["other"] += int(row["n"])
        failing = conn.execute(
            "SELECT consumer, kind, attempts, next_attempt_at, last_error, created_at FROM web_outbox "
            "WHERE status = 'pending' AND last_error IS NOT NULL ORDER BY seq LIMIT ?", (RECENT_LIMIT,)).fetchall()
        dead = conn.execute(
            "SELECT consumer, kind, attempts, last_error, created_at FROM web_outbox "
            "WHERE status = 'dead_letter' ORDER BY seq DESC LIMIT ?", (RECENT_LIMIT,)).fetchall()
        return {"consumers": sorted(consumers.values(), key=lambda c: (-c["dead_letter"], -c["pending"], c["consumer"])),
                "pending_total": sum(c["pending"] for c in consumers.values()),
                "dead_total": sum(c["dead_letter"] for c in consumers.values()),
                "dead": [{"consumer": r["consumer"], "kind": r["kind"], "attempts": int(r["attempts"] or 0),
                          "last_error": r["last_error"], "created_at": _dt(r["created_at"])} for r in dead],
                "failing": [{"consumer": r["consumer"], "kind": r["kind"], "attempts": int(r["attempts"] or 0),
                             "next_attempt_at": _dt(r["next_attempt_at"]), "last_error": r["last_error"],
                             "created_at": _dt(r["created_at"])} for r in failing]}

    def _workers(self, conn, now: datetime, configured: bool) -> list[dict] | None:
        """两条线都列出来（没登记的也列，按配置判是「关着」还是「失联」）；状态按配置判，见 lanes.py。"""
        rows = _rows(conn, "SELECT name, role, holder, host, pid, started_at, heartbeat_at, expires_at, last_tick_at, last_ok_at, "
                           "last_error, ticks FROM web_worker_leases ORDER BY name")
        if rows is None:
            return None
        by_name = {r["name"]: r for r in rows}
        out = []
        for name in sorted(set(LANE_NAMES) | set(by_name)):
            r = by_name.get(name)
            alive = bool(r is not None and r["expires_at"] and parse_dt(r["expires_at"]) > now)
            out.append({"name": name, "registered": r is not None, "state": lane_state(configured, alive), "alive": alive,
                        "role": r["role"] if r else None, "holder": r["holder"] if r else None, "host": r["host"] if r else None,
                        "pid": r["pid"] if r else None, "started_at": _dt(r["started_at"]) if r else None,
                        "heartbeat_at": _dt(r["heartbeat_at"]) if r else None, "expires_at": _dt(r["expires_at"]) if r else None,
                        "last_tick_at": _dt(r["last_tick_at"]) if r else None, "last_ok_at": _dt(r["last_ok_at"]) if r else None,
                        "last_error": r["last_error"] if r else None, "ticks": int(r["ticks"] or 0) if r else 0})
        return out

    def _tasks(self, conn, now: datetime) -> dict[str, Any] | None:
        grouped = _rows(conn, "SELECT kind, status, COUNT(*) AS n FROM web_tasks GROUP BY kind, status ORDER BY kind, status")
        if grouped is None:
            return None
        from ..utils import iso
        overdue = conn.execute("SELECT kind, COUNT(*) AS n, MIN(run_after) AS oldest FROM web_tasks "
                               "WHERE status = 'queued' AND run_after <= ? GROUP BY kind", (iso(now),)).fetchall()
        failures = conn.execute("SELECT kind, last_error, attempts, max_attempts, updated_at FROM web_tasks WHERE status = 'failed' "
                                "ORDER BY updated_at DESC LIMIT ?", (RECENT_LIMIT,)).fetchall()
        return {"counts": [{"kind": r["kind"], "status": r["status"], "count": int(r["n"])} for r in grouped],
                "overdue": [{"kind": r["kind"], "count": int(r["n"]), "oldest_run_after": _dt(r["oldest"])} for r in overdue],
                "recent_failures": [{"kind": r["kind"], "last_error": r["last_error"], "attempts": int(r["attempts"] or 0),
                                     "max_attempts": int(r["max_attempts"] or 0), "updated_at": _dt(r["updated_at"])} for r in failures]}

    def _migrations(self, conn) -> dict[str, Any] | None:
        rows = _rows(conn, "SELECT migration_id, module, description, applied_at FROM web_schema_migrations ORDER BY applied_at DESC, rowid DESC")
        if rows is None:
            return None
        return {"count": len(rows),
                "latest": [{"migration_id": r["migration_id"], "module": r["module"], "description": r["description"],
                            "applied_at": _dt(r["applied_at"])} for r in rows[:5]]}

    def _providers(self, conn) -> list[dict] | None:
        rows = _rows(conn, "SELECT provider, last_success_at, last_failure_at, last_error, updated_at FROM web_provider_health ORDER BY provider")
        if rows is None:
            return None
        return [{"provider": r["provider"], "last_success_at": _dt(r["last_success_at"]), "last_failure_at": _dt(r["last_failure_at"]),
                 "last_error": r["last_error"], "updated_at": _dt(r["updated_at"])} for r in rows]
