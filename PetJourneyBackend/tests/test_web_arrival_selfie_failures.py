"""到站自拍：出错、重试、放弃，以及挂在真实认知线上。

从 `test_web_arrival_selfie.py` 拆出来的——那份超过了架构门禁「每个文件最多 30 个 def/class」（B 2026-09-24 提醒）。
共用的场景（假模型、假生图、找到站消息与明信片的办法）在 `test_web_arrival_selfie.ArrivalBase`。
"""

from __future__ import annotations

import unittest

from app.web_arrival.service import MAX_ATTEMPTS
from test_web_arrival_selfie import ArrivalBase


class ArrivalFailureTests(ArrivalBase):
    def test_a_failure_rolls_back_everything_and_retries_with_backoff_then_gives_up(self) -> None:
        owner = self.arrive("arrival-broken")
        original = self.web.arrival.pet_note_in

        def broken(conn, **kwargs):
            raise RuntimeError("db is sad")

        self.web.arrival.pet_note_in = broken
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self.assertEqual(self.run_round(), 0)
            state = self.web.arrival.state_of(owner.pet_id)
            self.assertEqual(state["attempts"], attempt)
            self.assertIn("db is sad", state["last_error"])
            self.assertIsNone(self.arrival_postcard(owner), "消息没写成，明信片也不能单独留下（同一个事务）")
            self.assertEqual(self.selfie_tasks(owner.pet_id), [], "生图任务也随事务回滚，不会白画")
            self.clock.advance(hours=1)  # 越过退避
        self.assertEqual(self.web.arrival.state_of(owner.pet_id)["state"], "abandoned", "用尽次数就放弃，原因留给运营")
        self.web.arrival.pet_note_in = original
        self.assertEqual(self.run_round(), 0, "放弃之后不再自动重试")

    def test_two_failures_recorded_from_the_same_snapshot_both_count(self) -> None:
        """两路轮次拿着同一份旧快照、同时记失败：次数要各加一，不能互相覆盖成一次（否则放弃被推迟）。"""
        owner = self.arrive("arrival-count")
        self.web.arrival._failed(owner.pet_id, "first", self.clock.now)
        self.web.arrival._failed(owner.pet_id, "second", self.clock.now)
        self.assertEqual(self.web.arrival.state_of(owner.pet_id)["attempts"], 2)

    def test_backoff_holds_the_retry_until_it_is_due(self) -> None:
        owner = self.arrive("arrival-backoff")
        original = self.web.arrival.postcard_in
        self.web.arrival.postcard_in = lambda conn, **kwargs: (_ for _ in ()).throw(RuntimeError("once"))
        self.run_round()
        self.web.arrival.postcard_in = original
        self.assertEqual(self.run_round(), 0, "还没到重试时刻")
        self.clock.advance(seconds=31)
        self.assertEqual(self.run_round(), 1, "到点就重试成功")
        self.assertIsNotNone(self.arrival_postcard(owner))

    def test_a_pet_that_left_the_household_before_delivery_is_skipped(self) -> None:
        owner = self.arrive("arrival-left")
        with self.app.state.storage.connect() as conn:
            conn.execute("UPDATE web_pet_arrivals SET household_id = 'hh-somewhere-else' WHERE pet_id = ?", (owner.pet_id,))
        self.assertEqual(self.run_round(), 0)
        self.assertEqual(self.web.arrival.state_of(owner.pet_id)["state"], "skipped")
        self.assertIsNone(self.arrival_message(owner))
        self.assertEqual(self.selfie_tasks(owner.pet_id), [])


class ArrivalWiringTests(ArrivalBase):
    def test_the_real_cognition_round_delivers_it(self) -> None:
        """挂在认知线上：跑一轮真实的认知 ticker 就发出（不是只在测试里手动调 run）。"""
        owner = self.arrive("arrival-ticker")
        self.clock.advance(seconds=1)
        self.assertTrue(self.web.cognition.tick(self.clock.now), "前提：这一轮真的跑了（拿到了认知线租约）")
        self.assertIsNotNone(self.arrival_message(owner))
        self.assertIsNotNone(self.arrival_postcard(owner))


if __name__ == "__main__":
    unittest.main()
