"""方案 §7 工作流 #4「客服补偿一次游戏奖励」与方案 §5「游戏账本 / 平台调用账两个独立标签」。

补偿这条路在第一批就有后端与用例，这里补的是**工作流本身**：从宠物出发 → 看影响 → 填原因 →
发 20 星币 → 在这只宠物的游戏账本上看到那一条 → 同一个操作号重试不会再入一次 →
这只宠物的平台调用账前后一模一样。

另外钉住两件新东西：
- 预览与提交用同一套校验（不存在的宠物、超限金额，预览也要拒）；
- 宠物的平台调用账只按 `subject_scope = pet:<id>` 归集，前缀比较不受宠物号里下划线的影响。
"""

from __future__ import annotations

import unittest

from admin_base import AdminTestBase

from app.web_platform.budget import BudgetLedger, BudgetLimit


class PetGrantWorkflowTests(AdminTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.player = self.user("ledger-owner")
        self.player.adopt_and_move_in("adopt-lan")
        self.ops = self.staff("ledger-economy", ["economy_ops"])
        self.ops.login_ok()
        self.auditor = self.staff("ledger-auditor", ["auditor"])
        self.auditor.login_ok()

    def calls(self) -> dict:
        response = self.auditor.get(f"/pets/{self.player.pet_id}/calls")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_workflow_4_grant_twenty_coins_from_the_pet_page(self):
        pet_id = self.player.pet_id
        calls_before = self.calls()
        ledger_before = self.ops.get(f"/economy/ledger?pet_id={pet_id}").json()

        preview = self.ops.get(f"/economy/grant/preview?pet_id={pet_id}&amount=20")
        self.assertEqual(preview.status_code, 200, preview.text)
        preview = preview.json()
        self.assertEqual(preview["pet_name"], self.web.pets.profile(pet_id).name)
        self.assertEqual(preview["balance_after"] - preview["balance_before"], 20)
        self.assertFalse(preview["caregiver_frozen"])
        self.assertTrue(any("平台 API 调用账" in line for line in preview["effects"]))

        key = "op-workflow4-0001"
        body = {"pet_id": pet_id, "amount": 20, "reason": "照片一直没出来，补偿 20 星币"}
        first = self.ops.post("/economy/grant", body, key=key)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertTrue(first.json()["applied"])
        self.assertFalse(first.json()["replayed"])

        # 结果没确认时界面会用**同一个操作号**重试：拿回第一次的结果，不再入账
        retry = self.ops.post("/economy/grant", body, key=key)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertTrue(retry.json()["replayed"])
        self.assertEqual(retry.json()["balance"], preview["balance_before"] + 20)

        ledger = self.ops.get(f"/economy/ledger?pet_id={pet_id}").json()
        new_rows = [t for t in ledger["transactions"]
                    if t["tx_id"] not in {row["tx_id"] for row in ledger_before["transactions"]}]
        self.assertEqual(len(new_rows), 1, "同一个操作号只能留下一条入账")
        self.assertEqual(new_rows[0]["travel_coin"], 20)
        self.assertEqual(new_rows[0]["source"], "admin.compensation")
        self.assertEqual(new_rows[0]["idempotency_key"], f"admin:grant:{key}")
        self.assertEqual(self.web.economy.wallet(pet_id).balance, preview["balance_before"] + 20)

        # 另一本账：这只宠物的平台调用账前后一模一样
        calls_after = self.calls()
        for field in ("counters_today", "reservations_by_status", "reservations"):
            self.assertEqual(calls_after[field], calls_before[field], f"补偿星币不该碰平台调用账：{field}")

    def test_preview_rejects_what_the_grant_would_reject(self):
        self.assert_admin_error(self.ops.get("/economy/grant/preview?pet_id=pet-does-not-exist&amount=20"), 404, "NOT_FOUND")
        for amount in (0, -5, 201):
            with self.subTest(amount=amount):
                error = self.assert_admin_error(
                    self.ops.get(f"/economy/grant/preview?pet_id={self.player.pet_id}&amount={amount}"), 422, "VALIDATION_FAILED")
                self.assertEqual(error["details"]["field"], "amount")

    def test_preview_warns_when_the_caregiver_is_frozen(self):
        support = self.staff("ledger-support", ["support"])
        support.login_ok()
        frozen = support.post(f"/users/{self.player.user_id}/freeze",
                              {"frozen": True, "reason": "冻结后再看补偿预览", "expected_version": 0})
        self.assertEqual(frozen.status_code, 200, frozen.text)
        preview = self.ops.get(f"/economy/grant/preview?pet_id={self.player.pet_id}&amount=20").json()
        self.assertTrue(preview["caregiver_frozen"])
        self.assertEqual(preview["caregiver_user_id"], self.player.user_id)
        self.assertIn("冻结", preview["effects"][0])


class PetCallLedgerTests(AdminTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.player = self.user("calls-owner")
        self.player.adopt_and_move_in("adopt-lan")
        self.other = self.user("calls-other")
        self.other.adopt_and_move_in("adopt-doudou")
        self.sre = self.staff("calls-sre", ["sre"])
        self.sre.login_ok()
        self.ledger = BudgetLedger(self.app.state.storage)

    def reserve(self, pet_id: str, operation_id: str):
        return self.ledger.reserve(operation_id, provider="image", purpose="illustration", subject_scope=f"pet:{pet_id}",
                                   limits=[BudgetLimit(f"pet:{pet_id}:illustration", 5)])

    def test_only_this_pets_calls_with_status_and_unknown_cost(self):
        mine = self.reserve(self.player.pet_id, "illustration:calls-1:1")
        self.ledger.settle(mine, "succeeded", actual_units=1)
        self.reserve(self.player.pet_id, "illustration:calls-2:1")      # 还在途
        self.reserve(self.other.pet_id, "illustration:calls-other:1")   # 别的宠物

        view = self.sre.get(f"/pets/{self.player.pet_id}/calls").json()
        self.assertEqual(view["subject_scope"], f"pet:{self.player.pet_id}")
        self.assertEqual({r["operation_id"] for r in view["reservations"]},
                         {"illustration:calls-1:1", "illustration:calls-2:1"}, "别的宠物的调用不能混进来")
        self.assertEqual(view["reservations_by_status"], {"settled": 1, "reserved": 1})
        for row in view["reservations"]:
            self.assertIsNone(row["estimated_cost"], "没有价格表，费用是未知，不是 0")
            self.assertIsNone(row["billed_cost"])
            self.assertEqual(row["cost_state"], "unknown_no_price_table")
        counter = next(c for c in view["counters_today"] if c["scope_key"] == f"pet:{self.player.pet_id}:illustration")
        self.assertEqual((counter["used_units"], counter["inflight_units"]), (1, 1), "今日用量直接取账本自己的计数器")

    def copy_counter(self, source_key: str, new_key: str) -> None:
        with self.app.state.storage.connect() as conn:
            conn.execute("INSERT INTO web_budget_counters (window_key, scope_key, used_units, inflight_units, updated_at) "
                         "SELECT window_key, ?, 9, 0, updated_at FROM web_budget_counters WHERE scope_key = ?",
                         (new_key, source_key))

    def test_counter_prefix_does_not_catch_a_longer_pet_id(self):
        pet_id = self.player.pet_id
        self.reserve(pet_id, "illustration:calls-prefix:1")
        longer = f"pet:{pet_id}0:illustration"   # 另一只宠物，号码恰好以这只的号码开头
        self.copy_counter(f"pet:{pet_id}:illustration", longer)
        keys = {c["scope_key"] for c in self.sre.get(f"/pets/{pet_id}/calls").json()["counters_today"]}
        self.assertIn(f"pet:{pet_id}:illustration", keys)
        self.assertNotIn(longer, keys, "前缀带着结尾的冒号比较，号码更长的另一只宠物不能被算进来")

    def test_counter_prefix_is_not_a_like_pattern(self):
        """钉的是查询本身：现在的宠物号形如 `PJ-XXXXXXXX`，不含 `_` / `%`，所以这条走不到路由上
        （路由会先因为宠物不存在回 404）。直接调服务方法，证明前缀是精确比较、不是 LIKE 通配——
        以后宠物号格式变了，这里不会悄悄变成"把长得像的宠物也算进来"。"""
        synthetic = "pet_a1"
        self.ledger.reserve("illustration:synthetic:1", provider="image", purpose="illustration",
                            subject_scope=f"pet:{synthetic}", limits=[BudgetLimit(f"pet:{synthetic}:illustration", 5)])
        lookalike = f"pet:{synthetic.replace('_', 'X')}:illustration"
        self.copy_counter(f"pet:{synthetic}:illustration", lookalike)
        view = self.app.state.admin.overview.pet_calls(synthetic)
        keys = {c["scope_key"] for c in view["counters_today"]}
        self.assertEqual(keys, {f"pet:{synthetic}:illustration"}, "LIKE 会把下划线当通配符；这里必须是精确前缀")

    def test_two_ledgers_two_permissions(self):
        economy = self.staff("calls-economy", ["economy_ops"])
        economy.login_ok()
        self.assert_admin_error(economy.get(f"/pets/{self.player.pet_id}/calls"), 403, "FORBIDDEN")
        self.assertEqual(economy.get(f"/economy/ledger?pet_id={self.player.pet_id}").status_code, 200)
        self.assert_admin_error(self.sre.get(f"/economy/ledger?pet_id={self.player.pet_id}"), 403, "FORBIDDEN")
        self.assert_admin_error(self.sre.get("/pets/pet-does-not-exist/calls"), 404, "NOT_FOUND")


class CountedUnitsAnchorTests(AdminTestBase):
    """把 `app/web_admin/metering.py` 那张逐状态对应表钉在**真实账本的计数器**上。

    每种终态都用真实的 BudgetLedger 造出来，然后要求：后台逐条给出的「计入用量」加起来，
    等于账本自己的计数器。budget.py 的记账规则哪天变了，这里会先红——而不是后台悄悄显示错的数。
    用一个与"今天"无关的记账日，免得被别的用例或 seed 在当天留下的调用混进来。"""

    def setUp(self) -> None:
        super().setUp()
        self.player = self.user("anchor-owner")
        self.player.adopt_and_move_in("adopt-lan")

    def test_counted_units_match_the_ledger_counters(self):
        from datetime import datetime, timedelta, timezone

        pet_id = self.player.pet_id
        ledger = BudgetLedger(self.app.state.storage)
        t0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
        scope = f"pet:{pet_id}:illustration"

        def reserve(operation_id: str, units: int, *, now=t0, ttl: float = 300):
            return ledger.reserve(operation_id, provider="image", purpose="illustration", subject_scope=f"pet:{pet_id}",
                                  units=units, limits=[BudgetLimit(scope, 50)], ttl_seconds=ttl, now=now)

        ledger.settle(reserve("anchor:succeeded", 2), "succeeded", actual_units=1, now=t0)     # 预占 2、确认发出 1
        ledger.settle(reserve("anchor:failed", 1), "failed", actual_units=1, now=t0)
        ledger.settle(reserve("anchor:unknown-partial", 2), "unknown", actual_units=1, now=t0)  # 发出 1 次、结果不明
        ledger.settle(reserve("anchor:unknown-blind", 2), "unknown", now=t0)                    # 说不出发了几次：按预占全额
        ledger.settle(reserve("anchor:not-sent", 2), "not_sent", now=t0)                        # 确定没发出：计 0
        reserve("anchor:expired", 2, ttl=5)
        ledger.expire_stale(now=t0 + timedelta(seconds=30))                                     # 过期：按预占全额
        reserve("anchor:inflight", 1, now=t0 + timedelta(seconds=31), ttl=3600)                 # 在途：不进已用

        view = self.app.state.admin.overview.pet_calls(pet_id, now=t0)
        rows = {r["operation_id"]: r for r in view["reservations"] if r["accounting_window"] == t0.date().isoformat()}
        self.assertEqual({op: rows[op]["counted_units"] for op in rows}, {
            "anchor:succeeded": 1, "anchor:failed": 1, "anchor:unknown-partial": 1, "anchor:unknown-blind": 2,
            "anchor:not-sent": 0, "anchor:expired": 2, "anchor:inflight": None})
        counter = next(c for c in view["counters_today"] if c["scope_key"] == scope)
        self.assertEqual(sum(r["counted_units"] or 0 for r in rows.values()), counter["used_units"],
                         "逐条计入用量之和必须等于账本计数器")
        self.assertEqual(counter["inflight_units"], 1)

        # 全局那张按用途聚合的表同一口径：各状态加起来等于 usage 计数器
        usage = self.app.state.admin.overview.provider_usage(now=t0)
        grouped = sum(row["units"] or 0 for row in usage["by_provider_purpose"]
                      if (row["provider"], row["purpose"]) == ("image", "illustration"))
        with self.app.state.storage.connect() as conn:
            used = conn.execute("SELECT used_units FROM web_budget_counters WHERE window_key = ? AND scope_key = ?",
                                (t0.date().isoformat(), "usage:image:illustration")).fetchone()["used_units"]
        self.assertEqual(grouped, used)


class BatchSubmitReplayTests(AdminTestBase):
    def setUp(self) -> None:
        super().setUp()
        from app.web_admin.batches import BatchLimits

        self.app.state.admin.batches.limits = BatchLimits(10, 50, 500)
        self.submitter = self.staff("replay-ops", ["economy_ops"])
        self.submitter.login_ok()
        self.pet_ids = []
        for name, candidate in (("replay-a", "adopt-lan"), ("replay-b", "adopt-doudou")):
            player = self.user(name)
            player.adopt_and_move_in(candidate)
            self.pet_ids.append(player.pet_id)

    def batch_count(self) -> int:
        with self.app.state.storage.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) AS n FROM admin_grant_batches").fetchone()["n"])

    def test_same_key_resubmission_returns_the_first_batch(self):
        body = {"title": "照片积压补偿", "reason": "上周照片积压的补偿", "pet_ids": self.pet_ids, "amount_per_pet": 10}
        first = self.submitter.post("/economy/batches", body, key="op-batch-replay-1")
        self.assertEqual(first.status_code, 201, first.text)
        self.assertFalse(first.json()["replayed"])
        again = self.submitter.post("/economy/batches", body, key="op-batch-replay-1")
        self.assertEqual(again.status_code, 201, again.text)
        self.assertTrue(again.json()["replayed"])
        self.assertEqual(again.json()["batch_id"], first.json()["batch_id"])
        self.assertEqual(self.batch_count(), 1, "同一个操作号只能有一个批次")

        changed = self.submitter.post("/economy/batches", {**body, "amount_per_pet": 20}, key="op-batch-replay-1")
        self.assert_admin_error(changed, 409, "IDEMPOTENCY_KEY_REUSED")
        self.assertEqual(self.batch_count(), 1)


if __name__ == "__main__":
    unittest.main()
