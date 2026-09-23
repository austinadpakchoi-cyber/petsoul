"""照片导演：什么情况下一次请求都不发，以及未知结果不被改写成失败。用禁网替身。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "photo_director"))

import builders  # noqa: E402
from harness import FakeBudget, FakeChat, ModelPortCase, VALID_CAFE  # noqa: E402

import unittest  # noqa: E402

import builders as _b  # noqa: E402,F401
from app.web_photo_director import PhotoDirector  # noqa: E402

class ModelNotCalledTests(ModelPortCase):
    def test_unknown_result_is_not_auto_resent(self):
        """发出去了但没拿回结果：记 sent_unknown，不自动重发，也不写成"确定没画成"。"""
        chat, budget = FakeChat(raises=TimeoutError("no response")), FakeBudget()
        photo = self.direct(chat, budget)
        self.assertEqual(photo.text_call.outcome, "sent_unknown")
        self.assertNotEqual(photo.text_call.outcome, "invalid_output")
        self.assertTrue(photo.text_call.reserved)
        self.assertEqual(len(chat.calls), 1)
        self.assertEqual([outcome for _, outcome in budget.settled], ["sent_unknown"])
        self.assertEqual(photo.directed_by, "rule")

    def test_budget_denial_sends_nothing(self):
        chat, budget = FakeChat(text=VALID_CAFE), FakeBudget(allow=False)
        photo = self.direct(chat, budget)
        self.assertEqual(photo.text_call.outcome, "refused")
        self.assertEqual(photo.text_call.reason, "budget_denied")
        self.assertFalse(photo.text_call.reserved)
        self.assertEqual(chat.calls, [])
        self.assertEqual(budget.settled, [])

    def test_unavailable_provider_sends_nothing_and_reserves_nothing(self):
        chat, budget = FakeChat(text=VALID_CAFE, available=False), FakeBudget()
        photo = self.direct(chat, budget)
        self.assertEqual(photo.text_call.outcome, "skipped")
        self.assertEqual(photo.text_call.reason, "provider_unavailable")
        self.assertEqual(chat.calls, [])
        self.assertEqual(budget.reserved, [])

    def test_household_without_text_permission_sends_nothing(self):
        chat, budget = FakeChat(text=VALID_CAFE), FakeBudget()
        photo = self.direct(chat, budget, allowed=False)
        self.assertEqual(photo.text_call.outcome, "skipped")
        self.assertEqual(photo.text_call.reason, "text_director_not_permitted")
        self.assertEqual(chat.calls, [])
        self.assertEqual(budget.reserved, [])

    def test_unwired_ports_fall_back_cleanly(self):
        context = builders.build_context("cafe")
        access = builders.build_access(context, text_director=True)
        photo = PhotoDirector().direct(context, access)
        self.assertEqual(photo.text_call.outcome, "skipped")
        self.assertEqual(photo.text_call.reason, "text_director_not_wired")
        self.assertEqual(photo.directed_by, "rule")

    def test_explicit_rule_path_never_touches_the_port(self):
        chat, budget = FakeChat(text=VALID_CAFE), FakeBudget()
        context = builders.build_context("cafe")
        access = builders.build_access(context, text_director=True)
        photo = PhotoDirector(chat=chat, budget=budget).direct_with_rules(context, access)
        self.assertEqual(photo.directed_by, "rule")
        self.assertEqual(photo.text_call.outcome, "rule_only")
        self.assertEqual(chat.calls, [])
        self.assertEqual(budget.reserved, [])

    def test_revoked_household_never_reaches_the_model(self):
        """撤权要在调用模型之前挡住，不是拿到回复再丢掉。"""
        from app.web_photo_director import PhotoDirectorError

        chat, budget = FakeChat(text=VALID_CAFE), FakeBudget()
        context = builders.build_context("cafe")
        access = builders.build_access(context, text_director=True, generated_photos=False)
        with self.assertRaises(PhotoDirectorError):
            PhotoDirector(chat=chat, budget=budget).direct(context, access)
        self.assertEqual(chat.calls, [])
        self.assertEqual(budget.reserved, [])

    def test_operation_id_is_stable_per_event(self):
        chat, budget = FakeChat(text=VALID_CAFE), FakeBudget()
        first = self.direct(chat, budget)
        second = self.direct(chat, FakeBudget())
        self.assertEqual(first.text_call.operation_id, second.text_call.operation_id)
        other = self.direct(FakeChat(text=VALID_CAFE), FakeBudget(), scene_key="train")
        self.assertNotEqual(first.text_call.operation_id, other.text_call.operation_id)

if __name__ == "__main__":
    unittest.main()
