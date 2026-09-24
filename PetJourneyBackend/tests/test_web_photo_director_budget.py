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

class FakeMemo:
    """决策备忘：`get` 回读上一轮结论，`put` 在发送前先记一笔"在途"。"""

    def __init__(self, stored=None, *, any_key=None) -> None:
        self.stored = dict(stored or {})
        # 真实 operation_id 是由事件派生的哈希，用例里写不出来；
        # `any_key` 让备忘对任何编号都回同一条记录，从而测到回读那几条分支。
        self.any_key = any_key
        self.written: list[tuple[str, dict]] = []

    def get(self, operation_id: str):
        return self.any_key if self.any_key is not None else self.stored.get(operation_id)

    def put(self, operation_id: str, record: dict) -> None:
        self.written.append((operation_id, record))
        self.stored[operation_id] = record


class FailingBudget(FakeBudget):
    """结算这一步自己出错。挡住"画完了却记不上账"被当成什么都没发生。"""

    def settle(self, **kwargs):
        raise RuntimeError("ledger unavailable")


class SettlementFailureTests(ModelPortCase):
    """结算失败与备忘回读的边角路径——这几条此前一次都没被执行过。"""

    def build(self, chat, budget, **kwargs):
        context = builders.build_context("cafe")
        access = builders.build_access(context, text_director=True)
        return PhotoDirector(chat=chat, budget=budget, **kwargs).direct(context, access)

    def test_a_failing_settlement_notifier_cannot_bury_the_main_signal(self):
        """通知器自己抛了也不能盖掉主信号：照片照出，结算故障另行记录。"""
        def notifier(*_args):
            raise RuntimeError("pager down")

        photo = self.build(FakeChat(text=VALID_CAFE), FailingBudget(),
                           on_settlement_failure=notifier)
        self.assertEqual(photo.text_call.outcome, "sent_ok")

    def test_an_unrecorded_settlement_is_named_in_the_invalid_output_reason(self):
        """模型回复无效**且**结算也失败时，两件事都要留痕，不能只报一件。"""
        photo = self.build(FakeChat(text="{}"), FailingBudget())
        self.assertEqual(photo.text_call.outcome, "invalid_output")
        self.assertIn("settlement_unrecorded:RuntimeError", photo.text_call.reason)
        self.assertTrue(photo.text_call.reason.startswith("model_output_missing_field"))

    def test_a_memo_outcome_that_allows_a_retry_is_not_treated_as_decided(self):
        """备忘里记着的结果**不在终态集合里**时，不能当成已决定而跳过这次。

        `refused` / `sent_ok` / `in_flight` 这些都算已决定；`skipped` 不算——
        它表示上一轮压根没问过模型，那这一轮就该照常问。
        """
        chat = FakeChat(text=VALID_CAFE)
        memo = FakeMemo(any_key={"outcome": "skipped"})
        photo = self.build(chat, FakeBudget(), memo=memo)
        self.assertEqual(len(chat.calls), 1, "可重来的旧结果不该让这次一句都不问")
        self.assertEqual(photo.directed_by, "model")


class ReadinessSceneTests(unittest.TestCase):
    def test_an_unknown_scene_is_reported_as_not_supported(self):
        """场景键不在目录里时，readiness 要给出可辨的原因，而不是混进"缺必需项"。"""
        from dataclasses import replace

        from app.web_photo_director import readiness

        context = builders.build_context("cafe")
        unknown = replace(context, scene=replace(context.scene, scene="no_such_scene"))
        state = readiness(unknown, builders.build_access(context))
        self.assertFalse(state.ready)
        self.assertEqual(state.reason, "scene_not_supported")
