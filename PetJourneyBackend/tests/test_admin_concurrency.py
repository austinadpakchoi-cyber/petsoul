"""真并发：同一件事被同时点了好几次，只能生效一次（方案 §8「并发重复补偿/重试」）。

两种形状，证明的东西不同，分开写，不混着报：

1. **多线程同时打**：几个独立会话在同一道屏障后同时发请求，然后数账本、批次、审计里最终落了几条。
   证明的是「不管谁先谁后，结果只有一次」；**不保证**每一轮都恰好交错到最窄的那个窗口——
   所以断言只写「最终只有一次」，不写「某个线程一定拿到某种回执」。
2. **确定性交错**：在「读到失败」与「条件更新」之间，用钩子插进另一位员工的完整请求
   （以及任务又跑了一轮）。`already_queued` / `stale_attempt` 这两条恢复回执**只有这样才触发得了**，
   顺序执行的用例产生不出那个交错（第一批交接 §5 第 9 条记过这个缺口）。
   钩子只包住只读的诊断查询，不改任何被测实现。
"""

from __future__ import annotations

import threading
import unittest
from typing import Callable
from unittest import mock

from fastapi.testclient import TestClient

from admin_base import ADMIN_PREFIX, AdminStaff, AdminTestBase
from web_base import LUNCH_UTC, FakeClock
from web_provider_fakes import FakeIllustrator


class Tab:
    """同一位员工另开一个浏览器标签：同一个账号、独立的会话 cookie。

    同键并发必须来自**同一个员工**——幂等记录按员工隔离，换个人同一个键就是另一件事。"""

    def __init__(self, staff: AdminStaff) -> None:
        self.client = TestClient(staff.app)
        response = self.client.post(f"{ADMIN_PREFIX}/auth/login", json={"username": staff.username, "password": staff.password})
        assert response.status_code == 200, response.text

    def post(self, path: str, body: dict, key: str):
        headers = {"X-Admin-CSRF-Token": self.client.cookies.get("petsoul_admin_csrf") or "", "Idempotency-Key": key}
        return self.client.post(f"{ADMIN_PREFIX}{path}", json=body, headers=headers)


def race(calls: list[Callable[[], object]], timeout: float = 60.0) -> list:
    """让所有调用在同一道屏障后同时出发；任何一个线程里抛了异常都算用例失败。"""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)
    errors: list[BaseException] = []

    def worker(index: int, call: Callable[[], object]) -> None:
        try:
            barrier.wait(timeout=timeout)
            results[index] = call()
        except BaseException as exc:  # noqa: BLE001 — 收集起来在主线程里报
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i, call), daemon=True) for i, call in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout)
    assert not any(thread.is_alive() for thread in threads), "有线程没在时限内结束"
    assert not errors, f"线程里抛了异常：{errors!r}"
    return results


class ConcurrencyBase(AdminTestBase):
    def count(self, sql: str, params: tuple = ()) -> int:
        with self.app.state.storage.connect() as conn:
            return int(conn.execute(sql, params).fetchone()[0])

    def usage_snapshot(self) -> dict:
        with self.app.state.storage.connect() as conn:
            return {(r["window_key"], r["scope_key"]): (int(r["used_units"]), int(r["inflight_units"]))
                    for r in conn.execute("SELECT window_key, scope_key, used_units, inflight_units FROM web_budget_counters")}

    def assert_no_server_errors(self, responses) -> None:
        for response in responses:
            self.assertLess(response.status_code, 500, response.text)


class ParallelWriteTests(ConcurrencyBase):
    def setUp(self) -> None:
        super().setUp()
        self.player = self.user("race-owner")
        self.player.adopt_and_move_in("adopt-lan")

    def test_same_key_grant_from_six_tabs_moves_the_ledger_once(self):
        ops = self.staff("race-economy", ["economy_ops"])
        tabs = [Tab(ops) for _ in range(6)]
        pet_id = self.player.pet_id
        balance_before = self.web.economy.wallet(pet_id).balance
        usage_before = self.usage_snapshot()
        key = "op-race-grant-0001"
        body = {"pet_id": pet_id, "amount": 20, "reason": "六个标签同时点了发放"}

        responses = race([lambda tab=tab: tab.post("/economy/grant", body, key) for tab in tabs])
        self.assert_no_server_errors(responses)
        for response in responses:
            if response.status_code == 409:
                # 另一个标签正在处理同一个操作号：明确说"在处理中、可以重试"，不是失败、也不是第二笔
                self.assertEqual(response.json()["error"]["code"], "IDEMPOTENCY_IN_PROGRESS", response.text)
                self.assertTrue(response.json()["error"]["retryable"])
            else:
                self.assertEqual(response.status_code, 200, response.text)
        executed = [r for r in responses if r.status_code == 200 and not r.json()["replayed"]]
        self.assertEqual(len(executed), 1, "同一个操作号只能真正执行一次")

        self.assertEqual(self.count("SELECT COUNT(*) FROM economy_transactions WHERE idempotency_key = ?", (f"admin:grant:{key}",)), 1)
        self.assertEqual(self.web.economy.wallet(pet_id).balance, balance_before + 20)
        self.assertEqual(self.count("SELECT COUNT(*) FROM admin_audit WHERE action = 'economy.grant' AND operation_id = ?", (key,)), 1,
                         "审计也只记一次")
        self.assertEqual(self.usage_snapshot(), usage_before, "游戏补偿不碰平台调用账")

        # 并发结束后再用同一个操作号重试：拿回第一次的结果
        settled = Tab(ops).post("/economy/grant", body, key)
        self.assertEqual(settled.status_code, 200, settled.text)
        self.assertTrue(settled.json()["replayed"])
        self.assertTrue(settled.json()["applied"])
        self.assertEqual(self.web.economy.wallet(pet_id).balance, balance_before + 20)

    def test_two_staff_freezing_the_same_account_with_one_version_changes_it_once(self):
        agents = [self.staff(f"race-support-{i}", ["support"]) for i in range(2)]
        for agent in agents:
            agent.login_ok()
        user_id = self.player.user_id
        responses = race([lambda agent=agent, i=i: agent.post(f"/users/{user_id}/freeze",
                                                             {"frozen": True, "reason": f"并发冻结 {i}", "expected_version": 0})
                          for i, agent in enumerate(agents)])
        self.assert_no_server_errors(responses)
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        loser = next(r for r in responses if r.status_code == 409)
        self.assertEqual(loser.json()["error"]["code"], "VERSION_CONFLICT", loser.text)
        with self.app.state.storage.connect() as conn:
            flag = conn.execute("SELECT status, version FROM admin_account_flags WHERE user_id = ?", (user_id,)).fetchone()
        self.assertEqual((flag["status"], int(flag["version"])), ("frozen", 1))
        self.assertEqual(self.count("SELECT COUNT(*) FROM admin_audit WHERE action = 'account.freeze' AND status = 'succeeded' "
                                    "AND target_id = ?", (user_id,)), 1)

    def test_two_publishers_racing_on_one_version_publish_once(self):
        publishers = [self.staff(f"race-publisher-{i}", ["content_publisher"]) for i in range(2)]
        for publisher in publishers:
            publisher.login_ok()
        created = publishers[0].post("/content", {
            "content_type": "announcement", "slug": "race-notice", "title": "并发发布",
            "body": {"title": "并发发布", "body": "两个人同时点了发布。", "severity": "info", "audience": "all"}})
        self.assertEqual(created.status_code, 201, created.text)
        item = created.json()["item"]
        responses = race([lambda p=p, i=i: p.post(f"/content/{item['item_id']}/publish",
                                                  {"revision": 1, "expected_version": item["version"], "reason": f"并发发布 {i}"})
                          for i, p in enumerate(publishers)])
        self.assert_no_server_errors(responses)
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        self.assertEqual(next(r for r in responses if r.status_code == 409).json()["error"]["code"], "VERSION_CONFLICT")
        self.assertEqual(self.count("SELECT COUNT(*) FROM admin_content_publications WHERE item_id = ? AND action = 'publish'",
                                    (item["item_id"],)), 1, "发布流水只能多一条")
        seen = self.client.get("/api/v1/web/announcements").json()["announcements"]
        self.assertEqual([a["slug"] for a in seen], ["race-notice"])


class ParallelBatchTests(ConcurrencyBase):
    def setUp(self) -> None:
        super().setUp()
        from app.web_admin.batches import BatchLimits

        self.app.state.admin.batches.limits = BatchLimits(10, 50, 500)
        self.submitter = self.staff("race-batch-ops", ["economy_ops"])
        self.submitter.login_ok()
        self.pet_ids = []
        for name, candidate in (("race-batch-a", "adopt-lan"), ("race-batch-b", "adopt-doudou"), ("race-batch-c", "adopt-arong")):
            player = self.user(name)
            player.adopt_and_move_in(candidate)
            self.pet_ids.append(player.pet_id)
        submitted = self.submitter.post("/economy/batches", {"title": "并发批次", "reason": "并发执行测试",
                                                             "pet_ids": self.pet_ids, "amount_per_pet": 10})
        self.assertEqual(submitted.status_code, 201, submitted.text)
        self.batch_id = submitted.json()["batch_id"]

    def test_two_approvers_racing_decide_once(self):
        leads = [self.staff(f"race-lead-{i}", ["economy_lead"]) for i in range(2)]
        for lead in leads:
            lead.login_ok()
        responses = race([lambda lead=lead, i=i: lead.post(f"/economy/batches/{self.batch_id}/decision",
                                                           {"approve": True, "note": f"并发批准 {i}", "expected_version": 1})
                          for i, lead in enumerate(leads)])
        self.assert_no_server_errors(responses)
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        self.assertEqual(self.count("SELECT COUNT(*) FROM admin_audit WHERE action = 'economy.batch_decide' AND status = 'succeeded' "
                                    "AND target_id = ?", (self.batch_id,)), 1)

    def test_two_executors_racing_pay_each_pet_once(self):
        lead = self.staff("race-lead", ["economy_lead"])
        lead.login_ok()
        approved = lead.post(f"/economy/batches/{self.batch_id}/decision", {"approve": True, "note": "批准后并发执行", "expected_version": 1})
        self.assertEqual(approved.status_code, 200, approved.text)
        version = approved.json()["version"]
        executors = [self.submitter, self.staff("race-batch-ops-2", ["economy_ops"])]
        executors[1].login_ok()
        balances = {pet_id: self.web.economy.wallet(pet_id).balance for pet_id in self.pet_ids}

        responses = race([lambda staff=staff: staff.post(f"/economy/batches/{self.batch_id}/execute", {"expected_version": version})
                          for staff in executors])
        self.assert_no_server_errors(responses)
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        for pet_id in self.pet_ids:
            self.assertEqual(self.count("SELECT COUNT(*) FROM economy_transactions WHERE idempotency_key = ?",
                                        (f"admin:batch:{self.batch_id}:{pet_id}",)), 1, pet_id)
            self.assertEqual(self.web.economy.wallet(pet_id).balance, balances[pet_id] + 10, pet_id)
        self.assertEqual(self.count("SELECT COUNT(*) FROM admin_audit WHERE action = 'economy.batch_execute' AND status = 'succeeded' "
                                    "AND target_id = ?", (self.batch_id,)), 1)


class RecoveryInterleavingTests(ConcurrencyBase):
    """照片恢复的三种并发结局，都来自**同一张明确失败的照片**。"""

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.illustrator = FakeIllustrator()
        self.web.illustrations.illustrator = self.illustrator
        self.player = self.user("race-photo-owner")
        self.player.adopt_and_move_in("adopt-lan")
        self.assertTrue(self.player.patch("/settings", {"generated_photos": True}).json()["generated_photos"])
        self.late = self.staff("race-sre-late", ["sre"])
        self.late.login_ok()
        self.colleague = self.staff("race-sre-first", ["sre"])
        self.colleague.login_ok()
        self.illustration_id = self.failed_photo()

    def failed_photo(self) -> str:
        self.illustrator.fail_reason = "rejected"  # 被当场拒绝＝确定没受理，可以恢复
        self.player.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.clock.advance(minutes=7)
        visit_id = self.player.get("/journey/map").json()["current_visit_id"]
        greet = next(a for a in self.player.get(f"/visits/{visit_id}").json()["activities"] if a["kind"] == "greet_resident")
        self.player.post(f"/visits/{visit_id}/actions", {"activity_id": greet["activity_id"]})
        self.clock.advance(seconds=5)
        self.web.illustrations.run_pending()
        with self.app.state.storage.connect() as conn:
            illustration_id = conn.execute("SELECT illustration_id FROM web_illustrations ORDER BY created_at DESC LIMIT 1").fetchone()[0]
        detail = self.late.get(f"/photos/{illustration_id}").json()
        self.assertEqual((detail["call_state"], detail["recoverable"]), ("failed", True), detail)
        return illustration_id

    def task(self) -> dict:
        with self.app.state.storage.connect() as conn:
            row = conn.execute("SELECT t.task_id, t.status, t.attempts, t.max_attempts FROM web_tasks t "
                               "JOIN web_illustrations i ON i.task_id = t.task_id WHERE i.illustration_id = ?",
                               (self.illustration_id,)).fetchone()
        return dict(row)

    def recover_outcomes(self) -> list[str]:
        # 按写入顺序（rowid）排：假时钟冻结时两条审计的 occurred_at 相同，audit_id 又是随机的，按它们排不代表先后。
        with self.app.state.storage.connect() as conn:
            return [r["outcome"] for r in conn.execute(
                "SELECT outcome FROM admin_audit WHERE action = 'task.recover' AND target_id = ? ORDER BY rowid",
                (self.illustration_id,))]

    def between_read_and_retry(self, interleave: Callable[[], None]):
        """包住只读的诊断查询：迟到的那位员工读完"失败"之后、真正去排任务之前，先让 interleave 跑完。"""
        diagnosis = self.app.state.admin.diagnosis
        original = diagnosis.photo
        state = {"fired": False}

        def read_then_interleave(illustration_id: str):
            seen = original(illustration_id)
            if not state["fired"]:
                state["fired"] = True
                interleave()
            return seen  # 迟到的那位拿着的是交错发生**之前**读到的那一份

        return mock.patch.object(diagnosis, "photo", side_effect=read_then_interleave)

    def test_already_queued_when_a_colleague_requeued_first(self):
        before = self.task()

        def colleague_recovers() -> None:
            first = self.colleague.post(f"/photos/{self.illustration_id}/recover", {"reason": "同事先点了恢复"})
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(first.json()["result"], "requeued")

        with self.between_read_and_retry(colleague_recovers):
            late = self.late.post(f"/photos/{self.illustration_id}/recover", {"reason": "我也点了恢复"})
        self.assertEqual(late.status_code, 200, late.text)
        self.assertEqual(late.json()["result"], "already_queued")
        self.assertFalse(late.json()["accepted"], "没有新建尝试就不能说已受理")
        self.assertIn("没有新建尝试", late.json()["note"])

        after = self.task()
        self.assertEqual(after["status"], "queued")
        self.assertEqual(after["max_attempts"], before["attempts"] + 1, "只放宽了一次次数：只排了一次")
        self.assertEqual(self.recover_outcomes(), ["requeued", "already_queued"])

    def test_stale_attempt_when_the_task_failed_again_in_between(self):
        before = self.task()

        def colleague_recovers_and_it_fails_again() -> None:
            first = self.colleague.post(f"/photos/{self.illustration_id}/recover", {"reason": "同事先点了恢复"})
            self.assertEqual(first.json()["result"], "requeued", first.text)
            self.clock.advance(seconds=5)
            self.web.illustrations.run_pending()  # 排回去的那一次又被当场拒绝了
            again = self.task()
            self.assertEqual((again["status"], again["attempts"]), ("failed", before["attempts"] + 1), again)

        with self.between_read_and_retry(colleague_recovers_and_it_fails_again):
            late = self.late.post(f"/photos/{self.illustration_id}/recover", {"reason": "我点的是上一次的失败"})
        self.assertEqual(late.status_code, 200, late.text)
        self.assertEqual(late.json()["result"], "stale_attempt")
        self.assertFalse(late.json()["accepted"])
        self.assertIn("更早那次失败", late.json()["note"])

        after = self.task()
        self.assertEqual(after["status"], "failed", "迟到的那一下不能把新的失败又排回去")
        self.assertEqual(after["attempts"], before["attempts"] + 1)
        self.assertEqual(self.recover_outcomes(), ["requeued", "stale_attempt"])

        # 看到新失败之后重新点，是合法的一次新恢复
        fresh = self.late.post(f"/photos/{self.illustration_id}/recover", {"reason": "刷新后看到新失败，再恢复一次"})
        self.assertEqual(fresh.status_code, 200, fresh.text)
        self.assertEqual(fresh.json()["result"], "requeued")

    def test_four_staff_recovering_at_once_requeue_it_exactly_once(self):
        crew = [self.staff(f"race-sre-{i}", ["sre"]) for i in range(4)]
        for member in crew:
            member.login_ok()
        before = self.task()
        responses = race([lambda m=m, i=i: m.post(f"/photos/{self.illustration_id}/recover", {"reason": f"一起点了恢复 {i}"})
                          for i, m in enumerate(crew)])
        self.assert_no_server_errors(responses)
        results = []
        for response in responses:
            if response.status_code == 200:
                results.append(response.json()["result"])
            else:  # 读的时候任务已经被别人排回去了：明确拒绝，不是再排一次
                self.assertEqual(response.json()["error"]["code"], "NOT_RECOVERABLE", response.text)
                results.append("not_recoverable")
        self.assertEqual(results.count("requeued"), 1, results)
        self.assertTrue(set(results) <= {"requeued", "already_queued", "not_recoverable"}, results)
        after = self.task()
        self.assertEqual(after["status"], "queued")
        self.assertEqual(after["max_attempts"], before["attempts"] + 1, "四个人一起点，只排了一次")


if __name__ == "__main__":
    unittest.main()
