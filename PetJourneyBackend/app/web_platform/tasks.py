"""可恢复任务队列：去重登记、领取、过期回收、续租、有界重试与终态保护。

领取凭据、失效原因与事务内围栏（TaskClaim / LostClaim / StaleClaim、assert_current_claim / complete_in_tx / fail_in_tx /
supersede_in_tx）见 ``lease.py`` 的“任务领取租约”，这里一并导出，调用方统一从本模块 import。

- 领取：先回收这些类型里租期已过的 running（没用完次数就重排，用完或策略要求就进 failed），再领一个到期任务；
- 完成 / 失败 / 撤销 / 续租都按领取凭据做条件更新：旧 worker 即使后来返回，也写不进结果和业务副作用；
- 业务写入要和“任务完成”同一事务时，用 ``queue.fenced(claim)``，或把调用方的连接交给 assert_current_claim / complete_in_tx；
- 终态（succeeded / failed / superseded）不会被任何路径改回；只有 ``retry_failed`` 能显式重排 failed，且 attempts 不清零。

旧接口（enqueue / claim / complete / fail / supersede / supersede_pending / get / run_once）签名不变；
按 task_id 的旧写法不能再绕过围栏：running 任务只有同一个队列对象 claim() 时拿到的凭据才能完成或失败。
handler 在执行前必须 ``precheck``：例如记忆版本已被撤回/更正时返回 False，任务标记 superseded，旧结果不发布。
新写法的 handler 可以提供 ``run_claimed(task, claim, queue)``，在 ``with queue.fenced(claim) as conn:`` 里写业务结果。
"""

from __future__ import annotations

import json
import logging
import random
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Iterator, Mapping, Protocol, Sequence

from ..schemas.runtime_internal import LostClaim, StaleClaim, TaskClaim
from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from .lease import (
    MAX_LEASE_SECONDS,
    TaskLeaseKeeper,
    assert_current_claim,
    claim_from_row,
    complete_in_tx,
    fail_in_tx,
    lease_duration,
    lost_claim,
    recover_expired_in_tx,
    renew_in_tx,
    supersede_in_tx,
)

logger = logging.getLogger("petsoul.web.tasks")

DEFAULT_LEASE_SECONDS = 120
RETRY_BASE_SECONDS = 60  # 第一次重试间隔（与旧行为一致），之后指数增长
RETRY_MAX_SECONDS = 900
RECOVERY_BATCH = 50

__all__ = [
    "DEFAULT_LEASE_SECONDS", "MAX_LEASE_SECONDS", "LostClaim", "RecoveryCounts", "StaleClaim", "TaskClaim", "TaskHandler", "WebTask",
    "WebTaskQueue", "assert_current_claim", "complete_in_tx", "fail_in_tx", "run_once", "supersede_in_tx", "supersede_pending_in_tx",
]


@dataclass(frozen=True, slots=True)
class WebTask:
    task_id: str
    kind: str
    dedupe_key: str
    status: str
    attempts: int
    max_attempts: int
    payload: dict[str, Any]
    source_version: str | None
    run_after: datetime
    last_error: str | None


@dataclass(frozen=True, slots=True)
class RecoveryCounts:
    requeued: int
    failed: int


class TaskHandler(Protocol):
    kind: str

    def precheck(self, task: WebTask) -> bool:
        """任务依赖的来源版本仍有效才返回 True。"""

    def run(self, task: WebTask) -> None:
        ...


class WebTaskQueue:
    def __init__(self, storage: JourneyStorage, *, expired_policy: Mapping[str, str] | None = None) -> None:
        self.storage = storage
        # 租期过了的 running 怎么处理（按任务类型）："requeue"（默认，没用完次数就重排）或 "fail"（直接进 failed，适合不能重复付费的任务）
        self.expired_policy = dict(expired_policy or {})
        self.retry_jitter = random.Random()
        self._held: dict[str, TaskClaim] = {}  # 旧接口 claim() 拿到的凭据：旧写法 complete(task_id) / fail(task_id) 用它做围栏
        self._held_lock = threading.Lock()

    # ---- 登记与领取 ----
    def enqueue(
        self,
        kind: str,
        dedupe_key: str,
        payload: dict[str, Any],
        *,
        source_version: str | None = None,
        run_after: datetime | None = None,
        max_attempts: int = 3,
    ) -> tuple[WebTask, bool]:
        """同 dedupe_key 只登记一次；返回 (任务, 是否新建)。并发登记靠唯一约束冲突后读取既有记录，不会抛错。

        自己开一个短连接。要和调用方的业务写入同生共死，请用 `enqueue_in`（SQL 只有那一份，这里是它的包装）。
        """
        with self.storage.connect() as conn:
            return self.enqueue_in(conn, kind, dedupe_key, payload, source_version=source_version,
                                   run_after=run_after, max_attempts=max_attempts)

    def enqueue_in(
        self,
        conn: sqlite3.Connection,
        kind: str,
        dedupe_key: str,
        payload: dict[str, Any],
        *,
        source_version: str | None = None,
        run_after: datetime | None = None,
        max_attempts: int = 3,
        now: datetime | None = None,
    ) -> tuple[WebTask, bool]:
        """在**调用方的写事务里**登记任务：不自己开连接、不 BEGIN、不提交（COORD-A-ATOMIC 方案 B）。

        用在"任务和它所依据的业务事实必须同生共死"的地方：拍照登记要和 visit 更新、photo_taken 事件
        一起提交或一起回滚，否则版本冲突/租约被接手时会留下一张没有事件的孤儿任务——镜头没响，队列里却多了一张要画的照片。
        调用方须已 `BEGIN IMMEDIATE`（例如 `web_platform.uow.unit_of_work`）。
        远端调用仍由任务进程在事务之外发，这里只写本地登记。
        """
        stamp = now or utcnow()
        cur = conn.execute(
            "INSERT INTO web_tasks (task_id, kind, dedupe_key, status, attempts, max_attempts, payload_json, "
            "source_version, run_after, created_at, updated_at) VALUES (?, ?, ?, 'queued', 0, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(dedupe_key) DO NOTHING",
            (f"wt_{uuid.uuid4().hex[:20]}", kind, dedupe_key, max(1, int(max_attempts)), json.dumps(payload, ensure_ascii=False, default=str),
             source_version, iso(run_after or stamp), iso(stamp), iso(stamp)),
        )
        created = cur.rowcount == 1
        row = conn.execute("SELECT * FROM web_tasks WHERE dedupe_key = ?", (dedupe_key,)).fetchone()
        return _task_from_row(row), created

    def claim_next(self, worker_id: str, kinds: Sequence[str], *, lease_seconds: float = DEFAULT_LEASE_SECONDS,
                   now: datetime | None = None) -> TaskClaim | None:
        """先回收这些类型里租期已过的 running，再领取一个到期任务。返回的 worker_id 是本次领取唯一的持有者标识。"""
        kinds = list(kinds)
        if not kinds:
            return None
        now = now or utcnow()
        holder = f"{worker_id}#{uuid.uuid4().hex[:16]}"
        placeholders = ",".join("?" for _ in kinds)
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            recover_expired_in_tx(conn, now, kinds=kinds, limit=RECOVERY_BATCH, policy=self.expired_policy)
            row = conn.execute(
                f"SELECT task_id FROM web_tasks WHERE status = 'queued' AND run_after <= ? AND attempts < max_attempts "
                f"AND kind IN ({placeholders}) ORDER BY run_after, created_at LIMIT 1",
                (iso(now), *kinds),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE web_tasks SET status = 'running', attempts = attempts + 1, locked_by = ?, locked_until = ?, updated_at = ? "
                "WHERE task_id = ? AND status = 'queued'",
                (holder, iso(now + lease_duration(lease_seconds)), iso(now), row["task_id"]),
            )
            claimed = conn.execute("SELECT * FROM web_tasks WHERE task_id = ?", (row["task_id"],)).fetchone()
        return claim_from_row(claimed)

    def claim(self, worker_id: str, kinds: list[str], *, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> WebTask | None:
        """旧接口：返回任务快照。领取凭据留在本队列对象里，之后 complete(task_id) / fail(task_id) 按它做围栏。"""
        claim = self.claim_next(worker_id, kinds, lease_seconds=lease_seconds)
        if claim is None:
            return None
        with self._held_lock:
            self._held[claim.task_id] = claim
            if len(self._held) > 1024:
                self._held.pop(next(iter(self._held)))
        return self.get(claim.task_id)

    # ---- 持有者操作（全部带围栏）----
    def renew(self, claim: TaskClaim, *, extension_seconds: float = DEFAULT_LEASE_SECONDS, now: datetime | None = None,
              not_after: datetime | None = None) -> TaskClaim | LostClaim:
        """续租：从现在起再延 extension_seconds（不超过 MAX_LEASE_SECONDS、任务截止与 not_after）。领取已失效返回 LostClaim。"""
        now = now or utcnow()
        until = min(b for b in (now + lease_duration(extension_seconds), claim.deadline_at, not_after) if b is not None)
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if until > now and renew_in_tx(conn, claim, until, now=now):
                return replace(claim, lease_until=until)
            return lost_claim(conn, claim, now) or LostClaim(claim.task_id, claim.claim_generation, "expired")

    def complete_claim(self, claim: TaskClaim, *, now: datetime | None = None) -> None:
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            complete_in_tx(conn, claim, now=now)
        self._forget(claim)

    def fail_claim(self, claim: TaskClaim, error: str, *, retryable: bool = True, retry_delay_seconds: float | None = None,
                   now: datetime | None = None) -> str:
        """失败：可重试且没用完次数 → queued（指数退避，抖动只向下）；否则 failed。返回新状态。"""
        delay = self.retry_delay(claim.attempts) if retry_delay_seconds is None else retry_delay_seconds
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            status = fail_in_tx(conn, claim, error, retryable=retryable, retry_delay_seconds=delay, now=now)
        self._forget(claim)
        return status

    def supersede_claim(self, claim: TaskClaim, reason: str, *, now: datetime | None = None) -> None:
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            supersede_in_tx(conn, claim, reason, now=now)
        self._forget(claim)

    @contextmanager
    def fenced(self, claim: TaskClaim, *, complete: bool = True) -> Iterator[sqlite3.Connection]:
        """业务写入与“任务完成”同一事务：进入时确认领取仍有效，块内写业务，退出时按围栏标记完成并提交。

        领取失效抛 StaleClaim，块内的业务写入随事务一起回滚；块内抛出的其他异常同样回滚，任务保持 running，交给执行循环处理。
        """
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            assert_current_claim(conn, claim)
            yield conn
            if complete:
                complete_in_tx(conn, claim)
        if complete:
            self._forget(claim)

    def retry_delay(self, attempts: int) -> float:
        """第 n 次失败后的等待：60s、120s、240s……封顶 15 分钟；抖动只向下（×0.8–1.0），不会晚于名义间隔。"""
        nominal = min(RETRY_MAX_SECONDS, RETRY_BASE_SECONDS * (2 ** max(0, attempts - 1)))
        return nominal * (1.0 - 0.2 * self.retry_jitter.random())

    # ---- 维护 ----
    def recover_expired(self, *, now: datetime | None = None, limit: int = 100, kinds: Sequence[str] | None = None) -> RecoveryCounts:
        """回收租期已过的 running：没用完次数的重排（立即可领），用完的进 failed（last_error=lease_expired）。"""
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            requeued, failed = recover_expired_in_tx(conn, now or utcnow(), kinds=kinds, limit=limit, policy=self.expired_policy)
        return RecoveryCounts(requeued=requeued, failed=failed)

    def retry_failed(self, task_id: str, *, extra_attempts: int = 1, now: datetime | None = None,
                     expected_attempts: int | None = None, conn: sqlite3.Connection | None = None) -> bool:
        """把 failed 显式重排（例如主人点“重画”）：attempts 不清零，只放宽 max_attempts，领取代数保持单调。

        传入 conn 时在调用方事务里执行（调用方须已 BEGIN IMMEDIATE），可以和“把展示状态改回处理中”一起提交。

        ``expected_attempts``：调用方**当时看到的那次失败**的尝试次数。任务可能在"排回去 → 又跑了一轮 → 又失败"
        之后重新变成 failed，光看状态分不出"这是同一次失败"还是"又失败了一次"（ABA）。带上它就在同一条
        条件更新里核对版本：迟到的重复请求会一个都不匹配，不会白排一次。不传则不加这道围栏（旧调用方行为不变）。
        """
        now = now or utcnow()
        fence, extra = ("", ()) if expected_attempts is None else (" AND attempts = ?", (int(expected_attempts),))
        sql = ("UPDATE web_tasks SET status = 'queued', max_attempts = attempts + ?, run_after = ?, last_error = NULL, "
               f"locked_by = NULL, locked_until = NULL, updated_at = ? WHERE task_id = ? AND status = 'failed'{fence}")
        params = (max(1, int(extra_attempts)), iso(now), iso(now), task_id, *extra)
        if conn is not None:
            return conn.execute(sql, params).rowcount == 1
        with self.storage.connect() as own:
            return own.execute(sql, params).rowcount == 1

    def task_health(self, *, now: datetime | None = None, kinds: Sequence[str] | None = None) -> dict[str, int]:
        """只读运行指标：到期未领、之后才到期、领取中、租期已过仍 running、用完次数仍排队、最老到期等待秒数。"""
        now = now or utcnow()
        where, params = ("", ()) if not kinds else (f" AND kind IN ({','.join('?' for _ in kinds)})", tuple(kinds))
        checks = {
            "queued_due": ("status = 'queued' AND run_after <= ? AND attempts < max_attempts", (iso(now),)),
            "queued_later": ("status = 'queued' AND run_after > ?", (iso(now),)),
            "running": ("status = 'running'", ()),
            "running_expired": ("status = 'running' AND (locked_until IS NULL OR locked_until <= ?)", (iso(now),)),
            "queued_exhausted": ("status = 'queued' AND attempts >= max_attempts", ()),
        }
        with self.storage.connect() as conn:
            health = {name: int(conn.execute(f"SELECT COUNT(*) FROM web_tasks WHERE {cond}{where}", (*args, *params)).fetchone()[0])
                      for name, (cond, args) in checks.items()}
            due = conn.execute(f"SELECT MIN(run_after) FROM web_tasks WHERE status = 'queued' AND run_after <= ?{where}", (iso(now), *params)).fetchone()[0]
        health["oldest_due_lag_seconds"] = 0 if due is None else max(0, int((now - parse_dt(due)).total_seconds()))
        return health

    # ---- 旧接口（按 task_id）----
    def complete(self, task_id: str) -> bool:
        """旧写法。本队列 claim() 领取中 → 按凭据围栏完成；从未领取的 queued（例如同步生成的明信片）→ succeeded；其余拒绝。"""
        with self._held_lock:
            held = self._held.get(task_id)
        if held is not None:
            try:
                self.complete_claim(held)
                return True
            except StaleClaim as stale:
                logger.info("complete refused: %s", stale)
                return False
        with self.storage.connect() as conn:
            cur = conn.execute("UPDATE web_tasks SET status = 'succeeded', last_error = NULL, locked_until = NULL, updated_at = ? "
                               "WHERE task_id = ? AND status = 'queued'", (iso(utcnow()), task_id))
        if cur.rowcount != 1:
            logger.warning("complete(%s) refused: running under another claim or already terminal", task_id)
        return cur.rowcount == 1

    def supersede(self, task_id: str, reason: str) -> bool:
        """外部撤销（来源失效）：queued 或 running 都可撤销；终态不变。running 的持有者随后提交会被围栏拒绝。"""
        with self.storage.connect() as conn:
            cur = conn.execute("UPDATE web_tasks SET status = 'superseded', last_error = ?, locked_until = NULL, updated_at = ? "
                               "WHERE task_id = ? AND status IN ('queued', 'running')", ((reason or "")[:500], iso(utcnow()), task_id))
        with self._held_lock:
            self._held.pop(task_id, None)
        return cur.rowcount == 1

    def fail(self, task_id: str, error: str, *, retry_delay_seconds: int = 60) -> WebTask:
        """旧写法。本队列领取中 → 按凭据围栏；否则只处理 queued 或租期已过的 running（孤儿），终态与别人领取中的任务不动。

        未超过最大次数则回到 queued 并延后；否则标记 failed。error 不写原始私人内容。
        """
        with self._held_lock:
            held = self._held.get(task_id)
        if held is not None:
            try:
                self.fail_claim(held, error, retry_delay_seconds=retry_delay_seconds)
            except StaleClaim as stale:
                logger.info("fail refused: %s", stale)
            return self.get(task_id)  # type: ignore[return-value]
        now = utcnow()
        with self.storage.connect() as conn:
            conn.execute(
                "UPDATE web_tasks SET status = CASE WHEN attempts < max_attempts THEN 'queued' ELSE 'failed' END, last_error = ?, "
                "run_after = CASE WHEN attempts < max_attempts THEN ? ELSE run_after END, locked_by = NULL, locked_until = NULL, "
                "updated_at = ? WHERE task_id = ? AND (status = 'queued' OR (status = 'running' AND (locked_until IS NULL OR locked_until <= ?)))",
                ((error or "")[:500], iso(now + timedelta(seconds=retry_delay_seconds)), iso(now), task_id, iso(now)),
            )
            row = conn.execute("SELECT * FROM web_tasks WHERE task_id = ?", (task_id,)).fetchone()
        return _task_from_row(row)

    def supersede_pending(self, dedupe_prefix: str, reason: str) -> list[str]:
        """撤回/更正后使尚未完成的相关任务失效（例如 ``reception:note:<id>:``）；领取中的任务一并撤销，持有者提交会被拒绝。"""
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            ids = supersede_pending_in_tx(conn, dedupe_prefix, reason)
        with self._held_lock:
            for task_id in ids:
                self._held.pop(task_id, None)
        return ids

    def get(self, task_id: str) -> WebTask | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_tasks WHERE task_id = ?", (task_id,)).fetchone()
        return None if row is None else _task_from_row(row)

    def _forget(self, claim: TaskClaim) -> None:
        with self._held_lock:
            if task_id_held := self._held.get(claim.task_id):
                if task_id_held.worker_id == claim.worker_id:
                    del self._held[claim.task_id]


def redraw_ticket(row, task_column: str) -> str | None:
    """把“可以重画吗”的查询结果变成**重画凭据** `<任务号>#<当时看到的失败尝试次数>`；没有任务号就返回 None。

    `row` 要带上任务号那一列和 `web_tasks.attempts`（`LEFT JOIN web_tasks` 得到）。
    带上版本是为了挡住**迟到的重复请求**：任务可能已经"排回去 → 又跑了一轮 → 又失败"，
    状态同样是 failed，但那已经是另一次失败了（见 `retry_failed` 的 `expected_attempts`）。
    老数据没有对应任务行时 `attempts` 为 NULL，退回不带版本的凭据，行为与加围栏之前一致。
    """
    if row is None or not row[task_column]:
        return None
    attempts = row["attempts"] if "attempts" in row.keys() else None
    return row[task_column] if attempts is None else f"{row[task_column]}#{attempts}"


def supersede_pending_in_tx(conn: sqlite3.Connection, dedupe_prefix: str, reason: str, *, now: datetime | None = None) -> list[str]:
    """与更正/撤回的业务写入同一事务，撤销前缀匹配的 queued/running 任务（调用方须已 BEGIN IMMEDIATE）。返回受影响的 task_id。"""
    now = now or utcnow()
    escaped = dedupe_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = conn.execute("SELECT task_id FROM web_tasks WHERE status IN ('queued', 'running') AND dedupe_key LIKE ? ESCAPE '\\'",
                        (escaped + "%",)).fetchall()
    ids = [row["task_id"] for row in rows]
    for task_id in ids:
        conn.execute("UPDATE web_tasks SET status = 'superseded', last_error = ?, locked_until = NULL, updated_at = ? "
                     "WHERE task_id = ? AND status IN ('queued', 'running')", ((reason or "")[:500], iso(now), task_id))
    return ids


def run_once(queue: WebTaskQueue, handlers: dict[str, TaskHandler], worker_id: str, *,
             lease_seconds: float = DEFAULT_LEASE_SECONDS, keep_alive: bool = True) -> WebTask | None:
    """受控单 worker 的单步：领取 → precheck → 执行 → 按围栏记录。异常只记录类名，不记录原文。

    旧式 handler（只有 run）执行期间在后台续租，进程活着就不会被别人接手；进程死了，租期一过由下次领取回收。
    新式 handler（run_claimed）自己用 ``queue.fenced(claim)`` 提交业务结果。领取失效时本次结果作废，不改任务状态。
    """
    claim = queue.claim_next(worker_id, list(handlers), lease_seconds=lease_seconds)
    if claim is None:
        return None
    task = queue.get(claim.task_id)
    handler = handlers[claim.kind]
    try:
        if not handler.precheck(task):
            queue.supersede_claim(claim, "source version no longer valid")
            return queue.get(claim.task_id)
        keeper = TaskLeaseKeeper(queue.renew, claim, lease_seconds) if keep_alive else None
        try:
            run_claimed = getattr(handler, "run_claimed", None)
            if run_claimed is not None:
                run_claimed(task, claim, queue)
            else:
                handler.run(task)
        finally:
            if keeper is not None:
                keeper.stop()
        queue.complete_claim(claim)
    except StaleClaim as stale:
        logger.info("task result discarded: %s", stale)
    except Exception as exc:  # noqa: BLE001 - 记录后交给重试策略
        try:
            queue.fail_claim(claim, type(exc).__name__)
        except StaleClaim as stale:
            logger.info("task failure discarded: %s", stale)
    return queue.get(claim.task_id)


def _task_from_row(row) -> WebTask:
    return WebTask(
        task_id=row["task_id"],
        kind=row["kind"],
        dedupe_key=row["dedupe_key"],
        status=row["status"],
        attempts=row["attempts"],
        max_attempts=row["max_attempts"],
        payload=json.loads(row["payload_json"]),
        source_version=row["source_version"],
        run_after=parse_dt(row["run_after"]),
        last_error=row["last_error"],
    )
