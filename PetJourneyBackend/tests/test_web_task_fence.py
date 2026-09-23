"""工作包 A：业务写入与“任务完成”同一事务的围栏，以及 run_once 的领取、重试与失效处理（临时库，不联网）。"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.web_platform.tasks import StaleClaim, assert_current_claim, complete_in_tx, run_once, supersede_pending_in_tx
from task_budget_helpers import TaskTestBase

T0 = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)


class TransactionFenceTests(TaskTestBase):
    def write_effect(self, conn, task_id: str, writer: str) -> None:  # noqa: ANN001
        conn.execute("INSERT INTO probe_effects (task_id, writer) VALUES (?, ?)", (task_id, writer))

    def test_business_write_and_completion_commit_together(self) -> None:
        task, _ = self.queue.enqueue("probe", "fenced-ok", {})
        claim = self.queue.claim_next("worker-a", ["probe"])
        with self.queue.fenced(claim) as conn:
            self.write_effect(conn, task.task_id, "worker-a")
        self.assertEqual((self.row(task.task_id)["status"], self.effects()), ("succeeded", ["worker-a"]))

    def test_lost_claim_rolls_back_the_business_write(self) -> None:
        task, _ = self.queue.enqueue("probe", "reception:note:n2:photo", {})
        claim = self.queue.claim_next("worker-a", ["probe"])
        self.queue.supersede_pending("reception:note:n2:", "care note revoked")  # 执行期间撤回
        with self.assertRaises(StaleClaim) as ctx:
            with self.queue.fenced(claim) as conn:
                self.write_effect(conn, task.task_id, "worker-a")
        self.assertEqual(ctx.exception.lost.reason, "superseded")
        self.assertEqual((self.row(task.task_id)["status"], self.effects()), ("superseded", []), "业务写入随事务回滚")

    def test_claim_lost_between_business_write_and_completion_rolls_back(self) -> None:
        task, _ = self.queue.enqueue("probe", "race-in-tx", {})
        claim = self.queue.claim_next("worker-a", ["probe"], lease_seconds=2, now=T0)
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            assert_current_claim(conn, claim, now=T0 + timedelta(seconds=1))
            self.write_effect(conn, task.task_id, "worker-a")
            with self.assertRaises(StaleClaim) as ctx:
                complete_in_tx(conn, claim, now=T0 + timedelta(seconds=3))  # 写业务期间租期已过
            conn.rollback()
        self.assertEqual(ctx.exception.lost.reason, "expired")
        self.assertEqual((self.row(task.task_id)["status"], self.effects()), ("running", []))

    def test_exception_inside_fence_rolls_back_and_keeps_task_running(self) -> None:
        task, _ = self.queue.enqueue("probe", "boom-in-tx", {})
        claim = self.queue.claim_next("worker-a", ["probe"])
        with self.assertRaises(RuntimeError):
            with self.queue.fenced(claim) as conn:
                self.write_effect(conn, task.task_id, "worker-a")
                raise RuntimeError("provider parse failed")
        self.assertEqual((self.row(task.task_id)["status"], self.effects()), ("running", []))
        self.assertEqual(self.queue.fail_claim(claim, "RuntimeError"), "queued")

    def test_supersede_pending_joins_the_callers_transaction(self) -> None:
        task, _ = self.queue.enqueue("probe", "reception:note:n3:photo", {})
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self.assertEqual(supersede_pending_in_tx(conn, "reception:note:n3:", "revoked"), [task.task_id])
            conn.rollback()
        self.assertEqual(self.row(task.task_id)["status"], "queued", "调用方回滚：撤销一并撤回")
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            supersede_pending_in_tx(conn, "reception:note:n3:", "revoked")
        self.assertEqual(self.row(task.task_id)["status"], "superseded")

    def test_run_once_legacy_handler_revoked_mid_run_stays_superseded(self) -> None:
        self.queue.enqueue("probe", "reception:note:n4:photo", {})
        legacy = SimpleNamespace(kind="probe", precheck=lambda t: True,
                                 run=lambda t: self.queue.supersede_pending("reception:note:n4:", "care note revoked"))
        self.assertEqual(run_once(self.queue, {"probe": legacy}, "worker-a").status, "superseded", "旧 complete 不再覆盖 superseded")

    def test_run_once_fenced_handler_discards_business_write_when_revoked(self) -> None:
        self.queue.enqueue("probe", "reception:note:n5:photo", {})

        def run_claimed(task, claim, queue) -> None:  # noqa: ANN001
            queue.supersede_pending("reception:note:n5:", "care note revoked")  # 外部调用期间用户撤回
            with queue.fenced(claim) as conn:
                self.write_effect(conn, task.task_id, "fenced-handler")

        fenced = SimpleNamespace(kind="probe", precheck=lambda t: True, run_claimed=run_claimed)
        self.assertEqual((run_once(self.queue, {"probe": fenced}, "worker-a").status, self.effects()), ("superseded", []))

    def test_run_once_fenced_handler_commits_result_and_completion_once(self) -> None:
        task, _ = self.queue.enqueue("probe", "fenced-run", {})

        def run_claimed(t, claim, queue) -> None:  # noqa: ANN001
            with queue.fenced(claim) as conn:
                self.write_effect(conn, t.task_id, "fenced-handler")

        result = run_once(self.queue, {"probe": SimpleNamespace(kind="probe", precheck=lambda t: True, run_claimed=run_claimed)}, "worker-a")
        self.assertEqual((result.status, self.effects()), ("succeeded", ["fenced-handler"]), "handler 已完成，run_once 再完成是重放")

    def test_run_once_retries_then_exhausts(self) -> None:
        task, _ = self.queue.enqueue("probe", "flaky", {}, max_attempts=2)
        calls: list[int] = []

        def run(_task) -> None:  # noqa: ANN001
            calls.append(1)
            raise TimeoutError("upstream")

        flaky = SimpleNamespace(kind="probe", precheck=lambda t: True, run=run)
        with self.clock(T0):
            self.assertEqual(run_once(self.queue, {"probe": flaky}, "worker-a").status, "queued")
            self.assertIsNone(run_once(self.queue, {"probe": flaky}, "worker-a"), "退避期间不执行")
        with self.clock(T0 + timedelta(seconds=61)):
            self.assertEqual(run_once(self.queue, {"probe": flaky}, "worker-a").status, "failed")
        self.assertEqual((len(calls), self.row(task.task_id)["last_error"]), (2, "TimeoutError"))

    def test_run_once_precheck_failure_supersedes_without_running(self) -> None:
        self.queue.enqueue("probe", "stale-source", {}, source_version="1")
        ran: list[int] = []
        handler = SimpleNamespace(kind="probe", precheck=lambda t: t.source_version == "2", run=lambda t: ran.append(1))
        self.assertEqual((run_once(self.queue, {"probe": handler}, "worker-a").status, ran), ("superseded", []))


if __name__ == "__main__":
    unittest.main()
