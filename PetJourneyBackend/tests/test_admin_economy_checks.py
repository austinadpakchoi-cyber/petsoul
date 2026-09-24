"""游戏经济只读对账：判据与 PetEconomyEngine.rebuild_derived_state 同口径，能指出差额出在哪两条流水之间，只报不修。

"绕开账本改余额"在产品代码里没有入口（那正是对账要抓的东西），所以这里用直接写库来模拟它——
这些写库只发生在用例里，模拟的是"有人或有 bug 绕开了 apply_in"，不是产品路径。
"""

from __future__ import annotations

import json
import unittest

from admin_base import AdminTestBase
from web_base import LUNCH_UTC, FakeClock


class EconomyChecksTests(AdminTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.player = self.user("checks-owner")
        self.player.adopt_and_move_in("adopt-lan")
        self.other = self.user("checks-other")
        self.other.adopt_and_move_in("adopt-doudou")
        self.economy = self.staff("checks-economy", ["economy_ops"])
        self.economy.login_ok()

    def checks(self) -> dict:
        response = self.economy.get("/economy/checks")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def grant(self, amount: int, reason: str = "对账用例的补偿", staff=None, pet_id: str | None = None) -> dict:
        response = (staff or self.economy).post("/economy/grant", {"pet_id": pet_id or self.player.pet_id, "amount": amount,
                                                                   "reason": reason})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def bypass(self, delta: int) -> None:
        """模拟绕开账本改余额（产品里没有这条路）。"""
        with self.app.state.storage.connect() as conn:
            conn.execute("UPDATE pet_wallets SET travel_coin = travel_coin + ? WHERE pet_id = ?", (delta, self.player.pet_id))

    def tx_id(self, operation_key: str) -> str:
        with self.app.state.storage.connect() as conn:
            return conn.execute("SELECT tx_id FROM economy_transactions WHERE idempotency_key = ?", (operation_key,)).fetchone()[0]

    def of(self, result: dict, kind: str) -> list[dict]:
        return [f for f in result["findings"] if f["kind"] == kind]

    def test_a_clean_ledger_reports_nothing(self):
        self.grant(20)
        result = self.checks()
        self.assertEqual(result["findings"], [], result["findings"])
        self.assertEqual(result["pets_with_errors"], 0)
        self.assertGreaterEqual(result["checked_pets"], 2)
        self.assertGreaterEqual(result["checked_entries"], 3, "两只宠物各一笔入住礼 + 一笔补偿")
        overview = self.owner().get("/overview").json()
        metric = next(m for m in overview["metrics"] if m["key"] == "economy.mismatch")
        self.assertEqual(metric["value"], 0)
        self.assertNotIn("economy.mismatch", [m["key"] for m in overview["attention"]])

    def test_an_out_of_ledger_change_is_caught_and_located(self):
        first = self.grant(20)
        self.bypass(50)                    # 两次记账之间，有人绕开账本加了 50
        second = self.grant(10)
        result = self.checks()
        mismatch = self.of(result, "balance_mismatch")
        self.assertEqual(len(mismatch), 1, result["findings"])
        details = mismatch[0]["details"]
        self.assertEqual((details["currency"], details["difference"]), ("travel_coin", 50))
        self.assertEqual(details["first_gap"]["after_tx"], self.tx_id(first["ledger_key"]))
        self.assertEqual(details["first_gap"]["before_tx"], self.tx_id(second["ledger_key"]))
        self.assertEqual(details["first_gap"]["delta"], 50)
        gaps = self.of(result, "chain_gap")
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["severity"], "warn")
        self.assertEqual(result["pets_with_errors"], 1, "另一只宠物的账是干净的")

        overview = self.owner().get("/overview").json()
        self.assertIn("economy.mismatch", [m["key"] for m in overview["attention"]], "首页「需要处理」里要出现")

    def test_a_change_after_the_last_entry_is_reported_as_tail_drift(self):
        granted = self.grant(20)
        self.bypass(-5)
        mismatch = self.of(self.checks(), "balance_mismatch")[0]["details"]
        self.assertEqual(mismatch["difference"], -5)
        self.assertNotIn("first_gap", mismatch)
        tail = mismatch["after_last_entry"]
        self.assertEqual(tail["tx_id"], self.tx_id(granted["ledger_key"]))
        self.assertEqual(tail["wallet_now"], tail["after"] - 5)

    def test_negative_balance_and_self_inconsistent_entries(self):
        with self.app.state.storage.connect() as conn:
            conn.execute("UPDATE pet_wallets SET travel_coin = -3 WHERE pet_id = ?", (self.other.pet_id,))
            conn.execute(
                "INSERT INTO economy_transactions (tx_id, pet_id, type, idempotency_key, amounts_json, item_ids_json, before_json, "
                "after_json, reason, operator, source, status, created_at) VALUES (?, ?, 'web_reward', ?, ?, '[]', ?, ?, ?, ?, ?, "
                "'committed', ?)",
                ("TX-BROKEN", self.player.pet_id, "test:broken:1", json.dumps({"travel_coin": 5}),
                 json.dumps({"travel_coin": 999}), json.dumps({"travel_coin": 1030}), "用例构造的坏流水", "test", "test.broken",
                 "2026-09-22T04:00:00+00:00"))
        result = self.checks()
        negative = self.of(result, "negative_balance")
        self.assertEqual([f["pet_id"] for f in negative], [self.other.pet_id])
        broken = self.of(result, "entry_inconsistent")
        self.assertEqual(broken[0]["details"]["tx_id"], "TX-BROKEN")
        self.assertEqual((broken[0]["details"]["before"], broken[0]["details"]["after"], broken[0]["details"]["amount"]), (999, 1030, 5))
        self.assertEqual(result["pets_with_errors"], 2)

    def test_repeated_admin_compensation_is_flagged_for_review_not_as_an_error(self):
        colleague = self.staff("checks-economy-2", ["economy_ops"])
        colleague.login_ok()
        self.grant(20, reason="照片没出来的补偿")
        self.clock.advance(minutes=30)
        self.grant(20, reason="同一件事又补了一次", staff=colleague)
        flagged = self.of(self.checks(), "repeated_admin_compensation")
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]["severity"], "review")
        self.assertEqual(flagged[0]["details"]["total"], 40)
        self.assertEqual({e["operator"] for e in flagged[0]["details"]["entries"]},
                         {self.economy.staff_id, colleague.staff_id}, "列出每一笔是谁发的，方便人去判断")

        # 过了 24 小时的下一笔自成一组，不连进去
        self.clock.advance(hours=25)
        self.economy.login_ok()  # 假时钟跨过了会话有效期
        self.grant(15, reason="隔天另一件事的补偿")
        flagged = self.of(self.checks(), "repeated_admin_compensation")
        self.assertEqual(len(flagged), 1)
        self.assertEqual(len(flagged[0]["details"]["entries"]), 2)
        self.assertEqual(self.checks()["pets_with_errors"], 0, "需要人判断的不算错")

    def test_checks_only_read(self):
        self.grant(20)
        self.bypass(7)
        tables = ("pet_wallets", "economy_transactions", "owner_funds", "admin_audit")
        before = self.table_counts(tables)
        with self.app.state.storage.connect() as conn:
            balance = conn.execute("SELECT travel_coin FROM pet_wallets WHERE pet_id = ?", (self.player.pet_id,)).fetchone()[0]
        for _ in range(3):
            self.checks()
        self.assertEqual(self.table_counts(tables), before, "对账不写任何表，连审计都不写")
        with self.app.state.storage.connect() as conn:
            self.assertEqual(conn.execute("SELECT travel_coin FROM pet_wallets WHERE pet_id = ?", (self.player.pet_id,)).fetchone()[0],
                             balance, "发现了差额也不去改余额")

    def test_needs_economy_read(self):
        sre = self.staff("checks-sre", ["sre"])
        sre.login_ok()
        self.assert_admin_error(sre.get("/economy/checks"), 403, "FORBIDDEN")


if __name__ == "__main__":
    unittest.main()
