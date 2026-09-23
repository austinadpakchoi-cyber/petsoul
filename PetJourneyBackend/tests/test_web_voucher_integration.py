"""借车券的**最终接入验证**：真实收藏服务 + 正式装配 + 真实 depart，不装任何替身（CR-C9 收口）。

和 `test_web_fare_settlement.py` 的区别说清楚：那边用一张自备的券验**旅程这一侧的契约**（券的实现无关），
这里验的是**接上真实 `collection.consume_in` 之后整条路真的原子**——替身通过不能代替这一步。

每个用例自己新建一套隔离应用（一次性临时库），不复用别处已经建好的实例。
同事务核销 `consume_in` 现在是**必需能力**（凭证装配直接调用它），缺了就是回归：这里**明确失败**，不 skip。
`can_drive` 直接置真：驾照流程由 `test_web_driving_license` 覆盖，这里只看券与钱的事务边界。
不联网、不产生付费调用。
"""

from __future__ import annotations

import unittest

from app.schemas.base import EconomyTransactionType
from app.web_journey.errors import JourneyError
from app.web_platform.runtime_epochs import versions_in
from app.web_platform.uow import unit_of_work
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase

DRIVE, FEE = "local:drive_trip", 20


class VoucherIntegrationTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.assertTrue(hasattr(self.web.collection, "consume_in"),
                        "收藏服务必须提供同事务核销 consume_in(conn, pet_id, kind, now)——凭证装配直接调用它，缺了就是回归")
        self.assertIsNotNone(self.web.journeys.fee_waiver_in, "正式装配必须把 fee_waiver_in 接上，用券路径才是原子的")
        self.owner = self.user("voucher-integration")
        self.owner.adopt_and_move_in("adopt-lan")
        self.web.journeys.can_drive = lambda pet_id: True
        self.coins(200)

    # ---- 工具 ----
    def coins(self, amount: int) -> None:
        self.web.economy.apply(self.owner.pet_id, amount, EconomyTransactionType.web_reward, f"test:grant:{amount}",
                               reason="测试补给", source="test.voucher_integration", now=self.clock.now)

    def grant_voucher(self, count: int = 1) -> None:
        """用真实收藏服务发券（和驾校发券走同一个写法）。"""
        with unit_of_work(self.app.state.storage) as conn:
            for n in range(count):
                self.web.collection.keepsake(conn, user_id=self.owner.user_id, pet_id=self.owner.pet_id, kind="car_voucher",
                                             title="借车券", note="测试用", source_event_id=f"driving:test:{n}", now=self.clock.now)

    def vouchers_left(self) -> int:
        with self.app.state.storage.connect() as conn:
            return conn.execute("SELECT COUNT(*) AS n FROM web_collection_items WHERE pet_id = ? AND kind = 'car_voucher' AND consumed_at IS NULL",
                                (self.owner.pet_id,)).fetchone()["n"]

    def world(self) -> dict:
        """一次取齐要一起回滚的四样：行程、账本、余额、活动代数。"""
        with self.app.state.storage.connect() as conn:
            journeys = conn.execute("SELECT COUNT(*) AS n FROM web_journeys WHERE pet_id = ?", (self.owner.pet_id,)).fetchone()["n"]
            fares = [r["idempotency_key"] for r in
                     conn.execute("SELECT idempotency_key FROM economy_transactions WHERE pet_id = ? AND idempotency_key LIKE 'web:travel_fee:%'",
                                  (self.owner.pet_id,))]
            activity = versions_in(conn, self.owner.pet_id).activity_epoch
        return {"journeys": journeys, "fares": fares, "activity_epoch": activity,
                "balance": self.web.economy.wallet(self.owner.pet_id).balance, "vouchers": self.vouchers_left()}

    def during_resolve(self, change) -> None:
        original = self.web.journeys.resolve

        def resolved(*args, **kwargs):
            change()
            return original(*args, **kwargs)

        self.web.journeys.resolve = resolved

    def consume_elsewhere(self) -> None:
        """别处先把券用掉（真实服务、独立事务，就像另一条路上的一次核销）。"""
        self.assertTrue(self.web.collection.consume(self.owner.pet_id, "car_voucher", self.clock.now))

    def depart(self, **kwargs):
        return self.web.journeys.depart(self.owner.user_id, self.owner.pet_id, self.owner.home_id, DRIVE, self.clock.now, **kwargs)

    # ---- 五项 ----
    def test_a_real_voucher_departs_without_charging(self) -> None:
        self.grant_voucher()
        before = self.world()

        journey = self.depart()

        after = self.world()
        self.assertEqual(journey.destination_key, DRIVE)
        self.assertEqual((after["vouchers"], after["journeys"]), (0, before["journeys"] + 1), "券核销了、行程也建了")
        self.assertEqual(after["balance"], before["balance"], "用券这趟不扣租车费")
        self.assertEqual(after["fares"], [], "不花钱的那趟不在流水里记一笔")
        # 提交里换一次代（定了新行程），提交之后 `_apply_due` 结算立即到期的那一段还会再换一次，所以只断言"确实往前走了"
        self.assertGreater(after["activity_epoch"], before["activity_epoch"], "定了新行程就换代")

    def test_a_failure_after_the_real_voucher_is_consumed_rolls_everything_back(self) -> None:
        """先确认券**确已在当前事务里核销**，再注入异常：券、行程、账本、活动代数必须一起回滚。"""
        self.grant_voucher()
        before = self.world()
        wired, seen = self.web.journeys.fee_waiver_in, []

        def consume_then_explode(conn, pet_id: str, key: str) -> bool:
            used = wired(conn, pet_id, key)  # 真实 consume_in，不是替身
            row = conn.execute("SELECT consumed_at FROM web_collection_items WHERE pet_id = ? AND kind = 'car_voucher' ORDER BY obtained_at LIMIT 1",
                               (pet_id,)).fetchone()
            seen.append(bool(used) and row is not None and row["consumed_at"] is not None)
            raise RuntimeError("券已经在这个事务里核销，提交之前炸了")

        self.web.journeys.fee_waiver_in = consume_then_explode

        with self.assertRaises(RuntimeError):
            self.depart()

        self.assertEqual(seen, [True], "前提不成立就别谈回滚：抛错之前，这个事务里确实看得到券被核销了")
        self.assertEqual(self.world(), before, "券、行程、账本、余额、活动代数五样都要回到原样")

    def test_replaying_the_same_operation_does_not_consume_a_second_voucher(self) -> None:
        self.grant_voucher(2)
        before = self.world()

        first = self.depart(operation_key="op-drive-1")
        again = self.depart(operation_key="op-drive-1")

        after = self.world()
        self.assertEqual(again.journey_id, first.journey_id, "同一次操作重放还是那一趟")
        self.assertEqual((after["journeys"], after["vouchers"]), (before["journeys"] + 1, 1), "只建一趟、只核销一张")
        self.assertEqual((after["fares"], after["balance"]), ([], before["balance"]), "也不能改成扣一次钱")

    def test_a_voucher_taken_elsewhere_while_resolving_falls_back_to_paying(self) -> None:
        self.grant_voucher()
        before = self.world()
        self.during_resolve(self.consume_elsewhere)

        journey = self.depart()

        after = self.world()
        self.assertEqual(after["balance"], before["balance"] - FEE, "券没了就照价付")
        self.assertEqual(after["fares"], [f"web:travel_fee:{journey.journey_id}"])
        self.assertEqual(after["journeys"], before["journeys"] + 1)
        self.assertGreater(after["activity_epoch"], before["activity_epoch"])

    def test_a_voucher_taken_elsewhere_with_no_money_rolls_the_whole_departure_back(self) -> None:
        self.grant_voucher()
        before = self.world()

        def gone_and_broke() -> None:
            self.consume_elsewhere()
            self.web.economy.apply(self.owner.pet_id, -self.web.economy.wallet(self.owner.pet_id).balance,
                                   EconomyTransactionType.web_travel_fee, "test:broke", reason="被别处花掉",
                                   source="test.voucher_integration", now=self.clock.now)

        self.during_resolve(gone_and_broke)

        with self.assertRaises(JourneyError) as rejected:
            self.depart()

        after = self.world()
        self.assertEqual(rejected.exception.reason, "insufficient_funds")
        self.assertEqual((after["journeys"], after["fares"]), (before["journeys"], []), "一条行程、一笔旅费都不该留下")
        self.assertEqual(after["activity_epoch"], before["activity_epoch"], "代数也要跟着回滚")


if __name__ == "__main__":
    unittest.main()
