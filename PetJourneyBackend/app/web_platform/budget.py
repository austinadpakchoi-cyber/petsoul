"""运行层操作预算：付费调用（模型、生图、地图等）发出前原子预占，结束后结算。跨进程一致，重启不清零。

两层额度都要过：
- 供应商全局日上限：ProviderMeter.allow()（web_providers/meter.py）在发出 HTTP 前原子预计，所有调用方共用；
- 本模块管操作级：用途 / 宠物 / 家庭的日额度、在途并发数、operation_id 去重、结果不明（unknown）与超时未结算（expired）。
  调用顺序：先 reserve 操作额度，再调用供应商客户端（它内部 allow），最后 settle。

返回运行时内部契约的 BudgetReservation / BudgetDenied（runtime-internal 0.1.0）：
- reserve：所有额度层级在一个写事务里检查并占用，任何一层不够就整体不占。
  同一 operation_id：还在途 → BudgetDenied(reason="in_flight")，调用方不得再发；已结束（settled / unknown / expired）→ 原样返回那条预占，
  状态不是 reserved 就说明不能再发；只有 released（确定没发出）会被重新占用。要重试已发出的调用，用新的 operation_id（例如带尝试序号）。
- settle：succeeded / failed → settled，计入已用；unknown → unknown，保守计入已用，不能当“没花钱”释放后盲目重发；
  not_sent → released，退回额度。unknown 之后查清了可以再结算一次（查实没发出就退回）。
- 预占到期仍未结算（进程死在调用中途）：下一次 reserve 或 expire_stale 把它标为 expired，保守计入已用，并释放并发名额。
- 计费窗口固定 UTC 日；只计“调用单位”，不是金额；星币与真实费用无关，费用未知就保持未知。
- 需要表 web_budget_reservations / web_budget_counters（DDL 由集成窗口编号实施）；表不存在时 reserve 返回 BudgetDenied(ledger_unavailable)。
- 传入 conn 时在调用方事务里执行（调用方须已 BEGIN IMMEDIATE），这里不开始、不提交；调用方回滚则预占一并撤销。
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Callable, Sequence, TypeVar

from ..schemas.runtime_internal import BudgetDenied, BudgetReservation
from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow

DAILY = "daily"  # UTC 日累计（已用 + 在途）
CONCURRENT = "concurrent"  # 在途数量
OUTCOMES = ("succeeded", "failed", "not_sent", "unknown")
INFLIGHT_WINDOW = "inflight"
EXPIRE_BATCH = 50
TABLES = ("web_budget_reservations", "web_budget_counters")
_STATUS_OF = {"succeeded": "settled", "failed": "settled", "unknown": "unknown", "not_sent": "released"}

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class BudgetLimit:
    """一层额度。scope_key 由调用方约定，例如 purpose:brain、pet:<id>:brain、household:<id>、inflight:llm；“usage:” 前缀保留给用量统计。"""

    scope_key: str
    max_units: int
    kind: str = DAILY


class BudgetLedger:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage
        self._ready = False

    def available(self, conn: sqlite3.Connection | None = None) -> bool:
        if not self._ready:
            sql = f"SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name IN ({','.join('?' for _ in TABLES)})"
            self._ready = self._in_tx(conn, lambda c: c.execute(sql, TABLES).fetchone()[0] == len(TABLES), write=False)
        return self._ready

    def reserve(self, operation_id: str, *, provider: str, purpose: str, limits: Sequence[BudgetLimit] = (), units: int = 1,
                subject_scope: str = "global", ttl_seconds: float = 300, now: datetime | None = None,
                conn: sqlite3.Connection | None = None) -> BudgetReservation | BudgetDenied:
        """在所有额度层级里原子占用 units；任何一层不够就整体不占，返回 BudgetDenied。"""
        now = (now or utcnow()).astimezone(timezone.utc)
        if not operation_id or units < 1 or any(limit.kind not in (DAILY, CONCURRENT) or limit.max_units < 0 for limit in limits):
            return BudgetDenied(operation_id, "request", "invalid_request")
        if not self.available(conn):
            return BudgetDenied(operation_id, "ledger", "ledger_unavailable")
        return self._in_tx(conn, lambda c: self._reserve(c, operation_id, provider, purpose, limits, units, subject_scope or "global", ttl_seconds, now))

    def settle(self, reservation: BudgetReservation | str, outcome: str, *, actual_units: int | None = None, provider_request_id: str | None = None,
               now: datetime | None = None, conn: sqlite3.Connection | None = None) -> BudgetReservation:
        """结算一次预占。已结算的重复结算不改计数；unknown 可以在查清后再结算一次。"""
        if outcome not in OUTCOMES:
            raise ValueError(f"unknown budget outcome: {outcome}")
        now = (now or utcnow()).astimezone(timezone.utc)
        reservation_id = reservation if isinstance(reservation, str) else reservation.reservation_id
        return self._in_tx(conn, lambda c: self._settle(c, reservation_id, outcome, actual_units, provider_request_id, now))

    def expire_stale(self, *, now: datetime | None = None, limit: int = 100, conn: sqlite3.Connection | None = None) -> int:
        """把到期仍未结算的预占标为 expired（保守计入已用、释放并发名额）。返回处理条数。"""
        now = (now or utcnow()).astimezone(timezone.utc)
        if not self.available(conn):
            return 0
        return self._in_tx(conn, lambda c: _expire_in_tx(c, now, limit))

    def get(self, operation_id: str) -> BudgetReservation | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_budget_reservations WHERE operation_id = ?", (operation_id,)).fetchone()
        return None if row is None else _reservation(row)

    def usage(self, scope_key: str, *, kind: str = DAILY, now: datetime | None = None) -> dict[str, int]:
        window = INFLIGHT_WINDOW if kind == CONCURRENT else (now or utcnow()).astimezone(timezone.utc).date().isoformat()
        with self.storage.connect() as conn:
            row = conn.execute("SELECT used_units, inflight_units FROM web_budget_counters WHERE window_key = ? AND scope_key = ?",
                               (window, scope_key)).fetchone()
        return {"used": int(row["used_units"]) if row else 0, "inflight": int(row["inflight_units"]) if row else 0}

    # ---- 内部 ----
    def _in_tx(self, conn: sqlite3.Connection | None, work: Callable[[sqlite3.Connection], T], *, write: bool = True) -> T:
        if conn is not None:
            return work(conn)
        with self.storage.connect() as own:
            if write:
                own.execute("BEGIN IMMEDIATE")
            return work(own)

    def _reserve(self, conn: sqlite3.Connection, operation_id: str, provider: str, purpose: str, limits: Sequence[BudgetLimit],
                 units: int, subject_scope: str, ttl_seconds: float, now: datetime) -> BudgetReservation | BudgetDenied:
        _expire_in_tx(conn, now, EXPIRE_BATCH)
        existing = conn.execute("SELECT * FROM web_budget_reservations WHERE operation_id = ?", (operation_id,)).fetchone()
        if existing is not None and existing["status"] == "reserved":
            return BudgetDenied(operation_id, "operation", "in_flight", retry_after=parse_dt(existing["expires_at"]))
        if existing is not None and existing["status"] != "released":
            return _reservation(existing)
        day = now.date().isoformat()
        checks: dict[tuple[str, str], BudgetLimit] = {}
        for limit in limits:  # 同一层重复给出时取更严的上限
            key = (INFLIGHT_WINDOW if limit.kind == CONCURRENT else day, limit.scope_key)
            if key not in checks or limit.max_units < checks[key].max_units:
                checks[key] = limit
        for (window, scope_key), limit in checks.items():
            row = conn.execute("SELECT used_units, inflight_units FROM web_budget_counters WHERE window_key = ? AND scope_key = ?",
                               (window, scope_key)).fetchone()
            used, inflight = (int(row["used_units"]), int(row["inflight_units"])) if row else (0, 0)
            if (inflight if limit.kind == CONCURRENT else used + inflight) + units > limit.max_units:
                if limit.kind == CONCURRENT:
                    return BudgetDenied(operation_id, scope_key, "concurrency")
                next_day = datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=timezone.utc)
                return BudgetDenied(operation_id, scope_key, "limit_reached", retry_after=next_day)
        pairs = [[window, scope_key, limit.kind] for (window, scope_key), limit in checks.items()]
        if (day, f"usage:{provider}:{purpose}") not in checks:  # 不设上限的“供应商:用途”日用量，供运行状态查看
            pairs.append([day, f"usage:{provider}:{purpose}", DAILY])
        for window, scope_key, _kind in pairs:
            _bump(conn, window, scope_key, used=0, inflight=units, now=now)
        expires = now + timedelta(seconds=min(86400.0, max(5.0, float(ttl_seconds))))
        reservation_id = existing["reservation_id"] if existing is not None else f"br_{uuid.uuid4().hex[:20]}"
        conn.execute(
            "INSERT INTO web_budget_reservations (reservation_id, operation_id, provider, purpose, subject_scope, accounting_window, scope_pairs_json, "
            "reserved_units, actual_units, status, outcome, provider_request_id, created_at, expires_at, settled_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 'reserved', NULL, NULL, ?, ?, NULL, ?) "
            "ON CONFLICT(reservation_id) DO UPDATE SET provider = excluded.provider, purpose = excluded.purpose, subject_scope = excluded.subject_scope, "
            "accounting_window = excluded.accounting_window, scope_pairs_json = excluded.scope_pairs_json, reserved_units = excluded.reserved_units, "
            "actual_units = NULL, status = 'reserved', outcome = NULL, provider_request_id = NULL, expires_at = excluded.expires_at, settled_at = NULL, "
            "updated_at = excluded.updated_at",  # released（确定没发出）的操作重新占用
            (reservation_id, operation_id, provider, purpose, subject_scope, day, json.dumps(pairs), units, iso(now), iso(expires), iso(now)),
        )
        return _reservation(conn.execute("SELECT * FROM web_budget_reservations WHERE reservation_id = ?", (reservation_id,)).fetchone())

    def _settle(self, conn: sqlite3.Connection, reservation_id: str, outcome: str, actual_units: int | None,
                provider_request_id: str | None, now: datetime) -> BudgetReservation:
        row = conn.execute("SELECT * FROM web_budget_reservations WHERE reservation_id = ?", (reservation_id,)).fetchone()
        if row is None:
            raise KeyError(f"budget reservation not found: {reservation_id}")
        status, reserved = row["status"], int(row["reserved_units"])
        pairs = json.loads(row["scope_pairs_json"])
        if status == "reserved":  # 正常结算：释放在途，按结果计入已用
            used = 0 if outcome == "not_sent" else reserved if outcome == "unknown" or actual_units is None else max(0, int(actual_units))
            for window, scope_key, kind in pairs:
                _bump(conn, window, scope_key, used=used if kind == DAILY else 0, inflight=-reserved, now=now)
        elif status in ("unknown", "expired") and outcome != "unknown":  # 迟到或查清的结果
            # 转 unknown/expired 那一步已经**按预占全额**保守计入已用，所以这里只补**差额**：
            # 查清用了 1、当初记了 2，就回正 -1。原来只处理 not_sent（整笔退回），
            # "部分用上"这种情况一分钱都回不来，`used` 永久停在保守值——不是暂时多记，是永久多记。
            # 说不清用了几个单位（actual_units 为 None）时维持保守值，**不因为"回正"反而少记**。
            # 在途在那一步也已经释放过，这里一律不再动它（**不能重复扣 inflight**）。
            clarified = 0 if outcome == "not_sent" else (reserved if actual_units is None else max(0, int(actual_units)))
            correction = clarified - reserved
            if correction:
                for window, scope_key, kind in pairs:  # 用原 scope、原记账窗口，不碰当天别的操作
                    if kind == DAILY:
                        _bump(conn, window, scope_key, used=correction, inflight=0, now=now)
        else:  # 已结算、已退回，或重复报告 unknown：不改
            return _reservation(row)
        conn.execute(
            "UPDATE web_budget_reservations SET status = ?, outcome = ?, actual_units = ?, provider_request_id = COALESCE(?, provider_request_id), "
            "settled_at = ?, updated_at = ? WHERE reservation_id = ?",
            (_STATUS_OF[outcome], outcome, None if outcome == "unknown" else actual_units, provider_request_id, iso(now), iso(now), reservation_id),
        )
        return _reservation(conn.execute("SELECT * FROM web_budget_reservations WHERE reservation_id = ?", (reservation_id,)).fetchone())


def _expire_in_tx(conn: sqlite3.Connection, now: datetime, limit: int) -> int:
    rows = conn.execute(
        "SELECT reservation_id, reserved_units, scope_pairs_json FROM web_budget_reservations WHERE status = 'reserved' AND expires_at <= ? "
        "ORDER BY expires_at LIMIT ?", (iso(now), max(1, int(limit)))).fetchall()
    for row in rows:
        reserved = int(row["reserved_units"])
        for window, scope_key, kind in json.loads(row["scope_pairs_json"]):
            _bump(conn, window, scope_key, used=reserved if kind == DAILY else 0, inflight=-reserved, now=now)
        conn.execute("UPDATE web_budget_reservations SET status = 'expired', settled_at = ?, updated_at = ? WHERE reservation_id = ? AND status = 'reserved'",
                     (iso(now), iso(now), row["reservation_id"]))
    return len(rows)


def _bump(conn: sqlite3.Connection, window: str, scope_key: str, *, used: int, inflight: int, now: datetime) -> None:
    conn.execute(
        "INSERT INTO web_budget_counters (window_key, scope_key, used_units, inflight_units, updated_at) VALUES (?, ?, max(0, ?), max(0, ?), ?) "
        "ON CONFLICT(window_key, scope_key) DO UPDATE SET used_units = max(0, used_units + ?), inflight_units = max(0, inflight_units + ?), "
        "updated_at = excluded.updated_at",
        (window, scope_key, used, inflight, iso(now), used, inflight),
    )


def _reservation(row) -> BudgetReservation:
    return BudgetReservation(reservation_id=row["reservation_id"], operation_id=row["operation_id"], provider=row["provider"], purpose=row["purpose"],
                             subject_scope=row["subject_scope"], accounting_window=row["accounting_window"], reserved_units=int(row["reserved_units"]),
                             expires_at=parse_dt(row["expires_at"]), status=row["status"])
