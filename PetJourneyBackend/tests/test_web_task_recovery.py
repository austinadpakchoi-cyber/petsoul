"""工作包 A：任务领取围栏、过期回收、续租、有界重试与终态保护（注入时钟 + 临时库，不联网）。"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.web_platform.lease import MAX_LEASE_SECONDS
from app.web_platform.tasks import LostClaim, RecoveryCounts, StaleClaim, WebTaskQueue, complete_in_tx
from task_budget_helpers import TaskTestBase

# 注入时钟的起点放在真实时间之后：用真实时间登记的任务在 T0 一定已经到期
T0 = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)


class ClaimFencingTests(TaskTestBase):
    def test_expired_running_is_reclaimed_and_old_worker_is_fenced(self) -> None:
        with self.clock(T0):
            task, _ = self.queue.enqueue("probe", "expired-running", {"x": 1}, max_attempts=3)
        first = self.queue.claim_next("worker-a", ["probe"], lease_seconds=1, now=T0)
        self.assertEqual((first.claim_generation, first.attempts, first.payload_ref), (1, 1, f"web_tasks:{task.task_id}"))
        self.assertTrue(first.worker_id.startswith("worker-a#"), "持有者标识 = worker 标签 + 每次领取唯一的随机段")
        self.assertIsNone(self.queue.claim_next("worker-b", ["probe"], now=T0 + timedelta(milliseconds=500)), "租期内别人领不到")
        later = T0 + timedelta(seconds=2)
        second = self.queue.claim_next("worker-b", ["probe"], lease_seconds=60, now=later)
        self.assertIsNotNone(second, "租期过了，另一个 worker 能领回来")
        self.assertEqual((second.task_id, second.claim_generation), (task.task_id, 2))
        for action in (lambda: self.queue.complete_claim(first, now=later), lambda: self.queue.fail_claim(first, "Late", now=later),
                       lambda: self.queue.supersede_claim(first, "late", now=later)):
            with self.assertRaises(StaleClaim) as ctx:
                action()
            self.assertEqual((ctx.exception.lost.reason, ctx.exception.lost.current_generation), ("taken_over", 2))
        lost = self.queue.renew(first, now=later)
        self.assertIsInstance(lost, LostClaim, "续租失败返回 LostClaim")
        self.assertEqual(lost.reason, "taken_over")
        row = self.row(task.task_id)
        self.assertEqual((row["status"], row["locked_by"], row["attempts"]), ("running", second.worker_id, 2), "旧 worker 的提交一律不生效")
        self.queue.complete_claim(second, now=later)
        self.assertEqual(self.row(task.task_id)["status"], "succeeded")

    def test_expired_lease_cannot_commit_even_before_anyone_reclaims(self) -> None:
        task, _ = self.queue.enqueue("probe", "late-commit", {})
        claim = self.queue.claim_next("worker-a", ["probe"], lease_seconds=5, now=T0)
        with self.assertRaises(StaleClaim) as ctx:
            self.queue.complete_claim(claim, now=T0 + timedelta(seconds=6))
        self.assertEqual(ctx.exception.lost.reason, "expired")
        self.assertEqual(self.row(task.task_id)["status"], "running", "等下一次领取按次数回收")

    def test_superseded_is_terminal_for_stale_complete_and_fail(self) -> None:
        task, _ = self.queue.enqueue("probe", "reception:note:n1:photo", {})
        claim = self.queue.claim_next("worker-a", ["probe"], now=T0)
        self.assertEqual(self.queue.supersede_pending("reception:note:n1:", "care note revoked"), [task.task_id])
        with self.assertRaises(StaleClaim) as ctx:
            self.queue.complete_claim(claim, now=T0)
        self.assertEqual(ctx.exception.lost.reason, "superseded")
        with self.clock(T0):
            self.assertFalse(self.queue.complete(task.task_id), "旧写法也不能把 superseded 改成 succeeded")
            self.assertEqual(self.queue.fail(task.task_id, "LateError", retry_delay_seconds=0).status, "superseded", "fail 不能复活终态")
        self.assertEqual(self.row(task.task_id)["status"], "superseded")

    def test_terminal_states_never_come_back(self) -> None:
        done, _ = self.queue.enqueue("probe", "done", {})
        claim = self.queue.claim_next("worker-a", ["probe"], now=T0)
        self.queue.complete_claim(claim, now=T0)
        with self.assertRaises(StaleClaim) as ctx:
            self.queue.fail_claim(claim, "Late", now=T0)
        self.assertEqual(ctx.exception.lost.reason, "finished")
        failed, _ = self.queue.enqueue("probe", "failed", {}, max_attempts=1)
        claim = self.queue.claim_next("worker-a", ["probe"], now=T0)
        self.assertEqual(self.queue.fail_claim(claim, "Boom", now=T0), "failed")
        with self.clock(T0 + timedelta(seconds=1)):
            for task_id in (done.task_id, failed.task_id):
                before = self.row(task_id)["status"]
                self.assertFalse(self.queue.complete(task_id))
                self.assertEqual(self.queue.fail(task_id, "Late", retry_delay_seconds=0).status, before)
                self.assertFalse(self.queue.supersede(task_id, "late"))
                self.assertEqual(self.row(task_id)["status"], before)
        self.assertIsNone(self.queue.claim_next("worker-b", ["probe"], now=T0 + timedelta(days=1)))

    def test_completing_twice_with_the_same_claim_is_a_replay(self) -> None:
        self.queue.enqueue("probe", "twice", {})
        claim = self.queue.claim_next("worker-a", ["probe"], now=T0)
        for expected in (True, False):  # 第二次：重放，不报错也不改状态
            with self.storage.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                self.assertEqual(complete_in_tx(conn, claim, now=T0), expected)

    def test_foreign_worker_cannot_complete_a_running_task_by_id(self) -> None:
        task, _ = self.queue.enqueue("probe", "foreign", {})
        claim = self.queue.claim_next("worker-a", ["probe"], now=T0)
        other = WebTaskQueue(self.storage)
        with self.clock(T0):
            self.assertFalse(other.complete(task.task_id), "不是这次领取的持有者，不能按 task_id 完成")
            self.assertEqual(other.fail(task.task_id, "Foreign").status, "running", "租期内别人也不能按 task_id 失败重排")
        self.queue.complete_claim(claim, now=T0)

    def test_legacy_claim_then_complete_by_id_still_works_and_is_fenced(self) -> None:
        task, _ = self.queue.enqueue("probe", "legacy", {})
        with self.clock(T0):
            self.assertEqual(self.queue.claim("worker-a", ["probe"]).task_id, task.task_id)
            self.assertTrue(self.queue.complete(task.task_id), "同一个队列对象 claim() 拿到的领取：旧写法照常完成")
        self.assertEqual(self.row(task.task_id)["status"], "succeeded")
        queued, _ = self.queue.enqueue("postcard", "postcard:v1", {})
        with self.clock(T0):
            self.assertTrue(self.queue.complete(queued.task_id), "从未领取的 queued（同步生成的明信片）仍可直接完成")


class RecoveryAndRetryTests(TaskTestBase):
    def test_expiry_beyond_max_attempts_goes_to_failed(self) -> None:
        task, _ = self.queue.enqueue("probe", "exhaust", {}, max_attempts=2)
        now = T0
        for _ in range(2):
            self.assertIsNotNone(self.queue.claim_next("worker-a", ["probe"], lease_seconds=1, now=now))
            now += timedelta(seconds=2)
        self.assertEqual(self.queue.recover_expired(now=now), RecoveryCounts(requeued=0, failed=1))
        row = self.row(task.task_id)
        self.assertEqual((row["status"], row["last_error"], row["attempts"]), ("failed", "lease_expired", 2))
        self.assertIsNone(self.queue.claim_next("worker-b", ["probe"], now=now + timedelta(hours=1)))

    def test_expired_policy_fail_does_not_rerun_non_idempotent_kinds(self) -> None:
        queue = WebTaskQueue(self.storage, expired_policy={"paid-image": "fail"})
        task, _ = queue.enqueue("paid-image", "img-1", {}, max_attempts=3)
        queue.claim_next("worker-a", ["paid-image"], lease_seconds=1, now=T0)
        self.assertIsNone(queue.claim_next("worker-b", ["paid-image"], now=T0 + timedelta(seconds=2)))
        self.assertEqual((self.row(task.task_id)["status"], self.row(task.task_id)["last_error"]), ("failed", "lease_expired"))

    def test_renew_extends_but_is_bounded(self) -> None:
        self.queue.enqueue("probe", "renew", {})
        claim = self.queue.claim_next("worker-a", ["probe"], lease_seconds=10, now=T0)
        renewed = self.queue.renew(claim, extension_seconds=30, now=T0 + timedelta(seconds=8))
        self.assertEqual(renewed.lease_until, T0 + timedelta(seconds=38))
        self.assertIsNone(self.queue.claim_next("worker-b", ["probe"], now=T0 + timedelta(seconds=20)), "续租后别人领不走")
        capped = self.queue.renew(renewed, extension_seconds=10**6, now=T0 + timedelta(seconds=20))
        self.assertEqual(capped.lease_until, T0 + timedelta(seconds=20 + MAX_LEASE_SECONDS), "单次续租有上限")
        bounded = self.queue.renew(capped, extension_seconds=600, now=T0 + timedelta(seconds=21), not_after=T0 + timedelta(seconds=100))
        self.assertEqual(bounded.lease_until, T0 + timedelta(seconds=100), "不超过操作截止")
        lost = self.queue.renew(bounded, now=T0 + timedelta(seconds=101))
        self.assertEqual((type(lost), lost.reason), (LostClaim, "expired"), "过期后不能再续")

    def test_bounded_retry_with_exponential_backoff(self) -> None:
        task, _ = self.queue.enqueue("probe", "retry", {}, max_attempts=3)
        self.queue.retry_jitter.seed(7)
        now, delays = T0, []
        for expected_status in ("queued", "queued", "failed"):
            claim = self.queue.claim_next("worker-a", ["probe"], now=now)
            self.assertIsNotNone(claim)
            self.assertEqual(self.queue.fail_claim(claim, "Transient", now=now), expected_status)
            run_after = datetime.fromisoformat(self.row(task.task_id)["run_after"])
            delays.append((run_after - now).total_seconds())
            self.assertIsNone(self.queue.claim_next("worker-a", ["probe"], now=now), "退避期间不重领")
            now = run_after + timedelta(seconds=1)
        self.assertTrue(48 <= delays[0] <= 60 and 96 <= delays[1] <= 120, delays)
        self.assertEqual(self.row(task.task_id)["attempts"], 3)
        self.assertIsNone(self.queue.claim_next("worker-a", ["probe"], now=now + timedelta(days=1)), "用完次数就停")

    def test_non_retryable_failure_is_terminal_immediately(self) -> None:
        task, _ = self.queue.enqueue("probe", "revoked", {}, max_attempts=5)
        claim = self.queue.claim_next("worker-a", ["probe"], now=T0)
        self.assertEqual(self.queue.fail_claim(claim, "permission_revoked", retryable=False, now=T0), "failed")
        self.assertEqual(self.row(task.task_id)["attempts"], 1)

    def test_retry_failed_keeps_generation_monotonic(self) -> None:
        task, _ = self.queue.enqueue("probe", "redraw", {}, max_attempts=1)
        first = self.queue.claim_next("worker-a", ["probe"], now=T0)
        self.queue.fail_claim(first, "Boom", now=T0)
        self.assertTrue(self.queue.retry_failed(task.task_id, now=T0))
        self.assertFalse(self.queue.retry_failed(task.task_id, now=T0), "只对 failed 生效")
        second = self.queue.claim_next("worker-a", ["probe"], now=T0)
        self.assertEqual(second.claim_generation, 2, "attempts 不清零，领取代数继续增长")
        with self.assertRaises(StaleClaim):
            self.queue.complete_claim(first, now=T0)
        self.queue.complete_claim(second, now=T0)

    def test_raw_attempts_reset_still_cannot_revive_an_old_claim(self) -> None:
        task, _ = self.queue.enqueue("probe", "raw-reset", {}, max_attempts=1)
        old = self.queue.claim_next("web-illustrations", ["probe"], now=T0)
        self.queue.fail_claim(old, "Boom", now=T0)
        with self.storage.connect() as conn:  # 现有 illustrations.retry 的写法：直接把 attempts 清零重排
            conn.execute("UPDATE web_tasks SET status = 'queued', attempts = 0, run_after = ? WHERE task_id = ?", (T0.isoformat(), task.task_id))
        new = self.queue.claim_next("web-illustrations", ["probe"], now=T0)
        self.assertEqual(new.claim_generation, old.claim_generation, "代数重复了")
        with self.assertRaises(StaleClaim):
            self.queue.complete_claim(old, now=T0)  # 同一个 worker 标签、同一代数，仍靠每次领取唯一的持有者标识拦住
        self.queue.complete_claim(new, now=T0)

    def test_retry_failed_can_join_the_callers_transaction(self) -> None:
        """重画：把“任务重排”和“展示状态改回处理中”放进同一个事务，中途崩溃不会只做一半。"""
        task, _ = self.queue.enqueue("probe", "redraw-tx", {}, max_attempts=1)
        self.queue.fail_claim(self.queue.claim_next("worker-a", ["probe"], now=T0), "Boom", now=T0)
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self.assertTrue(self.queue.retry_failed(task.task_id, now=T0, conn=conn))
            conn.execute("INSERT INTO probe_effects (task_id, writer) VALUES (?, 'redraw')", (task.task_id,))
            conn.rollback()
        self.assertEqual((self.row(task.task_id)["status"], self.effects()), ("failed", []), "调用方回滚：两边都不生效")
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self.queue.retry_failed(task.task_id, now=T0, conn=conn)
            conn.execute("INSERT INTO probe_effects (task_id, writer) VALUES (?, 'redraw')", (task.task_id,))
        self.assertEqual((self.row(task.task_id)["status"], self.effects()), ("queued", ["redraw"]))
        self.assertEqual(self.queue.claim_next("worker-a", ["probe"], now=T0).claim_generation, 2, "次数只放宽不清零")

    def test_task_health_reports_stuck_and_lagging_work(self) -> None:
        self.queue.enqueue("probe", "h1", {}, run_after=T0 - timedelta(minutes=5))
        self.queue.enqueue("probe", "h2", {}, run_after=T0 + timedelta(minutes=5))
        self.queue.enqueue("probe", "h3", {}, run_after=T0 - timedelta(minutes=1))
        self.queue.claim_next("worker-a", ["probe"], lease_seconds=1, now=T0)  # 领走最老的 h1
        health = self.queue.task_health(now=T0 + timedelta(seconds=30))
        self.assertEqual((health["running"], health["running_expired"], health["queued_due"], health["queued_later"]), (1, 1, 1, 1))
        self.assertEqual(health["oldest_due_lag_seconds"], 90)


if __name__ == "__main__":
    unittest.main()
