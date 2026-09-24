"""第一阶段的写操作：权限、原因、影响预览、幂等、提交时版本检查、审计，以及**真的落到玩家侧**。

这里不接受"返回 200 就算数"：每一条都去玩家 API 或业务表验证结果，
并且验证 unknown 不被当成失败、不被自动重发、费用记录不被抹掉。
"""

from __future__ import annotations

import unittest

from admin_base import AdminTestBase
from web_base import LUNCH_UTC, FakeClock
from web_provider_fakes import FakeIllustrator


class AdminAccountCommandTests(AdminTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.player = self.user("target-owner")
        self.player.adopt_and_move_in("adopt-lan")
        self.agent = self.staff("support-cmd", ["support"])
        self.agent.login_ok()

    def test_freeze_preview_states_the_effects_before_acting(self):
        preview = self.agent.get(f"/users/{self.player.user_id}/freeze/preview").json()
        self.assertEqual(preview["current_status"], "active")
        self.assertEqual(preview["current_version"], 0)
        self.assertGreaterEqual(preview["active_sessions"], 1)
        self.assertEqual(preview["pets"], 1)
        self.assertTrue(any("家庭不会被解散" in line for line in preview["effects"]))

    def test_freeze_takes_effect_on_the_player_side_and_unfreeze_restores_login(self):
        self.assertEqual(self.player.get("/home").status_code, 200)
        response = self.agent.post(f"/users/{self.player.user_id}/freeze",
                                   {"frozen": True, "reason": "涉嫌滥用，等待核实", "expected_version": 0})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "frozen")
        self.assertGreaterEqual(body["revoked_sessions"], 1)

        # 1) 手上的会话立刻失效
        self.assert_web_error(self.player.get("/home"), 401, "SESSION_EXPIRED")
        # 2) 重新登录也进不来（不是只清了 cookie）
        relogin = self.player.client.post("/api/v1/web/auth/login",
                                          json={"username": "target-owner", "password": "longpassword1"})
        self.assert_web_error(relogin, 401, "INVALID_CREDENTIALS")
        # 3) 家庭与宠物都还在
        detail = self.agent.get(f"/users/{self.player.user_id}").json()
        self.assertEqual(detail["user"]["account_status"], "frozen")
        self.assertEqual(len(detail["households"][0]["pets"]), 1)

        # 解冻之后可以重新登录（旧会话不会自动恢复）
        unfreeze = self.agent.post(f"/users/{self.player.user_id}/freeze",
                                   {"frozen": False, "reason": "核实无误，恢复使用", "expected_version": body["version"]})
        self.assertEqual(unfreeze.status_code, 200, unfreeze.text)
        again = self.player.client.post("/api/v1/web/auth/login",
                                        json={"username": "target-owner", "password": "longpassword1"})
        self.assertEqual(again.status_code, 200, again.text)

    def test_freeze_is_idempotent_under_replay_and_rejects_stale_version(self):
        key = "freeze-replay-0001"
        first = self.agent.post(f"/users/{self.player.user_id}/freeze",
                                {"frozen": True, "reason": "重放测试", "expected_version": 0}, key=key)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertFalse(first.json()["replayed"])
        second = self.agent.post(f"/users/{self.player.user_id}/freeze",
                                 {"frozen": True, "reason": "重放测试", "expected_version": 0}, key=key)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertTrue(second.json()["replayed"])
        self.assertEqual(first.json()["version"], second.json()["version"], "重放不能再加一版")
        with self.app.state.storage.connect() as conn:
            rows = conn.execute("SELECT COUNT(*) AS n FROM admin_audit WHERE action = 'account.freeze'").fetchone()["n"]
        self.assertEqual(rows, 1, "重放不能写第二条审计")
        # 换一个幂等键、但拿旧版本号：提交时版本检查把它挡下
        stale = self.agent.post(f"/users/{self.player.user_id}/freeze",
                                {"frozen": False, "reason": "版本冲突测试", "expected_version": 0})
        self.assert_admin_error(stale, 409, "VERSION_CONFLICT")

    def test_reason_is_required_and_lands_in_audit(self):
        short = self.agent.post(f"/users/{self.player.user_id}/freeze", {"frozen": True, "reason": "x", "expected_version": 0})
        self.assertEqual(short.status_code, 422, short.text)
        self.agent.post(f"/users/{self.player.user_id}/freeze",
                        {"frozen": True, "reason": "反复举报待核实", "expected_version": 0})
        owner = self.owner()
        entry = next(e for e in owner.get("/audit?action=account.freeze").json()["entries"])
        self.assertEqual(entry["reason"], "反复举报待核实")
        self.assertEqual(entry["permission"], "account.freeze")
        self.assertEqual(entry["actor_username"], "support-cmd")
        self.assertEqual(entry["target_id"], self.player.user_id)

    def test_audit_is_append_only_at_the_database_level(self):
        self.agent.post(f"/users/{self.player.user_id}/revoke-sessions", {"reason": "换设备登录"})
        import sqlite3

        with self.app.state.storage.connect() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE admin_audit SET reason = '改过了'")
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM admin_audit")

    def assert_web_error(self, response, status: int, code: str) -> None:
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(response.json()["error"]["code"], code, response.text)


class AdminSwitchTests(AdminTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.illustrator = FakeIllustrator()
        self.web.illustrations.illustrator = self.illustrator
        self.sre = self.staff("sre-switch", ["sre"])
        self.sre.login_ok()

    def test_pausing_ai_calls_blocks_new_provider_calls_only(self):
        """测试环境里供应商是关的（meter 为 None），所以这里对一个真实的 ProviderMeter 实例
        装上**生产同一个**执行点函数 `guard_provider_meter`，再用 HTTP 改开关，验证它确实挡住调用。"""
        from app.web_admin.enforcement import guard_provider_meter
        from app.web_providers.meter import ProviderMeter

        meter = ProviderMeter(self.app.state.storage, caps={"image": 100, "llm": 100})
        guard_provider_meter(meter, self.app.state.admin.switches)
        self.assertTrue(meter.allow("image"), "暂停之前应当放行")
        response = self.sre.post("/switches/ai_calls", {"state": "paused", "reason": "供应商异常，先停新调用", "expected_version": 0})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["state"], "paused")
        self.assertFalse(meter.allow("image"), "暂停之后新的付费调用必须被挡住")
        self.assertFalse(meter.allow("llm"))
        resumed = self.sre.post("/switches/ai_calls", {"state": "active", "reason": "供应商恢复", "expected_version": 1})
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertTrue(meter.allow("image"))

    def test_switch_requires_permission_and_checks_version(self):
        reader = self.staff("auditor-switch", ["auditor"])
        reader.login_ok()
        self.assert_admin_error(reader.post("/switches/ai_calls", {"state": "paused", "reason": "无权限测试", "expected_version": 0}),
                                403, "FORBIDDEN")
        self.assert_admin_error(self.sre.post("/switches/ai_calls", {"state": "paused", "reason": "版本冲突", "expected_version": 7}),
                                409, "VERSION_CONFLICT")


class AdminPhotoRecoveryTests(AdminTestBase):
    """受控恢复：明确失败的可以恢复一次；结果未确认（unknown）的一律拒绝。"""

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.illustrator = FakeIllustrator()
        self.web.illustrations.illustrator = self.illustrator
        self.player = self.user("photo-owner")
        self.player.adopt_and_move_in("adopt-lan")
        self.assertTrue(self.player.patch("/settings", {"generated_photos": True}).json()["generated_photos"])
        self.sre = self.staff("sre-photo-cmd", ["sre"])
        self.sre.login_ok()

    def run_one_photo(self, fail_reason: str | None) -> str:
        self.illustrator.fail_reason = fail_reason
        self.player.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.clock.advance(minutes=7)
        visit_id = self.player.get("/journey/map").json()["current_visit_id"]
        greet = next(a for a in self.player.get(f"/visits/{visit_id}").json()["activities"] if a["kind"] == "greet_resident")
        self.player.post(f"/visits/{visit_id}/actions", {"activity_id": greet["activity_id"]})
        self.clock.advance(seconds=5)
        self.web.illustrations.run_pending()
        with self.app.state.storage.connect() as conn:
            row = conn.execute("SELECT illustration_id FROM web_illustrations ORDER BY created_at DESC LIMIT 1").fetchone()
        return row["illustration_id"]

    def test_unknown_is_not_failure_and_cannot_be_recovered(self):
        illustration_id = self.run_one_photo("timeout")  # 超时＝发出去了但没等到响应
        detail = self.sre.get(f"/photos/{illustration_id}").json()
        self.assertEqual(detail["status"], "failed")
        self.assertEqual(detail["call_state"], "unknown")
        self.assertFalse(detail["recoverable"])
        self.assertEqual(detail["reservations"][0]["status"], "unknown")
        charged_before = detail["reservations"][0]["actual_units"]

        response = self.sre.post(f"/photos/{illustration_id}/recover", {"reason": "用户说照片一直没出来"})
        error = self.assert_admin_error(response, 409, "NOT_RECOVERABLE")
        self.assertEqual(error["details"]["call_state"], "unknown")

        after = self.sre.get(f"/photos/{illustration_id}").json()
        self.assertEqual(after["task_status"], "failed", "被拒绝的恢复不能把任务排回去")
        self.assertEqual(after["reservations"][0]["status"], "unknown", "费用记录不能被改写")
        self.assertEqual(after["reservations"][0]["actual_units"], charged_before)
        owner = self.owner()
        denied = [e for e in owner.get("/audit?action=task.recover").json()["entries"] if e["status"] == "denied"]
        self.assertTrue(denied, "被拒绝的恢复也要留痕")

    def test_definite_failure_can_be_recovered_once_and_replay_creates_no_second_attempt(self):
        illustration_id = self.run_one_photo("rejected")  # 被当场拒绝＝确定没受理
        detail = self.sre.get(f"/photos/{illustration_id}").json()
        self.assertEqual(detail["call_state"], "failed")
        self.assertTrue(detail["recoverable"])

        key = "recover-once-0001"
        first = self.sre.post(f"/photos/{illustration_id}/recover", {"reason": "供应商已恢复，重排一次"}, key=key)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["result"], "requeued")
        self.assertTrue(first.json()["accepted"])
        self.assertEqual(self.sre.get(f"/photos/{illustration_id}").json()["task_status"], "queued")

        replay = self.sre.post(f"/photos/{illustration_id}/recover", {"reason": "供应商已恢复，重排一次"}, key=key)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()["replayed"])

        # 换一个幂等键再点一次：任务已经排回队列，没有"失败"可恢复，明确拒绝而不是再排一次
        again = self.sre.post(f"/photos/{illustration_id}/recover", {"reason": "再点一次看看"})
        error = self.assert_admin_error(again, 409, "NOT_RECOVERABLE")
        self.assertEqual(error["details"]["task_status"], "queued")
        with self.app.state.storage.connect() as conn:
            attempts = conn.execute("SELECT attempts FROM web_tasks WHERE task_id = ?",
                                    (first.json()["task_id"],)).fetchone()["attempts"]
        self.assertEqual(attempts, 1, "第二次点击不能又排一次尝试")

    # 说明：`illustrations.retry` 还会返回 already_queued / stale_attempt。走管理端时这两种只在
    # "读到 failed"与"条件更新"之间被别人插进来时才到得了，顺序执行产生不出来——
    # 它们的真触发用例在 test_admin_concurrency.py 的 RecoveryInterleavingTests（用钩子做确定性交错）。
    # 实测多线程硬撞 8 轮，already_queued 一次都没撞出来，所以那里用的是确定性交错而不是碰运气。


class AdminModerationTests(AdminTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.author = self.user("poster")
        self.author.adopt_and_move_in("adopt-lan", public_posts=True)
        self.reporter = self.user("reporter")
        self.moderator = self.staff("moderator-1", ["moderator"])
        self.moderator.login_ok()

    def public_post(self) -> str:
        self.author.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.clock.advance(minutes=7)
        self.run_background()
        self.clock.advance(minutes=30)
        self.run_background()
        with self.app.state.storage.connect() as conn:
            row = conn.execute("SELECT post_id FROM web_posts WHERE visibility = 'public' ORDER BY created_at DESC LIMIT 1").fetchone()
        self.assertIsNotNone(row, "这段旅程应当产生一条公开动态")
        return row["post_id"]

    def test_takedown_removes_it_from_the_player_feed_and_restore_brings_it_back(self):
        post_id = self.public_post()
        feed = self.reporter.get("/circle/feed").json()
        self.assertTrue(any(item["post_id"] == post_id for item in feed["items"]), feed)

        report = self.reporter.post("/reports", {"target_kind": "post", "target_id": post_id, "reason": "内容不适"})
        self.assertEqual(report.status_code, 204, report.text)
        queue = self.moderator.get("/reports").json()["reports"]
        self.assertTrue(any(r["target_id"] == post_id for r in queue), queue)
        self.assertTrue(any(r["target"]["text"] for r in queue if r["target_id"] == post_id))

        preview = self.moderator.get(f"/moderation/preview?target_kind=post&target_id={post_id}").json()
        self.assertTrue(preview["visible"])

        action = self.moderator.post("/moderation", {"target_kind": "post", "target_id": post_id,
                                                     "decision": "takedown", "reason": "违反公开内容规范"})
        self.assertEqual(action.status_code, 200, action.text)
        self.assertFalse(action.json()["visible"])
        feed_after = self.reporter.get("/circle/feed").json()
        self.assertFalse(any(item["post_id"] == post_id for item in feed_after["items"]), "下架后玩家不该再看到")

        # 举报记录与原文都还在（不是硬删除）
        with self.app.state.storage.connect() as conn:
            self.assertIsNotNone(conn.execute("SELECT 1 FROM web_reports WHERE target_id = ?", (post_id,)).fetchone())
            self.assertIsNotNone(conn.execute("SELECT text FROM web_posts WHERE post_id = ?", (post_id,)).fetchone()["text"])

        restore = self.moderator.post("/moderation", {"target_kind": "post", "target_id": post_id,
                                                      "decision": "restore", "reason": "复核后判定合规"})
        self.assertEqual(restore.status_code, 200, restore.text)
        feed_back = self.reporter.get("/circle/feed").json()
        self.assertTrue(any(item["post_id"] == post_id for item in feed_back["items"]))

    def test_same_operation_id_only_changes_things_once(self):
        post_id = self.public_post()
        key = "moderate-once-0001"
        body = {"target_kind": "post", "target_id": post_id, "decision": "takedown", "reason": "重复提交测试"}
        first = self.moderator.post("/moderation", body, key=key)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["changed"], 1)
        second = self.moderator.post("/moderation", body, key=key)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertTrue(second.json()["replayed"])
        with self.app.state.storage.connect() as conn:
            count = conn.execute("SELECT COUNT(*) AS n FROM admin_report_actions WHERE target_id = ?", (post_id,)).fetchone()["n"]
        self.assertEqual(count, 1, "同一个操作号只能留一条处理记录")


class AdminGrantTests(AdminTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.player = self.user("grant-owner")
        self.player.adopt_and_move_in("adopt-lan")
        self.ops = self.staff("economy-1", ["economy_ops"])
        self.ops.login_ok()

    def usage_snapshot(self) -> dict:
        with self.app.state.storage.connect() as conn:
            return {row["scope_key"]: int(row["used_units"]) for row in conn.execute("SELECT scope_key, used_units FROM web_budget_counters")}

    def test_grant_writes_only_the_game_ledger_and_replays_once(self):
        before_wallet = self.web.economy.wallet(self.player.pet_id).balance
        before_usage = self.usage_snapshot()
        preview = self.ops.get(f"/economy/grant/preview?pet_id={self.player.pet_id}&amount=20").json()
        self.assertEqual(preview["balance_before"], before_wallet)
        self.assertEqual(preview["balance_after"], before_wallet + 20)

        key = "grant-once-0001"
        body = {"pet_id": self.player.pet_id, "amount": 20, "reason": "照片没出来的补偿"}
        first = self.ops.post("/economy/grant", body, key=key)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertTrue(first.json()["applied"])
        self.assertEqual(first.json()["balance"], before_wallet + 20)

        replay = self.ops.post("/economy/grant", body, key=key)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()["replayed"])
        self.assertEqual(self.web.economy.wallet(self.player.pet_id).balance, before_wallet + 20, "重放不能再发一次")

        # 平台调用账一动不动
        self.assertEqual(self.usage_snapshot(), before_usage, "发游戏币不该影响平台 API 调用账")
        ledger = self.ops.get(f"/economy/ledger?pet_id={self.player.pet_id}").json()
        entry = next(t for t in ledger["transactions"] if t["idempotency_key"].endswith(key))
        self.assertEqual(entry["travel_coin"], 20)
        self.assertEqual(entry["source"], "admin.compensation")
        self.assertEqual(entry["operator"], self.ops.staff_id)

    def test_grant_is_capped_and_needs_permission(self):
        over = self.ops.post("/economy/grant", {"pet_id": self.player.pet_id, "amount": 5000, "reason": "超额测试"})
        self.assertEqual(over.status_code, 422, over.text)
        support = self.staff("support-no-grant", ["support"])
        support.login_ok()
        self.assert_admin_error(support.post("/economy/grant", {"pet_id": self.player.pet_id, "amount": 20, "reason": "越权测试"}),
                                403, "FORBIDDEN")


if __name__ == "__main__":
    unittest.main()
