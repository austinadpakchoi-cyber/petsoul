"""工作包 A：真实多进程下的领取互斥、被杀 worker 的接管与晚到提交拦截，以及进程租约的任期标识（临时库，不联网）。"""

from __future__ import annotations

import multiprocessing as mp
import os
import sys
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.web_platform.lease import LeaseLost, WorkerLease, assert_lease_held
from app.web_platform.tasks import LostClaim, StaleClaim, WebTaskQueue
from task_budget_helpers import TaskTestBase, block_network_hook, claim_from_json, claim_to_json, open_storage

T0 = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)


# ---- 子进程（spawn 需要模块级函数；每个子进程自己禁网）----

def child_claim_all(db: str, worker: str, barrier, out) -> None:  # noqa: ANN001
    sys.addaudithook(block_network_hook)
    queue = WebTaskQueue(open_storage(db, budget_tables=False))
    barrier.wait(timeout=60)
    got = []
    while (claim := queue.claim_next(worker, ["race"], lease_seconds=300)) is not None:
        got.append(claim.task_id)
        queue.complete_claim(claim)
    out.put((worker, got))


def child_claim_then_crash(db: str, claim_file: str) -> None:
    sys.addaudithook(block_network_hook)
    claim = WebTaskQueue(open_storage(db, budget_tables=False)).claim_next("worker-a", ["crash"], lease_seconds=1)
    Path(claim_file).write_text(claim_to_json(claim), encoding="utf-8")
    os._exit(0)  # 模拟进程被杀：不完成、不失败、不释放


def child_late_commit(db: str, claim_file: str, out) -> None:  # noqa: ANN001
    sys.addaudithook(block_network_hook)
    queue = WebTaskQueue(open_storage(db, budget_tables=False))
    stale = claim_from_json(Path(claim_file).read_text(encoding="utf-8"))
    results = {}
    for name, action in (("complete", lambda: queue.complete_claim(stale)), ("fail", lambda: queue.fail_claim(stale, "Late")),
                         ("fenced", lambda: queue.fenced(stale).__enter__())):
        try:
            action()
            results[name] = "accepted"
        except StaleClaim as stale_claim:
            results[name] = stale_claim.lost.reason
    renewed = queue.renew(stale)
    results["renew"] = renewed.reason if isinstance(renewed, LostClaim) else "accepted"
    out.put(results)


class ConcurrencyTests(TaskTestBase):
    def test_concurrent_enqueue_of_the_same_key_never_raises(self) -> None:
        barrier = threading.Barrier(8)
        results: list[bool] = []
        errors: list[str] = []

        def enqueue() -> None:
            barrier.wait(timeout=10)
            try:
                results.append(self.queue.enqueue("probe", "same-key", {"n": 1})[1])
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))

        threads = [threading.Thread(target=enqueue) for _ in range(8)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=60)
        self.assertEqual((errors, sorted(results)), ([], [False] * 7 + [True]))

    def test_real_processes_claim_each_task_exactly_once(self) -> None:
        ids = {self.queue.enqueue("race", f"race-{i}", {"i": i})[0].task_id for i in range(24)}
        ctx = mp.get_context("spawn")
        barrier, out = ctx.Barrier(3), ctx.Queue()
        procs = [ctx.Process(target=child_claim_all, args=(self.db, f"proc-{n}", barrier, out)) for n in range(3)]
        for proc in procs:
            proc.start()
        claimed = [out.get(timeout=120) for _ in procs]
        for proc in procs:
            proc.join(timeout=60)
        self.assertEqual([proc.exitcode for proc in procs], [0, 0, 0])
        every = [task_id for _worker, got in claimed for task_id in got]
        self.assertEqual(len(every), len(set(every)), "没有任务被两个进程同时领取")
        self.assertEqual(set(every), ids)
        with self.storage.connect() as conn:
            self.assertEqual({r[0] for r in conn.execute("SELECT DISTINCT attempts FROM web_tasks WHERE kind = 'race'")}, {1})

    def test_killed_worker_is_taken_over_and_its_late_commit_is_rejected(self) -> None:
        task, _ = self.queue.enqueue("crash", "crash-1", {}, max_attempts=3)
        claim_file = str(Path(self.tmp_dir) / "worker-a.claim.json")
        ctx = mp.get_context("spawn")
        crashed = ctx.Process(target=child_claim_then_crash, args=(self.db, claim_file))
        crashed.start()
        crashed.join(timeout=120)
        self.assertEqual(self.row(task.task_id)["status"], "running", "被杀的 worker 留下 running")
        taker = self.queue.claim_next("worker-b", ["crash"], lease_seconds=600, now=datetime.now(timezone.utc) + timedelta(seconds=5))
        self.assertIsNotNone(taker, "租期过后另一个进程接手")
        self.assertEqual(taker.claim_generation, 2)
        out = ctx.Queue()
        late = ctx.Process(target=child_late_commit, args=(self.db, claim_file, out))
        late.start()
        results = out.get(timeout=120)
        late.join(timeout=60)
        self.assertEqual(results, {"complete": "taken_over", "fail": "taken_over", "fenced": "taken_over", "renew": "taken_over"})
        with self.queue.fenced(taker) as conn:
            conn.execute("INSERT INTO probe_effects (task_id, writer) VALUES (?, 'worker-b')", (task.task_id,))
        row = self.row(task.task_id)
        self.assertEqual((row["status"], row["locked_by"], row["attempts"]), ("succeeded", taker.worker_id, 2))
        self.assertEqual(self.effects(), ["worker-b"], "旧 worker 的业务写入一条也没进库")


class WorkerLeaseTenureTests(TaskTestBase):
    def lease(self, role: str) -> WorkerLease:
        return WorkerLease(self.storage, "world", timedelta(seconds=90), role)

    def test_takeover_starts_a_new_tenure_so_aba_is_detected(self) -> None:
        p, q = self.lease("embedded"), self.lease("worker")
        self.assertTrue(p.acquire(T0))
        first_tenure = p.tenure()
        self.assertFalse(q.acquire(T0 + timedelta(seconds=10)))
        self.assertTrue(q.acquire(T0 + timedelta(seconds=91)), "过期后接手")
        self.assertTrue(p.acquire(T0 + timedelta(seconds=182)), "q 也过期后 p 再拿回")
        self.assertNotEqual(p.tenure(), first_tenure, "同一进程再拿回来也是新任期")
        with self.storage.connect() as conn:
            with self.assertRaises(LeaseLost) as ctx:
                assert_lease_held(conn, "world", first_tenure, now=T0 + timedelta(seconds=183))
            self.assertEqual(ctx.exception.reason, "taken_over", "上一个任期发起的操作不能提交")
            assert_lease_held(conn, "world", p.tenure(), now=T0 + timedelta(seconds=183))

    def test_renewal_keeps_the_tenure_and_expiry_is_detected(self) -> None:
        p = self.lease("worker")
        self.assertTrue(p.acquire(T0))
        tenure = p.tenure()
        self.assertTrue(p.acquire(T0 + timedelta(seconds=60)))
        self.assertEqual(p.tenure(), tenure, "续期不换任期")
        self.assertTrue(p.still_held(T0 + timedelta(seconds=100)))
        self.assertFalse(p.still_held(T0 + timedelta(seconds=151)))
        with self.storage.connect() as conn:
            with self.assertRaises(LeaseLost) as ctx:
                assert_lease_held(conn, "world", tenure, now=T0 + timedelta(seconds=151))
        self.assertEqual(ctx.exception.reason, "expired")

    def test_stale_holder_cannot_record_or_release(self) -> None:
        p, q = self.lease("embedded"), self.lease("worker")
        p.acquire(T0)
        q.acquire(T0 + timedelta(seconds=91))
        p.record_tick(True, None, T0 + timedelta(seconds=92))
        p.release()
        with self.storage.connect() as conn:
            row = conn.execute("SELECT holder, ticks, expires_at FROM web_worker_leases WHERE name = 'world'").fetchone()
        self.assertEqual((row["holder"], row["ticks"]), (q.tenure(), 0))
        self.assertGreater(datetime.fromisoformat(row["expires_at"]), T0 + timedelta(seconds=92), "旧持有者释放不影响新任期")


if __name__ == "__main__":
    unittest.main()
