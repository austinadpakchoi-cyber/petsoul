"""幂等恢复的硬情形：回执丢了、而"同时只有一段行程"这道领域约束**不再拦得住**的时候。

已有的 `IdempotencyRecoveryTests` 验的是"重试时 TA 还在路上"——那种情况靠唯一索引就挡住了。
这里验的是验收 CR-Q5 / 合同 C3a 真正难的两种：
  1. 业务已经提交、回执丢了，**原来那趟旅程已经结束**之后再用同一个键重试：这时唯一索引形同虚设；
  2. 两个进程同时接手同一个被遗弃的占位：副作用只能发生一次。
判断标准只有一个：同一个 Idempotency-Key，不论重试几次、什么时候重试，业务都只能发生一次。
"""

from __future__ import annotations

import threading
import unittest
from datetime import timedelta

from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class LostReceiptAfterTheJourneyEndedTests(WebPlatformTestBase):
    settle_on_read = True

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("idem-late")
        self.owner.adopt_and_move_in("adopt-lan")

    def abandon_receipt(self, key: str, minutes_ago: int = 10) -> None:
        """把这个键的回执改回"处理中"并往前拨时间：模拟业务已提交、写回执之前进程挂了。"""
        stamp = (self.clock.now - timedelta(minutes=minutes_ago)).isoformat()
        with self.app.state.storage.connect() as conn:
            conn.execute("UPDATE web_idempotency_keys SET status = 'in_progress', response_json = NULL, updated_at = ? WHERE idem_key = ?",
                         (stamp, key))

    def journey_ids(self) -> list[str]:
        with self.app.state.storage.connect() as conn:
            return [r["journey_id"] for r in conn.execute("SELECT journey_id FROM web_journeys WHERE pet_id = ? ORDER BY created_at",
                                                          (self.owner.pet_id,))]

    def fee_rows(self) -> list[str]:
        with self.app.state.storage.connect() as conn:
            return [r["idempotency_key"] for r in conn.execute(
                "SELECT idempotency_key FROM economy_transactions WHERE pet_id = ? AND type = 'web_travel_fee' ORDER BY rowid",
                (self.owner.pet_id,))]

    def test_retrying_after_the_first_journey_finished_must_not_start_a_second_one(self) -> None:
        key = "idem-late-0001"
        first = self.owner.post("/journey/depart", {"destination_key": "local:cafe"}, key=key)
        self.assertEqual(first.status_code, 200, first.text)
        started = first.json()["journey_id"]
        before = self.owner.home()["wallet"]["balance"]

        self.abandon_receipt(key)
        self.clock.advance(hours=6)  # 这趟已经回家了：“同时只有一段行程”这道约束不再拦得住
        self.run_background()
        self.assertIsNone(self.web.journeys.repo.active_for_pet(self.owner.pet_id), "前提：TA 已经到家了")

        again = self.owner.post("/journey/depart", {"destination_key": "local:cafe"}, key=key)

        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json()["journey_id"], started, "同一个键必须还是原来那一趟，不能另开一趟")
        self.assertEqual(self.journey_ids(), [started], "库里只有一趟行程")
        self.assertEqual(len(self.fee_rows()), 1, "旅费只扣一次")
        self.assertEqual(self.owner.home()["wallet"]["balance"], before, "重试不改变余额")

    def test_a_third_retry_much_later_is_still_the_same_journey(self) -> None:
        key = "idem-late-0002"
        started = self.owner.post("/journey/depart", {"destination_key": "local:cafe"}, key=key).json()["journey_id"]
        for hours in (6, 30):
            self.abandon_receipt(key)
            self.clock.advance(hours=hours)
            self.run_background()
            replay = self.owner.post("/journey/depart", {"destination_key": "local:cafe"}, key=key)
            self.assertEqual((replay.status_code, replay.json().get("journey_id")), (200, started), f"第 {hours} 小时后重试")
        self.assertEqual(self.journey_ids(), [started])
        self.assertEqual(len(self.fee_rows()), 1, "多次重试，旅费仍然只扣一次")

    def test_two_processes_taking_over_the_same_abandoned_receipt_only_act_once(self) -> None:
        key = "idem-race-0001"
        started = self.owner.post("/journey/depart", {"destination_key": "local:cafe"}, key=key).json()["journey_id"]
        self.abandon_receipt(key)
        self.clock.advance(hours=6)
        self.run_background()

        results: list[tuple[int, str | None]] = []
        lock = threading.Lock()

        def retry() -> None:
            response = self.owner.post("/journey/depart", {"destination_key": "local:cafe"}, key=key)
            with lock:
                results.append((response.status_code, response.json().get("journey_id") if response.status_code == 200 else None))

        threads = [threading.Thread(target=retry) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        self.assertEqual(len(results), 4)
        ok = [journey for status, journey in results if status == 200]
        self.assertTrue(all(journey == started for journey in ok), f"拿到结果的都必须是原来那一趟：{results}")
        self.assertEqual(self.journey_ids(), [started], "并发接管也只有一趟行程")
        self.assertEqual(len(self.fee_rows()), 1, "并发接管，旅费仍然只扣一次")


if __name__ == "__main__":
    unittest.main()
