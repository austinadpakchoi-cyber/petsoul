"""冲正一笔后台补偿：只冲后台发的、整笔、只能一次、经手人不能冲、余额不够就拒绝；玩家看到的是说明，不是内部原因。

规则的出处在 `app/web_admin/reversals.py` 开头逐条写了；这里每条一个用例，另加并发与对账联动。
"""

from __future__ import annotations

import unittest

from admin_base import AdminTestBase
from test_admin_concurrency import race

from app.schemas.base import EconomyTransactionType


class ReversalTests(AdminTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.player = self.user("reverse-owner")
        self.player.adopt_and_move_in("adopt-lan")
        self.ops = self.staff("reverse-ops", ["economy_ops"])      # 发补偿的人
        self.ops.login_ok()
        self.lead = self.staff("reverse-lead", ["economy_lead"])   # 冲正的人
        self.lead.login_ok()

    def grant(self, amount: int = 20, staff=None) -> str:
        response = (staff or self.ops).post("/economy/grant", {"pet_id": self.player.pet_id, "amount": amount,
                                                               "reason": "照片没出来的补偿"})
        self.assertEqual(response.status_code, 200, response.text)
        with self.app.state.storage.connect() as conn:
            return conn.execute("SELECT tx_id FROM economy_transactions WHERE idempotency_key = ?",
                                (response.json()["ledger_key"],)).fetchone()["tx_id"]

    def reverse(self, tx_id: str, staff=None, key: str | None = None, **extra):
        return (staff or self.lead).post("/economy/reversals", {"tx_id": tx_id, "reason": "同一件事补了两次，撤回一笔", **extra}, key=key)

    def balance(self) -> int:
        return self.web.economy.wallet(self.player.pet_id).balance

    def test_reversal_adds_a_negative_entry_and_keeps_the_original(self):
        tx_id = self.grant()
        before = self.balance()
        preview = self.lead.get(f"/economy/reversals/preview?tx_id={tx_id}").json()
        self.assertTrue(preview["reversible"], preview)
        self.assertEqual((preview["balance_before"], preview["balance_after"]), (before, before - 20))
        self.assertEqual(preview["original"]["internal_reason"], "照片没出来的补偿", "预览里看得到原补偿的内部原因")
        self.assertEqual(preview["player_view"]["reason"], "撤回一笔多发的补偿")

        response = self.reverse(tx_id)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["reversal"]["amount"], -20)
        self.assertEqual(self.balance(), before - 20)
        with self.app.state.storage.connect() as conn:
            rows = {r["tx_id"]: dict(r) for r in conn.execute(
                "SELECT tx_id, idempotency_key, reason, source, operator FROM economy_transactions WHERE pet_id = ?", (self.player.pet_id,))}
        reversal = rows[body["reversal"]["tx_id"]]
        self.assertEqual(reversal["idempotency_key"], f"admin:reverse:{tx_id}")
        self.assertEqual((reversal["source"], reversal["operator"]), ("admin.compensation.reversal", self.lead.staff_id))
        self.assertEqual(reversal["reason"], "撤回一笔多发的补偿", "写进账本的是给玩家看的说明")
        self.assertIn(tx_id, rows, "原补偿那条流水保留")

        audit = self.lead.get("/audit?action=economy.reverse").json()["entries"][0]
        self.assertEqual(audit["reason"], "同一件事补了两次，撤回一笔")
        self.assertEqual(audit["changes"]["original_tx_id"], tx_id)

        ledger = self.lead.get(f"/economy/ledger?pet_id={self.player.pet_id}").json()["transactions"]
        by_id = {t["tx_id"]: t for t in ledger}
        self.assertEqual(by_id[tx_id]["reversed_by"], body["reversal"]["tx_id"])
        self.assertEqual(by_id[body["reversal"]["tx_id"]]["reversal_of"], tx_id)

    def test_only_once_even_with_another_operation_id(self):
        tx_id = self.grant()
        first = self.reverse(tx_id, key="op-reverse-once")
        self.assertEqual(first.status_code, 200, first.text)
        replay = self.reverse(tx_id, key="op-reverse-once")
        self.assertTrue(replay.json()["replayed"], "同一个操作号：拿回第一次的结果")
        another = self.reverse(tx_id, key="op-reverse-again")
        error = self.assert_admin_error(another, 409, "CONFLICT")
        self.assertEqual(error["details"]["reason"], "already_reversed")
        self.assertEqual(error["details"]["reversed_by_tx_id"], first.json()["reversal"]["tx_id"])
        with self.app.state.storage.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM economy_transactions WHERE source = 'admin.compensation.reversal'")
                             .fetchone()[0], 1)

    def test_you_cannot_reverse_your_own_compensation(self):
        boss = self.owner()                     # 平台负责人既能发也能冲——但不能冲自己发的
        tx_id = self.grant(staff=boss)
        error = self.assert_admin_error(self.reverse(tx_id, staff=boss), 403, "FORBIDDEN")
        self.assertEqual(error["details"]["reason"], "self_reversal")
        denied = [e for e in boss.get("/audit?action=economy.reverse").json()["entries"] if e["status"] == "denied"]
        self.assertEqual(denied[0]["outcome"], "self_reversal", "被挡下的这一次也要留痕")
        self.assertEqual(self.reverse(tx_id).status_code, 200, "换一位同事就可以")

    def test_nobody_who_handled_a_batch_can_reverse_its_entries(self):
        from app.web_admin.batches import BatchLimits

        self.app.state.admin.batches.limits = BatchLimits(10, 50, 500)
        submitted = self.ops.post("/economy/batches", {"title": "照片积压补偿", "reason": "照片积压的统一补偿",
                                                       "pet_ids": [self.player.pet_id], "amount_per_pet": 10})
        self.assertEqual(submitted.status_code, 201, submitted.text)
        batch_id = submitted.json()["batch_id"]
        decided = self.lead.post(f"/economy/batches/{batch_id}/decision", {"approve": True, "note": "核对过名单", "expected_version": 1})
        self.assertEqual(decided.status_code, 200, decided.text)
        executed = self.ops.post(f"/economy/batches/{batch_id}/execute", {"expected_version": decided.json()["version"]})
        self.assertEqual(executed.status_code, 200, executed.text)
        with self.app.state.storage.connect() as conn:
            tx_id = conn.execute("SELECT tx_id FROM economy_transactions WHERE source = 'admin.compensation.batch' AND pet_id = ?",
                                 (self.player.pet_id,)).fetchone()["tx_id"]

        # 账本上的 operator 是执行人（这里是提交人）；批准这个批次的负责人同样经手过，不能一个人撤回
        preview = self.lead.get(f"/economy/reversals/preview?tx_id={tx_id}").json()
        self.assertEqual((preview["reversible"], preview["refusal"]["reason"]), (False, "self_reversal"))
        self.assertEqual(set(preview["original"]["handled_by"]), {self.ops.staff_id, self.lead.staff_id})
        error = self.assert_admin_error(self.reverse(tx_id), 403, "FORBIDDEN")
        self.assertEqual(error["details"]["reason"], "self_reversal")
        other_lead = self.staff("reverse-lead-3", ["economy_lead"])
        other_lead.login_ok()
        self.assertEqual(self.reverse(tx_id, staff=other_lead).status_code, 200, "没经手的负责人可以")

    def test_insufficient_balance_is_refused_without_partial_or_negative(self):
        tx_id = self.grant()
        # 用真实账本原语把钱花掉（例如宠物已经用它出发旅行了）
        self.web.economy.apply(self.player.pet_id, -self.balance(), EconomyTransactionType.web_travel_fee, "test:spend:all",
                               reason="测试：把钱花完", source="test.spend")
        self.assertEqual(self.balance(), 0)
        preview = self.lead.get(f"/economy/reversals/preview?tx_id={tx_id}").json()
        self.assertFalse(preview["reversible"])
        self.assertEqual(preview["refusal"]["reason"], "insufficient_balance")
        error = self.assert_admin_error(self.reverse(tx_id), 409, "CONFLICT")
        self.assertEqual((error["details"]["reason"], error["details"]["balance"], error["details"]["needed"]), ("insufficient_balance", 0, 20))
        self.assertEqual(self.balance(), 0, "不扣成负数")
        with self.app.state.storage.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM economy_transactions WHERE source = 'admin.compensation.reversal'")
                             .fetchone()[0], 0, "也不做部分冲正")
        denied = [e for e in self.lead.get("/audit?action=economy.reverse").json()["entries"] if e["status"] == "denied"]
        self.assertEqual(denied[0]["outcome"], "insufficient_balance")

    def test_only_admin_compensations_can_be_reversed(self):
        with self.app.state.storage.connect() as conn:
            welcome = conn.execute("SELECT tx_id FROM economy_transactions WHERE pet_id = ? AND source != 'admin.compensation'",
                                   (self.player.pet_id,)).fetchone()["tx_id"]
        error = self.assert_admin_error(self.reverse(welcome), 409, "CONFLICT")
        self.assertEqual(error["details"]["reason"], "not_admin_compensation")
        self.assert_admin_error(self.reverse("TX-NOPE"), 404, "NOT_FOUND")

    def test_the_grant_side_cannot_reverse(self):
        tx_id = self.grant()
        self.assert_admin_error(self.reverse(tx_id, staff=self.ops), 403, "FORBIDDEN")
        self.assert_admin_error(self.ops.get(f"/economy/reversals/preview?tx_id={tx_id}"), 403, "FORBIDDEN")

    def test_the_player_sees_the_reversal_note_on_the_bank_card(self):
        tx_id = self.grant()
        self.assertEqual(self.reverse(tx_id, player_note="撤回重复的照片补偿").status_code, 200)
        cards = self.player.get(f"/credentials?pet_id={self.player.pet_id}").json()
        bank = next(c for c in cards if c["kind"] == "bank_card")
        ledger = self.player.get(f"/credentials/{bank['credential_id']}").json()["ledger"]
        self.assertEqual((ledger[0]["delta"], ledger[0]["reason"]), (-20, "撤回重复的照片补偿"))
        self.assertFalse(any("同一件事补了两次" in (e["reason"] or "") for e in ledger), "内部原因不给玩家看")

    def test_a_reversed_duplicate_no_longer_shows_up_in_the_checks(self):
        colleague = self.staff("reverse-ops-2", ["economy_ops"])
        colleague.login_ok()
        self.grant()
        duplicate = self.grant(staff=colleague)
        checks = self.lead.get("/economy/checks").json()
        flagged = [f for f in checks["findings"] if f["kind"] == "repeated_admin_compensation"]
        self.assertEqual(len(flagged), 1)
        self.assertEqual({e["internal_reason"] for e in flagged[0]["details"]["entries"]}, {"照片没出来的补偿"},
                         "对账页给出每一笔的内部原因，方便判断是不是重复")

        self.assertEqual(self.reverse(duplicate).status_code, 200)
        after = self.lead.get("/economy/checks").json()
        self.assertEqual([f for f in after["findings"] if f["kind"] == "repeated_admin_compensation"], [],
                         "冲正掉重复的那一笔之后，这条提示消失")
        self.assertEqual(after["pets_with_errors"], 0, "冲正是正常记账，余额与流水之和仍然对得上")

    def test_two_leads_racing_reverse_it_once(self):
        tx_id = self.grant()
        other_lead = self.staff("reverse-lead-2", ["economy_lead"])
        other_lead.login_ok()
        responses = race([lambda staff=staff: self.reverse(tx_id, staff=staff) for staff in (self.lead, other_lead)])
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        loser = next(r for r in responses if r.status_code == 409).json()["error"]
        self.assertEqual(loser["details"]["reason"], "already_reversed")
        with self.app.state.storage.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM economy_transactions WHERE idempotency_key = ?",
                                          (f"admin:reverse:{tx_id}",)).fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
