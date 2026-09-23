"""工作包 A 测试共用：临时库、缺表场景、禁网、任务测试基类（非测试模块，不以 test_ 开头）。

只用临时 SQLite（真实 JourneyStorage + 真实 web 迁移）。额度两张表由迁移 0050_budget 建立，测试不再自己建表。
``budget_tables=False`` 表示“这个库没有额度表”：先跑完整迁移，再在这一次性临时库里删掉这两张表，
用来复现迁移未应用（或旧库）时的行为；正式迁移不动。
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from unittest import mock

from app.storage import JourneyStorage
from app.web_platform import lease as lease_mod
from app.web_platform import tasks as tasks_mod
from app.web_platform.migrations import apply_web_migrations
from app.web_platform.tasks import TaskClaim, WebTaskQueue

BUDGET_TABLES = ("web_budget_reservations", "web_budget_counters")  # 由迁移 0050_budget 建立
NETWORK_TARGETS = ("socket.socket.connect", "socket.create_connection", "socket.getaddrinfo")


def open_storage(path: str, *, budget_tables: bool = True) -> JourneyStorage:
    """跑完整迁移的一次性临时库。budget_tables=False 时再把额度表删掉，造出“没有额度表”的库。"""
    storage = JourneyStorage(Path(path))
    apply_web_migrations(storage)
    if not budget_tables:
        with storage.connect() as conn:
            for table in BUDGET_TABLES:
                conn.execute(f"DROP TABLE IF EXISTS {table}")
    return storage


def tables_in(storage: JourneyStorage, names: tuple[str, ...] = BUDGET_TABLES) -> set[str]:
    """库里实际存在的表（用于先断言缺表条件真的成立，再验证行为）。"""
    placeholders = ",".join("?" for _ in names)
    with storage.connect() as conn:
        return {row[0] for row in conn.execute(f"SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ({placeholders})", names)}


class CountingProvider:
    """付费调用替身：只数被调了几次，并记下每次的 operation_id；不联网、不产生费用。"""

    def __init__(self, fail: Exception | None = None) -> None:
        self.calls: list[str] = []
        self.fail = fail

    def __call__(self, operation_id: str) -> str:
        self.calls.append(operation_id)
        if self.fail is not None:
            raise self.fail
        return f"ok:{operation_id}"


def provider_error(settle_outcome: str) -> Exception:
    """付费调用失败的替身异常，带上调用方判定的结算口径：到上限 → not_sent，超时 → unknown，供应商报错 → failed。"""
    error = RuntimeError(f"provider {settle_outcome}")
    error.settle_outcome = settle_outcome
    return error


def reserve_then_call(ledger, provider_call: CountingProvider, operation_id: str, **reserve_kwargs):
    """A 交接第四节写的接法：预占成功才调用，调用完按结果结算；被拒或拿到的不是新预占就不调用。

    返回 (预占或拒绝, 结果或 None, 结算结果或 None)。
    """
    from app.schemas.runtime_internal import BudgetDenied

    held = ledger.reserve(operation_id, **reserve_kwargs)
    if isinstance(held, BudgetDenied) or held.status != "reserved":
        return held, None, None
    try:
        result = provider_call(operation_id)
    except Exception as exc:  # noqa: BLE001 - 由调用方按失败类型决定结算口径
        outcome = getattr(exc, "settle_outcome", "failed")
        return held, None, ledger.settle(held, outcome)
    return held, result, ledger.settle(held, "succeeded", actual_units=1)


def block_network_hook(event: str, _args) -> None:  # noqa: ANN001
    """子进程用：sys.addaudithook(block_network_hook)。"""
    if event in ("socket.connect", "socket.getaddrinfo"):
        raise RuntimeError("network blocked in test child")


def claim_to_json(claim: TaskClaim) -> str:
    return json.dumps({"task_id": claim.task_id, "kind": claim.kind, "worker_id": claim.worker_id, "claim_generation": claim.claim_generation,
                       "lease_until": claim.lease_until.isoformat(), "attempts": claim.attempts, "max_attempts": claim.max_attempts,
                       "payload_ref": claim.payload_ref})


def claim_from_json(text: str) -> TaskClaim:
    data = json.loads(text)
    return TaskClaim(task_id=data["task_id"], kind=data["kind"], aggregate_id=None, payload_ref=data["payload_ref"], worker_id=data["worker_id"],
                     claim_generation=data["claim_generation"], lease_until=datetime.fromisoformat(data["lease_until"]),
                     attempts=data["attempts"], max_attempts=data["max_attempts"])


class TaskTestBase(unittest.TestCase):
    """临时库 + 真实迁移 + 一张业务探针表；测试期间任何联网尝试都直接失败。

    默认保持迁移建出的完整 schema（含额度表）；只有专门验证“缺表”的用例把 budget_tables 设为 False。
    """

    budget_tables = True

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_dir = tmp.name
        self.db = str(Path(tmp.name) / "a.sqlite3")
        self.storage = open_storage(self.db, budget_tables=self.budget_tables)
        self.queue = WebTaskQueue(self.storage)
        with self.storage.connect() as conn:
            conn.execute("CREATE TABLE probe_effects (task_id TEXT NOT NULL, writer TEXT NOT NULL)")
        stack = ExitStack()
        for target in NETWORK_TARGETS:
            stack.enter_context(mock.patch(target, side_effect=AssertionError("tests must not touch the network")))
        self.addCleanup(stack.close)

    def row(self, task_id: str) -> sqlite3.Row:
        with self.storage.connect() as conn:
            return conn.execute("SELECT * FROM web_tasks WHERE task_id = ?", (task_id,)).fetchone()

    def effects(self) -> list[str]:
        with self.storage.connect() as conn:
            return [r["writer"] for r in conn.execute("SELECT writer FROM probe_effects ORDER BY rowid")]

    def clock(self, now: datetime) -> ExitStack:
        """把队列与领取租约模块里的 utcnow 换成固定时刻（旧接口内部取时间用）。"""
        stack = ExitStack()
        for module in (tasks_mod, lease_mod):
            stack.enter_context(mock.patch.object(module, "utcnow", return_value=now))
        return stack

