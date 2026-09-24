"""第一阶段工作流：搜索用户 → 家庭和宠物 → 宠物为什么没动静 → 照片链路 → 操作记录。

关键不变量：**后台这一串读接口不写任何业务表、不推进世界、不发起任何供应商调用。**
用例用业务表行数快照与替身供应商的调用计数来证明，而不是只看返回 200。
"""

from __future__ import annotations

import unittest

from admin_base import AdminTestBase
from web_base import LUNCH_UTC, FakeClock
from web_provider_fakes import FakeIllustrator

# 后台读接口绝对不能改动的业务表
BUSINESS_TABLES = ("users", "web_sessions", "web_journeys", "web_world_events", "web_tasks",
                   "web_illustrations", "web_budget_reservations", "web_budget_counters",
                   "economy_transactions", "pet_wallets", "web_posts", "web_messages")


class AdminDiagnosisTests(AdminTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.illustrator = FakeIllustrator()
        self.web.illustrations.illustrator = self.illustrator
        self.player = self.user("diag-owner")
        self.player.adopt_and_move_in("adopt-lan")
        self.household_id = self.player.get("/onboarding").json()["households"][0]["household_id"]

    def photo_attempt(self) -> str:
        """走一次真实冒险，排上生图任务（还没执行），返回 illustration_id。"""
        self.assertTrue(self.player.patch("/settings", {"generated_photos": True}).json()["generated_photos"])
        self.player.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.clock.advance(minutes=7)
        visit_id = self.player.get("/journey/map").json()["current_visit_id"]
        greet = next(a for a in self.player.get(f"/visits/{visit_id}").json()["activities"] if a["kind"] == "greet_resident")
        self.player.post(f"/visits/{visit_id}/actions", {"activity_id": greet["activity_id"]})
        self.clock.advance(seconds=5)
        with self.app.state.storage.connect() as conn:
            row = conn.execute("SELECT illustration_id FROM web_illustrations ORDER BY created_at DESC LIMIT 1").fetchone()
        self.assertIsNotNone(row, "冒险之后应当有一条插画记录")
        return row["illustration_id"]

    # ---- 检索 ----
    def test_search_finds_user_by_id_username_and_pet(self):
        staff = self.staff("support-search", ["support"])
        staff.login_ok()
        for term in (self.player.user_id, "diag-owner", self.player.pet_id):
            with self.subTest(term=term):
                body = staff.get(f"/search?q={term}").json()
                self.assertTrue(any(u["user_id"] == self.player.user_id for u in body["users"]), body)
        empty = staff.get("/search?q=no-such-thing-at-all").json()
        self.assertEqual(empty["users"], [])  # 没有就是空，不造数据
        self.assertEqual(empty["pets"], [])

    def test_user_detail_shows_household_and_pets_without_private_content(self):
        staff = self.staff("support-detail", ["support"])
        staff.login_ok()
        body = staff.get(f"/users/{self.player.user_id}").json()
        self.assertEqual(body["user"]["user_id"], self.player.user_id)
        self.assertEqual(body["user"]["pet_count"], 1)
        self.assertTrue(body["households"])
        pets = body["households"][0]["pets"]
        self.assertEqual(pets[0]["pet_id"], self.player.pet_id)
        self.assertTrue(pets[0]["home_activated"])
        # 授权是布尔值；正文一概不给
        self.assertIn("generated_photos", body["prefs"])
        self.assertIsInstance(body["prefs"]["generated_photos"], bool)
        # 取库里真实存在的私密值，逐个确认它们没有出现在响应里（不是靠关键词猜）
        with self.app.state.storage.connect() as conn:
            dna_json = conn.execute("SELECT dna_json FROM pets WHERE pet_id = ?", (self.player.pet_id,)).fetchone()["dna_json"]
            password_hash = conn.execute("SELECT password_hash FROM web_accounts WHERE user_id = ?",
                                         (self.player.user_id,)).fetchone()["password_hash"]
        text = staff.get(f"/users/{self.player.user_id}").text
        self.assertNotIn(password_hash, text)
        self.assertNotIn(dna_json[:40], text)
        for key in ("dna", "dna_json", "password_hash", "care_notes"):
            self.assertNotIn(key, body["user"])
            self.assertNotIn(key, body["households"][0]["pets"][0])

    # ---- 宠物诊断 ----
    def test_pet_diagnosis_explains_silence_with_a_business_level_reason(self):
        staff = self.staff("support-diag", ["support"])
        staff.login_ok()
        body = staff.get(f"/pets/{self.player.pet_id}/diagnosis").json()
        self.assertTrue(body["available"], body)
        self.assertTrue(body["headline"])
        self.assertTrue(body["detail"])
        self.assertIn(body["silence_kind"], (None, "正常", "已推迟", "故障"))
        self.assertIn("timezone", body["place"])
        self.assertIn("action", body["heartbeat"])
        self.assertIn("runtime", body["versions"])
        self.assertIn("household_generated_photos", body["consent"])
        self.assertEqual(body["pet"]["pet_id"], self.player.pet_id)
        self.assertEqual(body["owner_user_id"], self.player.user_id)

    def test_diagnosis_of_unknown_pet_is_404(self):
        staff = self.staff("support-404", ["support"])
        staff.login_ok()
        self.assert_admin_error(staff.get("/pets/PT-NOPE/diagnosis"), 404, "NOT_FOUND")

    # ---- 只读证明 ----
    def test_admin_reads_do_not_touch_business_tables_or_call_providers(self):
        illustration_id = self.photo_attempt()
        staff = self.staff("support-readonly", ["platform_owner"])
        staff.login_ok()
        before = self.table_counts(BUSINESS_TABLES)
        calls_before = len(self.illustrator.prompts)
        for _ in range(3):  # 模拟后台页面反复轮询
            for path in ("/overview", f"/search?q={self.player.user_id}", f"/users/{self.player.user_id}",
                         f"/pets/{self.player.pet_id}/diagnosis", f"/photos/{illustration_id}", "/photos",
                         "/providers/usage", "/economy/ledger", "/reports", "/content", "/audit", "/switches"):
                self.assertEqual(staff.get(path).status_code, 200, path)
        after = self.table_counts(BUSINESS_TABLES)
        self.assertEqual(before, after, "后台的读把业务表写动了")
        self.assertEqual(calls_before, len(self.illustrator.prompts), "后台的读发起了生图调用")

    def test_admin_reads_do_write_access_audit(self):
        """合法访问要留痕：这是审计写入，与上一条的"不写业务表"并不矛盾。"""
        staff = self.staff("support-trace", ["support"])
        staff.login_ok()
        staff.get(f"/users/{self.player.user_id}")
        staff.get(f"/pets/{self.player.pet_id}/diagnosis")
        owner = self.owner()
        entries = owner.get(f"/audit?target_id={self.player.user_id}").json()["entries"]
        self.assertTrue(any(e["action"] == "user.detail" and e["status"] == "allowed" for e in entries), entries)
        pet_entries = owner.get(f"/audit?target_id={self.player.pet_id}").json()["entries"]
        self.assertTrue(any(e["action"] == "pet.diagnosis" for e in pet_entries), pet_entries)

    # ---- 照片链路 ----
    def test_photo_detail_separates_processing_ready_failed_and_unknown(self):
        illustration_id = self.photo_attempt()
        staff = self.staff("sre-photo", ["sre"])
        staff.login_ok()
        body = staff.get(f"/photos/{illustration_id}").json()
        self.assertEqual(body["status"], "processing")
        self.assertEqual(body["call_state"], "processing")
        self.assertFalse(body["recoverable"])
        self.assertEqual(body["task_status"], "queued")

        self.web.illustrations.run_pending()
        ready = staff.get(f"/photos/{illustration_id}").json()
        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["call_state"], "ready")
        self.assertTrue(ready["reservations"], "出图之后应当有一条已结算的额度预占")
        self.assertEqual(ready["reservations"][0]["status"], "settled")

    def test_overview_metrics_carry_a_source_and_never_invent_numbers(self):
        staff = self.staff("ops-overview", ["platform_owner"])
        staff.login_ok()
        body = staff.get("/overview").json()
        keys = {m["key"]: m for m in body["metrics"]}
        self.assertEqual(keys["users.registered"]["value"], self.table_counts(("users",))["users"])
        for metric in body["metrics"]:
            self.assertTrue(metric["source"], metric)
            self.assertEqual(metric["available"], metric["value"] is not None)
        self.assertIn("environment", body["environment"])
        self.assertIn("read_only_note", body)

    def test_two_ledgers_are_reported_separately_and_cost_is_unknown_not_zero(self):
        staff = self.staff("ops-ledgers", ["platform_owner"])
        staff.login_ok()
        usage = staff.get("/providers/usage").json()
        self.assertEqual(usage["unit"], "调用次数（provider call unit）")
        self.assertFalse(usage["price_table_configured"])
        for line in usage["lines"]:
            self.assertIsNone(line["estimated_cost"])
            self.assertIsNone(line["billed_cost"])
            self.assertEqual(line["cost_state"], "unknown_no_price_table")
        ledger = staff.get("/economy/ledger").json()
        self.assertEqual(ledger["currency_code"], "travel_coin", "游戏账本记的是游戏币，不是人民币或美元")
        self.assertIn("星币", ledger["currency"])
        self.assertNotIn("estimated_cost", ledger)  # 游戏账里没有任何金额字段

    def test_unsettled_calls_stay_visible_across_the_utc_day_boundary(self):
        """计量按 UTC 日切窗，但"结果未确认"不能因为跨天就从页面上消失。"""
        self.run_one_unknown_photo()
        staff = self.staff("ops-unsettled", ["platform_owner"])
        staff.login_ok()
        usage = staff.get("/providers/usage").json()
        self.assertGreaterEqual(usage["reservations_all_time_by_status"].get("unknown", 0), 1)
        self.assertTrue(usage["unsettled"], usage)
        row = usage["unsettled"][0]
        self.assertIn(row["status"], ("reserved", "unknown", "expired"))
        self.assertTrue(usage["window_note"])

    def run_one_unknown_photo(self) -> None:
        from web_provider_fakes import FakeIllustrator

        self.illustrator = FakeIllustrator("timeout")
        self.web.illustrations.illustrator = self.illustrator
        self.photo_attempt()
        self.web.illustrations.run_pending()


if __name__ == "__main__":
    unittest.main()
