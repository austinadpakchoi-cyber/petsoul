"""补偿写进账本的是「给玩家看的说明」，员工的内部原因只进审计。

缺陷（第六批修）：账本流水的 `reason` 会原样显示在玩家的星球银行卡上（`routers/web/credentials.py`），
而后台发补偿一直把**员工写的内部处理原因**写进了这一栏。这里全部从玩家侧接口验证：玩家真正看到的是什么。
"""

from __future__ import annotations

import unittest

from admin_base import AdminTestBase

INTERNAL = "用户投诉语气很冲，先补一点安抚一下"   # 这种话绝不能出现在玩家眼前


class PlayerNoteTests(AdminTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.player = self.user("note-owner")
        self.player.adopt_and_move_in("adopt-lan")
        self.ops = self.staff("note-economy", ["economy_ops"])
        self.ops.login_ok()

    def bank_card(self) -> list[dict]:
        """玩家自己打开星球银行卡看到的流水（与玩家端页面读的是同一个接口）。"""
        cards = self.player.get(f"/credentials?pet_id={self.player.pet_id}")
        self.assertEqual(cards.status_code, 200, cards.text)
        bank = next(c for c in cards.json() if c["kind"] == "bank_card")
        detail = self.player.get(f"/credentials/{bank['credential_id']}")
        self.assertEqual(detail.status_code, 200, detail.text)
        return detail.json()["ledger"]

    def grant(self, **extra) -> dict:
        response = self.ops.post("/economy/grant", {"pet_id": self.player.pet_id, "amount": 20, "reason": INTERNAL, **extra})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_the_player_sees_the_default_note_never_the_internal_reason(self):
        result = self.grant()
        self.assertEqual(result["player_view"], {"where": "星球银行卡", "delta": 20, "type": "web_reward", "reason": "运营补偿"})
        entries = self.bank_card()
        self.assertEqual((entries[0]["delta"], entries[0]["reason"]), (20, "运营补偿"))
        self.assertFalse(any(INTERNAL in (e["reason"] or "") for e in entries), "内部原因不能出现在玩家的银行卡上")

        audit = self.owner().get("/audit?action=economy.grant").json()["entries"]
        self.assertEqual(audit[0]["reason"], INTERNAL, "内部原因只进审计")
        self.assertEqual(audit[0]["changes"]["player_note"], "运营补偿")

    def test_a_custom_note_is_what_the_player_sees(self):
        self.grant(player_note="照片延迟的补偿，谢谢耐心等待")
        self.assertEqual(self.bank_card()[0]["reason"], "照片延迟的补偿，谢谢耐心等待")

    def test_preview_shows_exactly_what_the_player_will_see(self):
        preview = self.ops.get(f"/economy/grant/preview?pet_id={self.player.pet_id}&amount=20&player_note=照片延迟的补偿").json()
        self.assertEqual(preview["player_view"]["reason"], "照片延迟的补偿")
        self.assertTrue(any("玩家在星球银行卡上会看到" in line for line in preview["effects"]))

    def test_notes_with_links_line_breaks_or_too_long_are_refused(self):
        for note in ("看这里 https://example.com", "第一行\n第二行", "字" * 31):
            with self.subTest(note=note[:12]):
                response = self.ops.post("/economy/grant", {"pet_id": self.player.pet_id, "amount": 20, "reason": INTERNAL,
                                                            "player_note": note})
                error = self.assert_admin_error(response, 422, "VALIDATION_FAILED")
                self.assertEqual(error["details"]["field"], "player_note")
        self.assertFalse(any(e["reason"] == INTERNAL for e in self.bank_card()))


class BatchPlayerNoteTests(AdminTestBase):
    def setUp(self) -> None:
        super().setUp()
        from app.web_admin.batches import BatchLimits

        self.app.state.admin.batches.limits = BatchLimits(10, 50, 500)
        self.player = self.user("batch-note-owner")
        self.player.adopt_and_move_in("adopt-lan")
        self.ops = self.staff("batch-note-ops", ["economy_ops"])
        self.ops.login_ok()
        self.lead = self.staff("batch-note-lead", ["economy_lead"])
        self.lead.login_ok()

    def run_batch(self, **extra) -> str:
        submitted = self.ops.post("/economy/batches", {"title": "说明测试批次", "reason": INTERNAL, "pet_ids": [self.player.pet_id],
                                                       "amount_per_pet": 10, **extra})
        self.assertEqual(submitted.status_code, 201, submitted.text)
        batch_id = submitted.json()["batch_id"]
        decided = self.lead.post(f"/economy/batches/{batch_id}/decision", {"approve": True, "note": "核对无误", "expected_version": 1})
        executed = self.ops.post(f"/economy/batches/{batch_id}/execute", {"expected_version": decided.json()["version"]})
        self.assertEqual(executed.status_code, 200, executed.text)
        return batch_id

    def ledger_reason(self, batch_id: str) -> str:
        with self.app.state.storage.connect() as conn:
            return conn.execute("SELECT reason FROM economy_transactions WHERE idempotency_key = ?",
                                (f"admin:batch:{batch_id}:{self.player.pet_id}",)).fetchone()["reason"]

    def test_batch_writes_the_player_note_not_the_batch_reason(self):
        batch_id = self.run_batch(player_note="系统维护补偿")
        self.assertEqual(self.ledger_reason(batch_id), "系统维护补偿")
        detail = self.ops.get(f"/economy/batches/{batch_id}").json()
        self.assertEqual(detail["batch"]["player_note"], "系统维护补偿", "审批人在批次详情里能看到玩家会看到什么")
        self.assertEqual(detail["batch"]["reason"], INTERNAL)

    def test_batch_without_a_note_uses_the_default(self):
        self.assertEqual(self.ledger_reason(self.run_batch()), "运营补偿")

    def test_batch_preview_shows_the_player_view(self):
        preview = self.ops.post("/economy/batches/preview", {"pet_ids": [self.player.pet_id], "amount_per_pet": 10,
                                                             "player_note": "系统维护补偿"}).json()
        self.assertEqual(preview["player_view"]["reason"], "系统维护补偿")


if __name__ == "__main__":
    unittest.main()
