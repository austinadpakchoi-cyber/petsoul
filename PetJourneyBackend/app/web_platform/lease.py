"""租约：世界推进的进程租约，以及单个任务的领取租约（围栏原语）。都存在 SQLite 里，跨进程有效。

进程租约（WorkerLease）：谁拿到谁推进世界，其余进程这一轮跳过。
- 租约有期限（ttl）；持有者每轮续期；持有进程挂掉后，期限一过其他进程（API 内嵌或独立 worker）自动接手；
- 每个任期一个新的持有者标识（holder）：同一进程失去租约、别人接手、再拿回来时标识也不同，
  上一个任期里发起的操作拿着旧标识，提交时会被 ``assert_lease_held`` 拒绝（防 ABA）；
- 同时记录最近一轮的时间、是否成功与脱敏错误摘要，供运行状态接口报告“任务是否真的在跑”。

任务领取租约（web_tasks 的 running 行）：
- 领取凭据是运行时内部契约的 TaskClaim：worker_id 由队列生成（``<worker 标签>#<每次领取唯一的随机段>``，写进 locked_by），
  claim_generation 是领取时 +1 后的 attempts；
- 提交一律按 “task_id + worker_id + claim_generation + running + 租期未过” 条件更新，不成立就抛 StaleClaim（携带 LostClaim），
  调用方回滚整个业务事务；续租失败返回 LostClaim；
- 这些函数在调用方的连接上执行（调用方须已 BEGIN IMMEDIATE），不开始、不提交、不回滚。

三种权威分开：进程租约只证明“这个进程现在有权推进世界”；领取租约只证明“这一次领取仍有效”；
实体版本与权限由集成层在同一事务里另行校验，缺一不可。
"""

from __future__ import annotations

import logging
import os
import socket
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta

from ..schemas.runtime_internal import LostClaim, StaleClaim, TaskClaim
from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow

logger = logging.getLogger("petsoul.web.lease")

MAX_LEASE_SECONDS = 3600  # 单次领取或续租的最长期限；更长的活动须分段续租


class LeaseLost(Exception):
    """进程租约已不属于这个任期（被接管、已过期或已释放）：本任期发起的写入必须回滚。"""

    def __init__(self, name: str, reason: str) -> None:
        super().__init__(f"worker lease {name}: {reason}")
        self.name = name
        self.reason = reason


class WorkerLease:
    def __init__(self, storage: JourneyStorage, name: str, ttl: timedelta, role: str) -> None:
        self.storage = storage
        self.name = name
        self.ttl = ttl
        self.role = role
        self._instance = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.holder = self._new_tenure()

    def _new_tenure(self) -> str:
        return f"{self._instance}#{uuid.uuid4().hex[:8]}"

    def acquire(self, now: datetime | None = None) -> bool:
        """拿到（或续上）租约返回 True。别的进程的租约还没过期时返回 False。接手别人的租约时开始新任期（换 holder）。"""
        now = now or utcnow()
        expires = iso(now + self.ttl)
        try:
            with self.storage.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute("SELECT holder, expires_at FROM web_worker_leases WHERE name = ?", (self.name,)).fetchone()
                if row is not None and row["holder"] == self.holder:
                    # 自己的任期（期间没人接手过）：续期
                    conn.execute("UPDATE web_worker_leases SET heartbeat_at = ?, expires_at = ? WHERE name = ? AND holder = ?",
                                 (iso(now), expires, self.name, self.holder))
                    return True
                if row is not None and parse_dt(row["expires_at"]) > now:
                    return False
                tenure = self._new_tenure()
                if row is None:
                    conn.execute("INSERT INTO web_worker_leases (name, holder, pid, host, role, started_at, heartbeat_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                 (self.name, tenure, os.getpid(), socket.gethostname(), self.role, iso(now), iso(now), expires))
                else:
                    conn.execute("UPDATE web_worker_leases SET holder = ?, pid = ?, host = ?, role = ?, started_at = ?, heartbeat_at = ?, expires_at = ? "
                                 "WHERE name = ? AND holder = ?",
                                 (tenure, os.getpid(), socket.gethostname(), self.role, iso(now), iso(now), expires, self.name, row["holder"]))
                self.holder = tenure
                return True
        except Exception:  # noqa: BLE001 - 数据库忙：这一轮先不跑，下一轮再试
            return False

    def tenure(self) -> str:
        """当前任期标识。一次操作开始时记下它，提交时交给 assert_lease_held；不要在提交时再读（那可能已是新任期）。"""
        return self.holder

    def still_held(self, now: datetime | None = None) -> bool:
        """只读：本任期是否仍持有且未过期（长任务在两步之间自查用）。"""
        try:
            with self.storage.connect() as conn:
                assert_lease_held(conn, self.name, self.holder, now=now)
            return True
        except LeaseLost:
            return False

    def record_tick(self, ok: bool, error: str | None, now: datetime | None = None) -> None:
        now = now or utcnow()
        with self.storage.connect() as conn:
            conn.execute(
                "UPDATE web_worker_leases SET last_tick_at = ?, last_ok_at = CASE WHEN ? THEN ? ELSE last_ok_at END, last_error = ?, ticks = ticks + 1 "
                "WHERE name = ? AND holder = ?", (iso(now), 1 if ok else 0, iso(now), (error or None) and error[:200], self.name, self.holder))

    def release(self) -> None:
        with self.storage.connect() as conn:
            conn.execute("UPDATE web_worker_leases SET expires_at = ? WHERE name = ? AND holder = ?", (iso(utcnow()), self.name, self.holder))


def assert_lease_held(conn: sqlite3.Connection, name: str, tenure: str, *, now: datetime | None = None) -> None:
    """在调用方事务里确认：进程租约仍是这个任期、且未过期；否则抛 LeaseLost（调用方回滚）。不开始、不提交事务。"""
    now = now or utcnow()
    row = conn.execute("SELECT holder, expires_at FROM web_worker_leases WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise LeaseLost(name, "missing")
    if row["holder"] != tenure:
        raise LeaseLost(name, "taken_over")
    if parse_dt(row["expires_at"]) <= now:
        raise LeaseLost(name, "expired")


def lease_status(storage: JourneyStorage, name: str, now: datetime | None = None) -> dict | None:
    now = now or utcnow()
    try:
        with storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_worker_leases WHERE name = ?", (name,)).fetchone()
    except Exception:  # noqa: BLE001 - 迁移尚未应用
        return None
    if row is None:
        return None
    return {"holder_role": row["role"], "pid": row["pid"], "host": row["host"], "started_at": parse_dt(row["started_at"]),
            "heartbeat_at": parse_dt(row["heartbeat_at"]), "expires_at": parse_dt(row["expires_at"]), "alive": parse_dt(row["expires_at"]) > now,
            "last_tick_at": parse_dt(row["last_tick_at"]) if row["last_tick_at"] else None, "last_ok_at": parse_dt(row["last_ok_at"]) if row["last_ok_at"] else None,
            "last_error": row["last_error"], "ticks": row["ticks"]}


# ---- 任务领取租约 ----

def lease_duration(seconds: float) -> timedelta:
    return timedelta(seconds=min(MAX_LEASE_SECONDS, max(1.0, float(seconds))))


def claim_from_row(row) -> TaskClaim:
    """running 行 → 领取凭据（旧任务没有语义版本与聚合编号，source_versions / aggregate_id 为 None）。"""
    return TaskClaim(task_id=row["task_id"], kind=row["kind"], aggregate_id=None, payload_ref=f"web_tasks:{row['task_id']}",
                     worker_id=row["locked_by"], claim_generation=int(row["attempts"]), lease_until=parse_dt(row["locked_until"]),
                     attempts=int(row["attempts"]), max_attempts=int(row["max_attempts"]))


def lost_claim(conn: sqlite3.Connection, claim: TaskClaim, now: datetime) -> LostClaim | None:
    """领取仍有效返回 None；否则说明失效原因。"""
    row = conn.execute("SELECT status, locked_by, locked_until, attempts, last_error FROM web_tasks WHERE task_id = ?", (claim.task_id,)).fetchone()
    if row is None:
        return LostClaim(claim.task_id, claim.claim_generation, "missing")
    status, generation = row["status"], int(row["attempts"])
    if status == "running" and (row["locked_by"] != claim.worker_id or generation != claim.claim_generation):
        reason = "taken_over"
    elif status == "running":
        if row["locked_until"] is not None and parse_dt(row["locked_until"]) > now:
            return None
        reason = "expired"
    elif status == "superseded":
        reason = "superseded"
    elif status == "queued" and row["last_error"] == "lease_expired":
        reason = "expired"  # 过期后已回收重排
    else:
        reason = "finished"  # 已完成、已失败，或本次领取已按失败重排
    return LostClaim(claim.task_id, claim.claim_generation, reason, current_status=status, current_generation=generation)


def assert_current_claim(conn: sqlite3.Connection, claim: TaskClaim, *, now: datetime | None = None) -> None:
    """领取仍有效（running、持有者与代数一致、租期未过）才返回；否则抛 StaleClaim。"""
    lost = lost_claim(conn, claim, now or utcnow())
    if lost is not None:
        raise StaleClaim(lost)


def complete_in_tx(conn: sqlite3.Connection, claim: TaskClaim, *, now: datetime | None = None) -> bool:
    """按围栏标记完成；同一领取重复完成视为重放（返回 False，不报错）。领取失效抛 StaleClaim。"""
    now = now or utcnow()
    if _fence_update(conn, claim, now, "status = 'succeeded', last_error = NULL, locked_until = NULL, updated_at = ?", (iso(now),)):
        return True
    row = conn.execute("SELECT status, locked_by, attempts FROM web_tasks WHERE task_id = ?", (claim.task_id,)).fetchone()
    if row is not None and row["status"] == "succeeded" and row["locked_by"] == claim.worker_id and int(row["attempts"]) == claim.claim_generation:
        return False
    raise StaleClaim(lost_claim(conn, claim, now) or LostClaim(claim.task_id, claim.claim_generation, "finished"))


def fail_in_tx(conn: sqlite3.Connection, claim: TaskClaim, error: str, *, retryable: bool = True,
               retry_delay_seconds: float = 60.0, now: datetime | None = None) -> str:
    """按围栏记失败：可重试且没用完次数 → queued（run_after 延后），否则 failed。返回新状态；领取失效抛 StaleClaim。"""
    now = now or utcnow()
    requeue = 1 if retryable else 0
    changed = _fence_update(
        conn, claim, now,
        "status = CASE WHEN ? = 1 AND attempts < max_attempts THEN 'queued' ELSE 'failed' END, "
        "run_after = CASE WHEN ? = 1 AND attempts < max_attempts THEN ? ELSE run_after END, "
        "locked_by = CASE WHEN ? = 1 AND attempts < max_attempts THEN NULL ELSE locked_by END, "
        "locked_until = NULL, last_error = ?, updated_at = ?",
        (requeue, requeue, iso(now + timedelta(seconds=max(0.0, retry_delay_seconds))), requeue, (error or "")[:500], iso(now)),
    )
    if not changed:
        raise StaleClaim(lost_claim(conn, claim, now) or LostClaim(claim.task_id, claim.claim_generation, "finished"))
    return conn.execute("SELECT status FROM web_tasks WHERE task_id = ?", (claim.task_id,)).fetchone()["status"]


def supersede_in_tx(conn: sqlite3.Connection, claim: TaskClaim, reason: str, *, now: datetime | None = None) -> None:
    """持有者自己判定来源已失效（precheck 不通过）：按围栏标记 superseded。"""
    now = now or utcnow()
    if not _fence_update(conn, claim, now, "status = 'superseded', locked_until = NULL, last_error = ?, updated_at = ?", ((reason or "")[:500], iso(now))):
        raise StaleClaim(lost_claim(conn, claim, now) or LostClaim(claim.task_id, claim.claim_generation, "finished"))


def renew_in_tx(conn: sqlite3.Connection, claim: TaskClaim, until: datetime, *, now: datetime) -> bool:
    """按围栏把租期改到 until。成功返回 True；领取已失效返回 False（由调用方取 LostClaim）。"""
    return _fence_update(conn, claim, now, "locked_until = ?, updated_at = ?", (iso(until), iso(now)))


def recover_expired_in_tx(conn: sqlite3.Connection, now: datetime, *, kinds=None, limit: int = 50, policy=None) -> tuple[int, int]:
    """回收租期已过的 running：没用完次数且策略允许的重排（立即可领），其余进 failed（last_error=lease_expired）。返回 (重排, 失败)。"""
    where, params = ("", ()) if not kinds else (f" AND kind IN ({','.join('?' for _ in kinds)})", tuple(kinds))
    rows = conn.execute(
        f"SELECT task_id, kind, attempts, max_attempts FROM web_tasks WHERE status = 'running' "
        f"AND (locked_until IS NULL OR locked_until <= ?){where} ORDER BY locked_until LIMIT ?",
        (iso(now), *params, max(1, int(limit))),
    ).fetchall()
    requeued = failed = 0
    for row in rows:
        requeue = (policy or {}).get(row["kind"], "requeue") == "requeue" and row["attempts"] < row["max_attempts"]
        conn.execute(
            "UPDATE web_tasks SET status = ?, run_after = CASE WHEN ? THEN ? ELSE run_after END, locked_by = NULL, locked_until = NULL, "
            "last_error = 'lease_expired', updated_at = ? WHERE task_id = ? AND status = 'running'",
            ("queued" if requeue else "failed", 1 if requeue else 0, iso(now), iso(now), row["task_id"]),
        )
        requeued, failed = (requeued + 1, failed) if requeue else (requeued, failed + 1)
    return requeued, failed


def _fence_update(conn: sqlite3.Connection, claim: TaskClaim, now: datetime, set_sql: str, params: tuple) -> bool:
    cur = conn.execute(
        f"UPDATE web_tasks SET {set_sql} WHERE task_id = ? AND status = 'running' AND locked_by = ? AND attempts = ? AND locked_until > ?",
        (*params, claim.task_id, claim.worker_id, claim.claim_generation, iso(now)),
    )
    return cur.rowcount == 1


class TaskLeaseKeeper:
    """旧式 handler 执行期间的后台续租：每 1/3 租期续一次，最长续到 max_run_seconds；续租失败即停。renew 由队列提供。"""

    def __init__(self, renew, claim: TaskClaim, lease_seconds: float, max_run_seconds: float = 1800.0) -> None:
        self.renew = renew
        self.claim = claim
        self.lease_seconds = lease_seconds
        self.lost: LostClaim | None = None
        self._deadline = time.monotonic() + max_run_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, args=(max(1.0, lease_seconds / 3),), name="web-task-lease", daemon=True)
        self._thread.start()

    def _loop(self, interval: float) -> None:
        while not self._stop.wait(interval):
            if time.monotonic() > self._deadline:
                return  # 不再续租：租期过后由下一次领取回收
            try:
                result = self.renew(self.claim, extension_seconds=self.lease_seconds)
            except Exception:  # noqa: BLE001 - 数据库忙等：下一轮再试
                logger.warning("task lease renewal failed; will retry", exc_info=True)
                continue
            if isinstance(result, LostClaim):
                self.lost = result
                return
            self.claim = result

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
