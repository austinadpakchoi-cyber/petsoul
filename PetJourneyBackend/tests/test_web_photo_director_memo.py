"""照片导演：备忘让重试不重复调用文本模型。

**这里证明的范围**：内存备忘下，异常恢复与重新构造对象都不会再发一次请求。
**这里没有证明**：持久提交、真实进程退出、并发恢复。它们列在交接文档的
"启用模型导演前的门槛"。首批规则导演零文本调用，不等这些。

全程禁网，用注入替身，不是真实供应商。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "photo_director"))

import builders  # noqa: E402
from harness import FakeBudget, FakeChat, ModelPortCase, VALID_CAFE  # noqa: E402

from app.web_photo_director import PhotoDirector  # noqa: E402
from app.web_photo_director.memo import recall  # noqa: E402


class MemoDict:
    """A 那一侧要持久化的最小形状；测试里用**进程内内存字典**代替。

    没有序列化、没有真实存储、没有并发——所以它证明不了跨进程恢复。
    """

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    def get(self, operation_id: str):
        return self.rows.get(operation_id)

    def put(self, operation_id: str, record: dict) -> None:
        self.rows[operation_id] = record


class RetryDoesNotRecallTests(ModelPortCase):
    def _context(self):
        context = builders.build_context("cafe")
        return context, builders.build_access(context, text_director=True)

    def _run(self, chat, budget, memo, **kwargs):
        context = builders.build_context("cafe", **kwargs)
        access = builders.build_access(context, text_director=True)
        return PhotoDirector(chat=chat, budget=budget, memo=memo).direct(context, access)

    def test_second_attempt_reuses_the_recorded_shot_without_calling_again(self):
        """稳定编号只是名字；挡住重复付费的是"这个编号已经有结论了"。"""
        memo = MemoDict()
        chat, budget = FakeChat(text=VALID_CAFE), FakeBudget()
        first = self._run(chat, budget, memo)
        self.assertEqual(first.directed_by, "model")
        self.assertEqual(len(chat.calls), 1)

        second = self._run(chat, budget, memo)
        self.assertEqual(len(chat.calls), 1, "重试不该再调用一次文本模型")
        self.assertEqual(second.draft.recipe, first.draft.recipe)
        self.assertEqual(second.prompt, first.prompt)
        self.assertEqual(len(budget.reserved), 1)

    def test_a_new_director_instance_reuses_the_recorded_decision(self):
        """全新的 director / chat / budget 实例，只共享备忘，就不再调用。

        **这不是跨进程恢复的证明**：`MemoDict` 是同进程内存字典。
        真正的跨进程恢复要等 A 的持久化落地后另证。
        """
        memo = MemoDict()
        self._run(FakeChat(text=VALID_CAFE), FakeBudget(), memo)
        fresh_chat, fresh_budget = FakeChat(text=VALID_CAFE), FakeBudget()
        photo = self._run(fresh_chat, fresh_budget, memo)
        self.assertEqual(fresh_chat.calls, [])
        self.assertEqual(fresh_budget.reserved, [])
        self.assertEqual(photo.directed_by, "model")

    def test_an_exception_between_send_and_settle_does_not_call_again(self):
        """先写后发堵的就是这个窗口：请求已经发出、结果还没写回就异常退出。

        注意这是**异常恢复**，不是真实进程退出。
        """
        memo = MemoDict()

        class RaiseAfterSend(FakeChat):
            def complete(self, messages, **kwargs):
                super().complete(messages, **kwargs)
                raise RuntimeError("这里异常了，结论没写回")

        raising = RaiseAfterSend(text=VALID_CAFE)
        context, access = self._context()
        with self.assertRaises(RuntimeError):
            PhotoDirector(chat=raising, budget=FakeBudget(), memo=memo,
                          abort_on=(RuntimeError,)).direct(context, access)
        self.assertEqual(len(raising.calls), 1)
        self.assertEqual(next(iter(memo.rows.values()))["outcome"], "in_flight")

        after, budget_after = FakeChat(text=VALID_CAFE), FakeBudget()
        photo = self._run(after, budget_after, memo)
        self.assertEqual(after.calls, [], "在途记录必须挡住第二次调用")
        self.assertEqual(photo.directed_by, "rule")
        self.assertEqual(photo.text_call.reason, "previous_attempt_in_flight")

    def test_an_old_in_flight_is_still_never_treated_as_not_sent(self):
        """在途记录不会因为"放久了"就被当成没发出——那等于自动重发一笔可能已计费的调用。"""
        memo = MemoDict()
        key = "photo-director:whatever"
        memo.rows[key] = {"outcome": "in_flight", "reserved": True,
                          "recorded_at": "2020-01-01T00:00:00Z"}
        draft, record = recall(memo, None, key)
        self.assertIsNone(draft)
        self.assertIsNotNone(record, "陈旧的在途记录仍然必须挡住再次调用")
        self.assertEqual(record.outcome, "sent_unknown")
        self.assertEqual(record.reason, "previous_attempt_in_flight")

    def test_an_unknown_result_is_never_retried_later(self):
        """上一次结果不明、可能已计费：重试只能走规则，不能再发一次。"""
        memo = MemoDict()
        self._run(FakeChat(raises=TimeoutError("no response")), FakeBudget(), memo)
        chat, budget = FakeChat(text=VALID_CAFE), FakeBudget()
        photo = self._run(chat, budget, memo)
        self.assertEqual(chat.calls, [])
        self.assertEqual(photo.directed_by, "rule")
        self.assertEqual(photo.text_call.outcome, "sent_unknown")

    def test_a_stale_recorded_shot_falls_back_instead_of_calling_again(self):
        """事实变了，旧拍法不再合法——也不重新调用，直接走规则。"""
        memo = MemoDict()
        self._run(FakeChat(text=VALID_CAFE), FakeBudget(), memo)
        for row in memo.rows.values():
            row["recipe"] = "gym_mirror_standing"  # 换成这个场景里不可能的拍法
        chat, budget = FakeChat(text=VALID_CAFE), FakeBudget()
        photo = self._run(chat, budget, memo)
        self.assertEqual(chat.calls, [])
        self.assertEqual(photo.directed_by, "rule")
        self.assertIn("recorded_decision_stale", photo.fallback_reason or "")

    def test_without_a_memo_the_guarantee_is_reported_as_absent(self):
        """没有备忘端口就没有跨进程保证——如实标出来，不假装已经防住。"""
        chat, budget = FakeChat(raises=TimeoutError("x")), FakeBudget()
        photo = self._run(chat, budget, None)
        self.assertIn("memo_absent", photo.fallback_reason or "")


if __name__ == "__main__":
    unittest.main()
