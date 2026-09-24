"""批量游戏补偿：额度没配就关着、影响预览、双人审批、执行逐条留痕、重放不重复发。"""

from __future__ import annotations

import unittest

from admin_base import AdminTestBase


class BatchGrantTests(AdminTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.submitter = self.staff("batch-ops", ["economy_ops"])
        self.submitter.login_ok()
        self.approver = self.staff("batch-lead", ["economy_lead"])
        self.approver.login_ok()
        self.players = []
        for index, name in enumerate(("batch-a", "batch-b", "batch-c")):
            player = self.user(name)
            player.adopt_and_move_in(["adopt-lan", "adopt-doudou", "adopt-arong"][index])
            self.players.append(player)
        self.pet_ids = [p.pet_id for p in self.players]

    def enable_limits(self, *, recipients: int = 10, per_pet: int = 50, total: int = 500) -> None:
        from app.web_admin.batches import BatchLimits

        self.app.state.admin.batches.limits = BatchLimits(recipients, per_pet, total)

    def wallets(self) -> dict[str, int]:
        return {pet_id: self.web.economy.wallet(pet_id).balance for pet_id in self.pet_ids}

    def usage_snapshot(self) -> dict:
        with self.app.state.storage.connect() as conn:
            return {row["scope_key"]: int(row["used_units"]) for row in conn.execute("SELECT scope_key, used_units FROM web_budget_counters")}

    # ---- 额度未配置 ----
    def test_capability_is_off_until_limits_are_configured(self):
        capability = self.submitter.get("/economy/batches/capability").json()
        self.assertFalse(capability["enabled"])
        self.assertIsNone(capability["max_recipients"])
        self.assertIn("没有配置", capability["note"])

        for path, body in (("/economy/batches/preview", {"pet_ids": self.pet_ids, "amount_per_pet": 10}),
                           ("/economy/batches", {"title": "试试", "reason": "额度未配测试", "pet_ids": self.pet_ids, "amount_per_pet": 10})):
            with self.subTest(path=path):
                error = self.assert_admin_error(self.submitter.post(path, body), 503, "NOT_CONFIGURED")
                self.assertEqual(error["details"]["reason"], "limits_not_configured")

    # ---- 权限分离 ----
    def test_submit_and_approve_need_different_permissions(self):
        self.enable_limits()
        self.assert_admin_error(
            self.approver.post("/economy/batches", {"title": "越权提交", "reason": "审批人不能提交", "pet_ids": self.pet_ids, "amount_per_pet": 10}),
            403, "FORBIDDEN")
        submitted = self.submitter.post("/economy/batches",
                                        {"title": "照片延迟补偿", "reason": "上周照片积压的补偿", "pet_ids": self.pet_ids, "amount_per_pet": 10})
        self.assertEqual(submitted.status_code, 201, submitted.text)
        batch_id = submitted.json()["batch_id"]
        self.assert_admin_error(
            self.submitter.post(f"/economy/batches/{batch_id}/decision", {"approve": True, "note": "自己批自己", "expected_version": 1}),
            403, "FORBIDDEN")

    def test_submitter_cannot_approve_even_with_both_permissions(self):
        """平台负责人两条权限都有，也不能批自己提的批次（双人原则）。"""
        self.enable_limits()
        owner = self.owner()
        submitted = owner.post("/economy/batches", {"title": "负责人自提", "reason": "双人原则测试", "pet_ids": self.pet_ids[:1], "amount_per_pet": 5})
        self.assertEqual(submitted.status_code, 201, submitted.text)
        batch_id = submitted.json()["batch_id"]
        error = self.assert_admin_error(
            owner.post(f"/economy/batches/{batch_id}/decision", {"approve": True, "note": "我自己批", "expected_version": 1}),
            403, "FORBIDDEN")
        self.assertEqual(error["details"]["reason"], "self_approval")
        entries = owner.get("/audit?action=economy.batch_decide").json()["entries"]
        self.assertTrue(any(e["status"] == "denied" and e["outcome"] == "self_approval" for e in entries), entries)

    # ---- 预览与上限 ----
    def test_preview_shows_effects_and_does_not_write(self):
        self.enable_limits()
        before = self.wallets()
        preview = self.submitter.post("/economy/batches/preview", {"pet_ids": self.pet_ids, "amount_per_pet": 20}).json()
        self.assertEqual(preview["eligible_count"], 3)
        self.assertEqual(preview["total_amount"], 60)
        for row in preview["recipients"]:
            self.assertTrue(row["eligible"])
            self.assertEqual(row["balance_after"], row["balance_before"] + 20)
        self.assertTrue(any("平台 API 调用账" in line for line in preview["effects"]))
        self.assertEqual(self.wallets(), before, "预览不能写任何东西")

    def test_limits_are_enforced(self):
        self.enable_limits(recipients=2, per_pet=10, total=100)
        too_many = self.submitter.post("/economy/batches/preview", {"pet_ids": self.pet_ids, "amount_per_pet": 5})
        self.assertEqual(too_many.status_code, 422, too_many.text)
        too_rich = self.submitter.post("/economy/batches/preview", {"pet_ids": self.pet_ids[:1], "amount_per_pet": 40})
        self.assertEqual(too_rich.status_code, 422, too_rich.text)

    def test_frozen_caregiver_is_skipped_in_preview_and_execution(self):
        self.enable_limits()
        support = self.staff("batch-support", ["support"])
        support.login_ok()
        frozen = support.post(f"/users/{self.players[1].user_id}/freeze",
                              {"frozen": True, "reason": "批量补偿跳过测试", "expected_version": 0})
        self.assertEqual(frozen.status_code, 200, frozen.text)

        preview = self.submitter.post("/economy/batches/preview", {"pet_ids": self.pet_ids, "amount_per_pet": 10}).json()
        self.assertEqual(preview["eligible_count"], 2)
        self.assertEqual(preview["skipped_count"], 1)
        skipped = next(row for row in preview["recipients"] if not row["eligible"])
        self.assertEqual(skipped["pet_id"], self.pet_ids[1])
        self.assertIn("冻结", skipped["reason"])

        before = self.wallets()
        batch_id = self.run_batch(self.pet_ids, 10)
        after = self.wallets()
        self.assertEqual(after[self.pet_ids[1]], before[self.pet_ids[1]], "被冻结的那只不发")
        self.assertEqual(after[self.pet_ids[0]], before[self.pet_ids[0]] + 10)
        detail = self.submitter.get(f"/economy/batches/{batch_id}").json()
        self.assertEqual(detail["batch"]["applied_count"], 2)
        self.assertEqual(detail["batch"]["skipped_count"], 0, "提交时就被剔除的不进名单")
        self.assertEqual({row["pet_id"] for row in detail["items"]}, {self.pet_ids[0], self.pet_ids[2]})

    # ---- 完整闭环 ----
    def run_batch(self, pet_ids, amount, *, title: str = "批量补偿") -> str:
        submitted = self.submitter.post("/economy/batches",
                                        {"title": title, "reason": "照片积压的统一补偿", "pet_ids": pet_ids, "amount_per_pet": amount})
        self.assertEqual(submitted.status_code, 201, submitted.text)
        batch_id = submitted.json()["batch_id"]
        decided = self.approver.post(f"/economy/batches/{batch_id}/decision",
                                     {"approve": True, "note": "核对过名单，同意", "expected_version": 1})
        self.assertEqual(decided.status_code, 200, decided.text)
        executed = self.submitter.post(f"/economy/batches/{batch_id}/execute", {"expected_version": decided.json()["version"]})
        self.assertEqual(executed.status_code, 200, executed.text)
        return batch_id

    def test_full_cycle_writes_only_the_game_ledger(self):
        self.enable_limits()
        before = self.wallets()
        usage_before = self.usage_snapshot()

        submitted = self.submitter.post("/economy/batches",
                                        {"title": "照片延迟补偿", "reason": "上周照片积压的补偿", "pet_ids": self.pet_ids, "amount_per_pet": 15})
        self.assertEqual(submitted.status_code, 201, submitted.text)
        batch_id = submitted.json()["batch_id"]
        self.assertIn("还没有发出任何星币", submitted.json()["note"])
        self.assertEqual(self.wallets(), before, "提交不发钱")

        decided = self.approver.post(f"/economy/batches/{batch_id}/decision",
                                     {"approve": True, "note": "名单核对无误", "expected_version": 1})
        self.assertEqual(decided.status_code, 200, decided.text)
        self.assertEqual(decided.json()["status"], "approved")
        self.assertEqual(self.wallets(), before, "批准也还没发钱")

        executed = self.submitter.post(f"/economy/batches/{batch_id}/execute",
                                       {"expected_version": decided.json()["version"], "note": "审批通过，按名单执行"})
        self.assertEqual(executed.status_code, 200, executed.text)
        self.assertFalse(executed.json()["replayed"])
        with self.app.state.storage.connect() as conn:
            audit = conn.execute("SELECT reason, changes_json FROM admin_audit WHERE action = 'economy.batch_execute' "
                                 "AND target_id = ?", (batch_id,)).fetchone()
        self.assertEqual(audit["reason"], "上周照片积压的补偿", "审计里的业务原因仍是提交时那一条")
        self.assertIn("审批通过，按名单执行", audit["changes_json"], "执行人自己的说明另记在变更摘要里")
        after = self.wallets()
        for pet_id in self.pet_ids:
            self.assertEqual(after[pet_id], before[pet_id] + 15)
        self.assertEqual(self.usage_snapshot(), usage_before, "发游戏币不该影响平台 API 调用账")

        ledger = self.submitter.get(f"/economy/ledger?pet_id={self.pet_ids[0]}").json()
        entry = next(t for t in ledger["transactions"] if t["idempotency_key"].startswith(f"admin:batch:{batch_id}"))
        self.assertEqual(entry["travel_coin"], 15)
        self.assertEqual(entry["source"], "admin.compensation.batch")
        self.assertEqual(entry["operator"], self.submitter.staff_id)

    def test_executing_twice_does_not_pay_twice(self):
        self.enable_limits()
        before = self.wallets()
        batch_id = self.run_batch(self.pet_ids, 12)
        paid = self.wallets()
        detail = self.submitter.get(f"/economy/batches/{batch_id}").json()

        again = self.submitter.post(f"/economy/batches/{batch_id}/execute", {"expected_version": detail["batch"]["version"]})
        self.assertEqual(again.status_code, 200, again.text)
        self.assertTrue(again.json()["replayed"])
        self.assertEqual(self.wallets(), paid, "重复执行不能再发一次")
        for pet_id in self.pet_ids:
            self.assertEqual(paid[pet_id], before[pet_id] + 12)

    def test_rejected_batch_cannot_be_executed(self):
        self.enable_limits()
        before = self.wallets()
        submitted = self.submitter.post("/economy/batches",
                                        {"title": "驳回测试", "reason": "这一批不该发", "pet_ids": self.pet_ids, "amount_per_pet": 10})
        batch_id = submitted.json()["batch_id"]
        decided = self.approver.post(f"/economy/batches/{batch_id}/decision",
                                     {"approve": False, "note": "名单有问题，驳回", "expected_version": 1})
        self.assertEqual(decided.status_code, 200, decided.text)
        self.assertEqual(decided.json()["status"], "rejected")
        blocked = self.submitter.post(f"/economy/batches/{batch_id}/execute", {"expected_version": decided.json()["version"]})
        self.assert_admin_error(blocked, 409, "CONFLICT")
        self.assertEqual(self.wallets(), before)

    def test_stale_version_is_rejected(self):
        self.enable_limits()
        submitted = self.submitter.post("/economy/batches",
                                        {"title": "版本冲突", "reason": "版本检查测试", "pet_ids": self.pet_ids[:1], "amount_per_pet": 10})
        batch_id = submitted.json()["batch_id"]
        self.assert_admin_error(
            self.approver.post(f"/economy/batches/{batch_id}/decision", {"approve": True, "note": "拿了旧版本号", "expected_version": 99}),
            409, "VERSION_CONFLICT")

    def test_every_step_is_audited(self):
        self.enable_limits()
        batch_id = self.run_batch(self.pet_ids[:2], 8)
        owner = self.owner()
        entries = owner.get(f"/audit?target_id={batch_id}").json()["entries"]
        actions = {e["action"]: e for e in entries}
        self.assertEqual(set(actions), {"economy.batch_submit", "economy.batch_decide", "economy.batch_execute"})
        self.assertEqual(actions["economy.batch_submit"]["actor_username"], "batch-ops")
        self.assertEqual(actions["economy.batch_decide"]["actor_username"], "batch-lead")
        self.assertEqual(actions["economy.batch_execute"]["changes"]["applied"], 2)
        self.assertEqual(actions["economy.batch_execute"]["changes"]["currency"], "travel_coin")


if __name__ == "__main__":
    unittest.main()
