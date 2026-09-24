"""照片导演模型端口：一次事件最多一次文本请求；模型改不了世界事实。用禁网替身，不是真实供应商。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "photo_director"))

import builders  # noqa: E402
from harness import FakeBudget, FakeChat, ModelPortCase, VALID_CAFE, reply  # noqa: E402

import unittest  # noqa: E402

class ModelAcceptedTests(ModelPortCase):
    def test_valid_reply_is_used_and_settled(self):
        chat, budget = FakeChat(text=VALID_CAFE), FakeBudget()
        photo = self.direct(chat, budget)
        self.assertEqual(photo.directed_by, "model")
        self.assertEqual(photo.draft.recipe, "cafe_observe_selfie")
        self.assertEqual(photo.draft.expression, "curious")
        self.assertIsNone(photo.fallback_reason)
        self.assertEqual(len(chat.calls), 1)
        self.assertEqual(budget.settled, [(photo.text_call.operation_id, "sent_ok")])

    def test_exactly_one_text_request_per_event(self):
        chat, budget = FakeChat(text=VALID_CAFE), FakeBudget()
        photo = self.direct(chat, budget)
        self.assertEqual(len(chat.calls), 1)
        self.assertEqual(len(budget.reserved), 1)
        self.assertEqual(budget.reserved, [photo.text_call.operation_id])

    def test_reservation_happens_before_the_request(self):
        """预占必须先于发出；否则超预算的调用已经发出去了才被发现。"""
        order: list[str] = []

        class OrderedBudget(FakeBudget):
            def reserve(self, **kwargs):
                order.append("reserve")
                return super().reserve(**kwargs)

        class OrderedChat(FakeChat):
            def complete(self, messages, **kwargs):
                order.append("send")
                return super().complete(messages, **kwargs)

        self.direct(OrderedChat(text=VALID_CAFE), OrderedBudget())
        self.assertEqual(order, ["reserve", "send"])

    def test_model_sees_codes_not_raw_dna_or_media(self):
        chat, budget = FakeChat(text=VALID_CAFE), FakeBudget()
        self.direct(chat, budget)
        payload = chat.calls[0]["messages"][-1]["content"]
        self.assertIn("personality:curious", payload)
        for leaked in ("fx-ref-amber-1", "1111111111111111", "fx-pet-amber"):
            self.assertNotIn(leaked, payload)

    def test_usage_is_recorded_for_the_directors_own_budget(self):
        chat, budget = FakeChat(text=VALID_CAFE), FakeBudget()
        photo = self.direct(chat, budget)
        self.assertEqual(photo.text_call.provider_label, "fx-chat")
        self.assertEqual(photo.text_call.effective_model, "fx-director-model-0930")
        self.assertEqual(photo.text_call.prompt_tokens, 120)
        self.assertTrue(photo.text_call.reserved)

    def test_json_mode_is_requested(self):
        chat, budget = FakeChat(text=VALID_CAFE), FakeBudget()
        self.direct(chat, budget)
        self.assertTrue(chat.calls[0]["json_mode"])

    def test_fenced_json_is_still_accepted(self):
        chat, budget = FakeChat(text=f"```json\n{VALID_CAFE}\n```"), FakeBudget()
        photo = self.direct(chat, budget)
        self.assertEqual(photo.directed_by, "model")

class ModelRejectedTests(ModelPortCase):
    def assert_fell_back(self, photo, reason_contains: str, budget: FakeBudget):
        self.assertEqual(photo.directed_by, "rule")
        self.assertEqual(photo.text_call.outcome, "invalid_output")
        self.assertIn(reason_contains, photo.text_call.reason or "")
        self.assertEqual([outcome for _, outcome in budget.settled], ["invalid_output"])

    def test_non_json_falls_back_without_a_second_request(self):
        chat, budget = FakeChat(text="它今天看起来很开心"), FakeBudget()
        photo = self.direct(chat, budget)
        self.assert_fell_back(photo, "model_output_not_json", budget)
        self.assertEqual(len(chat.calls), 1)

    def test_model_cannot_move_the_pet_to_another_city(self):
        chat, budget = FakeChat(text=reply(
            recipe="cafe_observe_selfie", expression="curious",
            visible_facts=["at_cafe"], city="巴黎",
        )), FakeBudget()
        photo = self.direct(chat, budget)
        self.assert_fell_back(photo, "model_output_unknown_field", budget)
        self.assertIn("香港", photo.prompt)
        self.assertNotIn("巴黎", photo.prompt)

    def test_model_cannot_invent_an_unverified_object(self):
        """没核验就是没有：模型说画面里有勋章也不算数。"""
        chat, budget = FakeChat(text=reply(
            recipe="cockpit_focus", expression="focused",
            visible_facts=["flight_adventure", "earned_medal"],
        )), FakeBudget()
        photo = self.direct(chat, budget, scene_key="flight_adventure")
        self.assert_fell_back(photo, "visible_fact_not_verified", budget)
        self.assertNotIn("勋章", photo.prompt)

    def test_model_cannot_borrow_another_scenes_action(self):
        chat, budget = FakeChat(text=reply(
            recipe="train_watch_selfie", expression="curious", visible_facts=["at_cafe"],
        )), FakeBudget()
        photo = self.direct(chat, budget)
        self.assert_fell_back(photo, "recipe_scene_mismatch", budget)

    def test_model_cannot_invent_a_recipe(self):
        chat, budget = FakeChat(text=reply(
            recipe="cafe_drone_orbit", expression="curious", visible_facts=["at_cafe"],
        )), FakeBudget()
        photo = self.direct(chat, budget)
        self.assert_fell_back(photo, "recipe_not_allowed", budget)

    def test_model_cannot_pick_a_camera_on_its_own(self):
        """镜头由配方带，单独给 camera 字段就是在试图绕开互斥编译。"""
        chat, budget = FakeChat(text=reply(
            recipe="cafe_observe_selfie", camera="detail_pov",
            expression="curious", visible_facts=["at_cafe"],
        )), FakeBudget()
        photo = self.direct(chat, budget)
        self.assert_fell_back(photo, "model_output_unknown_field", budget)

    def test_model_cannot_override_an_explicit_camera_request(self):
        chat, budget = FakeChat(text=reply(
            recipe="cafe_detail_pov", expression="focused",
            visible_facts=["at_cafe", "coffee_cup"],
        )), FakeBudget()
        photo = self.direct(chat, budget, requested_camera="front_selfie")
        self.assert_fell_back(photo, "requested_camera_overridden", budget)
        self.assertEqual(photo.draft.camera, "front_selfie")

    def test_model_must_keep_the_mandatory_fact_visible(self):
        chat, budget = FakeChat(text=reply(
            recipe="cafe_observe_selfie", expression="curious", visible_facts=["weather_sunny"],
        )), FakeBudget()
        photo = self.direct(chat, budget)
        self.assert_fell_back(photo, "mandatory_fact_not_visible", budget)

    def test_fallback_photo_is_still_complete(self):
        chat, budget = FakeChat(text="{}"), FakeBudget()
        photo = self.direct(chat, budget)
        self.assertEqual(photo.directed_by, "rule")
        self.assertTrue(photo.prompt)
        self.assertIn("place_anchored", photo.prompt_checks)
        self.assertIn("identity_locked", photo.prompt_checks)
        self.assertEqual(photo.references[0].role, "pet_identity")

if __name__ == "__main__":
    unittest.main()
