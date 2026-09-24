"""第一条集成链：打工/旅程到期 → 工资、世界事件、行程完成与 outbox 同一个事务 → 提交后投递家庭消息等下游。

恰好一次按领域编号核对：工资按 web:job:<journey> 幂等键，家庭消息按 source_event_id，下游回执按 outbox 行。
"""

from __future__ import annotations

import threading
import unittest
from unittest import mock

from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class SettlementChainTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("chain-owner")
        self.owner.adopt_and_move_in("adopt-lan")

    def sql(self, query: str, params: tuple = ()) -> list:
        with self.app.state.storage.connect() as conn:
            return conn.execute(query, params).fetchall()

    def go_to_work(self) -> str:
        journey = self.owner.post("/journey/depart", {"destination_key": "work:florist"}).json()
        return journey["journey_id"]

    def wages(self, journey_id: str) -> list:
        return self.sql("SELECT amounts_json, created_at FROM economy_transactions WHERE idempotency_key = ?", (f"web:job:{journey_id}",))

    def messages(self, journey_id: str, key: str) -> list:
        return self.sql("SELECT user_id, channel, created_at FROM web_messages WHERE source_event_id = ?", (f"{journey_id}:{key}",))

    def events(self, journey_id: str) -> dict:
        return {r["event_key"]: r for r in self.sql("SELECT * FROM web_world_events WHERE journey_id = ?", (journey_id,))}

    def outbox(self, journey_id: str, key: str) -> list:
        return self.sql("SELECT consumer, status, attempts FROM web_outbox WHERE event_id = ?", (f"{journey_id}:{key}",))

    def test_wage_event_and_family_message_exactly_once_however_many_members_refresh(self) -> None:
        journey_id = self.go_to_work()
        household_id = self.owner.get("/onboarding").json()["households"][0]["household_id"]
        token = self.owner.post(f"/households/{household_id}/invites", {"role": "caregiver"}).json()["token"]
        member = self.user("chain-member")
        self.assertEqual(member.post("/invites/accept", {"token": token}).status_code, 200)
        self.clock.advance(hours=4)  # 收工、回家都过了
        for reader in (self.owner, member, self.owner, member):
            self.assertEqual(reader.get(f"/journey/map?pet_id={self.owner.pet_id}").status_code, 200)
            reader.get(f"/jobs?pet_id={self.owner.pet_id}")
        self.run_background()
        self.run_background()
        wages = self.wages(journey_id)
        self.assertEqual(len(wages), 1, "同一工作实例只入账一次")
        self.assertIn('"travel_coin": 16', wages[0]["amounts_json"])
        done = self.messages(journey_id, "work_done")
        self.assertEqual([(m["user_id"], m["channel"]) for m in done], [("*", "family")], "全家一条“打工结束”")
        self.assertEqual(len(self.messages(journey_id, "returned_home")), 1)
        rows = self.outbox(journey_id, "work_done")
        self.assertEqual(sorted(r["consumer"] for r in rows), sorted(self.web.journeys.consumers), "每个下游一行")
        self.assertEqual({r["status"] for r in rows}, {"delivered"})
        self.assertEqual(self.web.journeys.repo.get(journey_id).lifecycle, "completed")

    def test_family_view_ledger_and_ops_point_to_the_same_work(self) -> None:
        journey_id = self.go_to_work()
        self.clock.advance(hours=4)
        self.run_background()
        items = self.owner.get(f"/communicator/{self.owner.pet_id}/messages").json()["items"]
        done = [m for m in items if m.get("source_event_id") == f"{journey_id}:work_done"]
        self.assertEqual([(m["channel"], m["composed_by"]) for m in done], [("family", "event")], "家人看到的“打工结束”按事件编号恰好一条")
        self.assertTrue(all(m.get("source_event_id") in (None, "") or m["source_event_id"].startswith("jn-") for m in items), "只下发世界事件来源")
        bank = next(c for c in self.owner.get(f"/credentials?pet_id={self.owner.pet_id}").json() if c["kind"] == "bank_card")
        ledger = self.owner.get(f"/credentials/{bank['credential_id']}").json()["ledger"]
        wages = [e for e in ledger if e["type"] == "web_job_income"]
        self.assertEqual([(e["ref_kind"], e["ref_id"], e["delta"]) for e in wages], [("journey", journey_id, 16)], "银行卡流水指回这份工作")
        ops = self.client.get("/api/v1/web/ops/status").json()
        outbox = {row["consumer"]: row for row in ops["outbox"]}
        self.assertEqual(set(outbox), set(self.web.journeys.consumers))
        self.assertTrue(all(row["pending"] == 0 and row["dead_letter"] == 0 for row in outbox.values()), outbox)
        self.assertIn("running_expired", ops["tasks"])

    def test_the_world_scan_rotates_so_the_back_of_the_queue_is_not_starved(self) -> None:
        pets = [self.owner.pet_id]
        household_id = self.owner.get("/onboarding").json()["households"][0]["household_id"]
        for name in ("小豆", "小米"):
            created = self.owner.upload_pet(name, "cat", household_id=household_id)
            self.assertEqual(created.status_code, 201, created.text)
            pet_id = created.json()["pet_id"]
            self.assertEqual(self.owner.post("/onboarding/move-in", {"pet_id": pet_id}).status_code, 200)
            pets.append(pet_id)
        for pet_id in pets:
            self.assertEqual(self.owner.post(f"/journey/depart?pet_id={pet_id}", {"destination_key": "local:stroll"}).status_code, 200)
        self.clock.advance(hours=3)
        journeys = self.web.journeys
        for _ in range(len(pets)):  # 每轮只处理一段：靠游标轮转，三轮之后每只都结算到位
            journeys.advance_all(self.clock.now, limit=1)
            journeys.deliver_outbox(self.clock.now, lanes=("fast",))
        lifecycles = [journeys.repo.latest_for_pet(pet_id).lifecycle for pet_id in pets]
        self.assertEqual(lifecycles, ["completed"] * len(pets), "后排的宠物也轮得到，不会一直排不上")
        self.assertEqual(journeys.due_lag_seconds(self.clock.now), 0, "没有还没登记的到期事实")

    def test_a_failing_consumer_retries_alone_without_undoing_the_wage(self) -> None:
        journey_id = self.go_to_work()
        sink, lane = self.web.journeys.consumers["communicator"]
        failures = {"left": 1}

        class Flaky:
            def on_world_event(self, event) -> None:
                if event.kind == "work_done" and failures["left"]:
                    failures["left"] -= 1
                    raise RuntimeError("家庭来信暂时写不进去")
                sink.on_world_event(event)

        self.web.journeys.consumers["communicator"] = (Flaky(), lane)
        self.clock.advance(minutes=150)  # 收工了，还在回家路上
        self.run_background()
        self.assertEqual(len(self.wages(journey_id)), 1, "工资已经成立，不因下游失败回滚")
        self.assertIn("work_done", self.events(journey_id))
        self.assertEqual(self.messages(journey_id, "work_done"), [], "这一个下游失败了")
        statuses = {r["consumer"]: (r["status"], r["attempts"]) for r in self.outbox(journey_id, "work_done")}
        self.assertEqual(statuses["communicator"], ("pending", 1))
        self.assertEqual(statuses["social"], ("delivered", 0), "其他下游不受影响")
        self.run_background()  # 还没到退避时间：不重试
        self.assertEqual(self.messages(journey_id, "work_done"), [])
        self.clock.advance(minutes=1)
        self.run_background()
        self.run_background()
        self.assertEqual(len(self.messages(journey_id, "work_done")), 1, "重试后恰好一条")
        self.assertEqual(len(self.wages(journey_id)), 1)

    def test_a_lost_lease_is_not_recorded_as_a_consumer_failure(self) -> None:
        """租约在投递途中被接手：这**不是下游出错**，不能记成"这个下游失败了"。

        下游内部走 `unit_of_work`，租约失效是在那里抛出来的。原来这里被 `except Exception` 一把兜住，
        结果是：白写一条失败、白耗一次重试次数、还把这一行推进退避——而真正该做的是**中止本轮**，
        让这一行原样留给新任期。（B 在 fed3 日志 759 行提的同一类缺陷，MODULE-MAP 里这个文件归 I。）
        """
        from app.web_platform.lease import LeaseLost

        journey_id = self.go_to_work()
        sink, lane = self.web.journeys.consumers["communicator"]

        class Flaky:
            def on_world_event(self, event) -> None:
                if event.kind == "work_done":
                    raise RuntimeError("先真失败一次，造出一行等着重试的 outbox")
                sink.on_world_event(event)

        self.web.journeys.consumers["communicator"] = (Flaky(), lane)
        self.clock.advance(minutes=150)
        self.run_background()
        before = {r["consumer"]: (r["status"], r["attempts"]) for r in self.outbox(journey_id, "work_done")}
        self.assertEqual(before["communicator"], ("pending", 1), "前提：这一行确实失败过一次、在等重试")

        class LeaseGone:
            def on_world_event(self, event) -> None:
                if event.kind == "work_done":
                    raise LeaseLost("world", "这一轮的世界已经不归本进程推进了")
                sink.on_world_event(event)

        self.web.journeys.consumers["communicator"] = (LeaseGone(), lane)
        self.clock.advance(minutes=1)  # 过了退避时间，这一行会被重新领取

        with self.assertRaises(LeaseLost):
            self.web.journeys.deliver_outbox(self.clock.now, lanes=(lane,))

        after = {r["consumer"]: (r["status"], r["attempts"]) for r in self.outbox(journey_id, "work_done")}
        self.assertEqual(after["communicator"], before["communicator"],
                         f"租约失效不算下游失败：状态与重试次数都不许动（{before['communicator']} → {after['communicator']}）")
        self.assertEqual(len(self.wages(journey_id)), 1, "已经成立的工资不受影响")

    def test_settlement_commits_or_rolls_back_as_a_whole(self) -> None:
        journey_id = self.go_to_work()
        self.clock.advance(minutes=60)
        self.run_background()  # 已经到店开工
        self.clock.advance(minutes=90)
        journeys = self.web.journeys
        record = journeys.repo.get(journey_id)
        original = journeys.outbox.add_in

        def broken(conn, **kw):
            if kw["kind"] == "work_done":
                raise RuntimeError("登记 outbox 时出错")
            return original(conn, **kw)

        with mock.patch.object(journeys.outbox, "add_in", side_effect=broken):
            with self.assertRaises(RuntimeError):
                journeys._settle(record, self.clock.now)
        self.assertEqual(self.wages(journey_id), [], "整体回滚：工资不留半截")
        self.assertFalse({"visit_ended", "work_done", "returned_home"} & set(self.events(journey_id)), "同一批的其他事件也一起回滚")
        self.assertEqual(journeys.repo.get(journey_id).lifecycle, "active", "行程完成也回滚")
        settled = journeys._settle(record, self.clock.now)
        self.assertLessEqual({"visit_ended", "work_done"}, set(settled))
        self.assertEqual(len(self.wages(journey_id)), 1)
        self.assertEqual(journeys._settle(record, self.clock.now), [], "再结算一次什么也不新增")

    def test_api_and_worker_settling_at_the_same_moment_pay_once(self) -> None:
        journey_id = self.go_to_work()
        self.clock.advance(hours=4)
        journeys = self.web.journeys
        record = journeys.repo.get(journey_id)
        barrier = threading.Barrier(2)
        results: list[list[str]] = []

        def settle() -> None:
            barrier.wait()
            results.append(journeys._settle(record, self.clock.now))

        threads = [threading.Thread(target=settle) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertEqual(len(results), 2)
        self.assertEqual(set(results[0]) & set(results[1]), set(), "同一个事件只被一方登记")
        self.assertIn("work_done", set(results[0]) | set(results[1]))
        self.assertEqual(len(self.wages(journey_id)), 1)
        self.assertEqual(len(self.outbox(journey_id, "work_done")), len(journeys.consumers))

    def test_a_hanging_model_consumer_does_not_hold_up_settlement(self) -> None:
        journey_id = self.go_to_work()
        journeys = self.web.journeys
        release, entered = threading.Event(), threading.Event()

        class HangingGuide:  # 模拟写攻略时模型挂住
            def on_world_event(self, event) -> None:
                entered.set()
                release.wait(timeout=30)

        journeys.consumers["guides"] = (HangingGuide(), journeys.consumers["guides"][1])
        slow = threading.Thread(target=journeys.deliver_outbox, kwargs={"now": self.clock.now, "lanes": ("slow",)})
        slow.start()
        try:
            self.assertTrue(entered.wait(timeout=10), "慢通道正在等模型")
            self.clock.advance(hours=4)
            worker = threading.Thread(target=journeys.advance_all, args=(self.clock.now,))
            worker.start()
            worker.join(timeout=10)
            self.assertFalse(worker.is_alive(), "结算没有等模型")
            self.assertEqual(len(self.wages(journey_id)), 1)
            self.assertEqual(len(self.messages(journey_id, "work_done")), 1, "家庭来信走 fast 通道，已送到")
        finally:
            release.set()
            slow.join(timeout=30)

    def test_two_days_offline_settles_once_and_does_not_flood_messages(self) -> None:
        journey_id = self.go_to_work()
        self.clock.advance(hours=48)  # 全家关页两天，后台也停了
        self.run_background()
        self.run_background()
        self.assertEqual(len(self.wages(journey_id)), 1, "补齐时工资只记一次")
        events = self.events(journey_id)
        self.assertLessEqual({"departed", "visit_started", "visit_ended", "work_done", "returned_home"}, set(events), "该发生的事实一件不少")
        family = self.sql("SELECT source_event_id, COUNT(*) AS n FROM web_messages WHERE pet_id = ? AND channel = 'family' GROUP BY source_event_id",
                          (self.owner.pet_id,))
        self.assertTrue(all(row["n"] == 1 for row in family), "每件事一条来信，不会因为离线两天刷屏")
        self.assertLessEqual(len(family), len(events), "没有凭空补出两天的剧情")
        for key in ("work_done", "returned_home"):
            self.assertLess(events[key]["occurred_at"], events[key]["applied_at"], "有效时间是当时，登记时间是现在")
        self.assertEqual(self.web.journeys.repo.get(journey_id).lifecycle, "completed")
        self.assertEqual(self.web.journeys.due_lag_seconds(self.clock.now), 0, "补齐之后没有积压")

    def test_late_recovery_keeps_the_time_it_should_have_happened(self) -> None:
        journey_id = self.go_to_work()
        self.clock.advance(hours=6)  # 任务进程停了很久，也没人打开页面
        self.run_background()
        events = self.events(journey_id)
        visit = self.web.journeys.repo.visit_for_journey(journey_id)
        self.assertEqual(events["work_done"]["occurred_at"], events["visit_ended"]["occurred_at"])
        self.assertEqual(self.web.journeys.repo.get(journey_id).completed_at, self.web.journeys.repo.get(journey_id).completes_at)
        self.assertEqual(events["work_done"]["occurred_at"][:19], visit.ends_at.isoformat()[:19], "有效时间是原本收工的时刻")
        self.assertGreater(events["work_done"]["applied_at"], events["work_done"]["occurred_at"], "登记时间是实际补齐的时刻")
        self.assertEqual(self.wages(journey_id)[0]["created_at"][:19], visit.ends_at.isoformat()[:19])
        self.assertEqual(self.messages(journey_id, "work_done")[0]["created_at"][:19], visit.ends_at.isoformat()[:19])


if __name__ == "__main__":
    unittest.main()
