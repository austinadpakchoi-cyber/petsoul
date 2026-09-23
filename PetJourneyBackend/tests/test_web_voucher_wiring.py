"""借车券的核销要和行程、扣费在同一个事务里（C 的 CR-C9-b，A 的 `consume_in`，I 的装配）。

分两段写会留下两种坏结果：券已经核销、行程没建；或者行程建了、钱没扣。
幂等键能防"扣两次"，防不了"根本没扣"。所以核销必须发生在写行程的那个事务里。

这里验的是**装配**：`web_credentials_wiring` 有没有把 `journeys.fee_waiver_in` 接到收藏服务的同事务核销上。
依赖（`collection.consume_in`）已经落地，所以缺失一律**报失败**，没有跳过分支，也不用替身兜底——
用的就是装配好的那个回调本身。
"""

from __future__ import annotations

import unittest

from app.schemas import EconomyTransactionType
from app.web_journey.errors import JourneyError
from app.web_platform.uow import unit_of_work
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class VoucherWiringBase(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("voucher-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.journeys = self.web.journeys
        self.journeys.can_drive = lambda pet_id: True  # 驾照规则另有用例；这里只看借车券的事务边界
        self.web.economy.apply(self.owner.pet_id, 200, EconomyTransactionType.web_reward, f"test:grant:{self.owner.pet_id}",
                               reason="测试补给", source="test")

    def give_voucher(self) -> None:
        with unit_of_work(self.app.state.storage) as conn:
            self.web.collection.keepsake(conn, user_id=self.owner.user_id, pet_id=self.owner.pet_id, kind="car_voucher",
                                         title="借车券", note="测试用", source_event_id="driving:test", now=self.clock.now)

    def vouchers_left(self) -> int:
        with self.app.state.storage.connect() as conn:
            return conn.execute("SELECT COUNT(*) AS n FROM web_collection_items WHERE pet_id = ? AND kind = 'car_voucher' AND consumed_at IS NULL",
                                (self.owner.pet_id,)).fetchone()["n"]

    def journeys_count(self) -> int:
        with self.app.state.storage.connect() as conn:
            return conn.execute("SELECT COUNT(*) AS n FROM web_journeys WHERE pet_id = ?", (self.owner.pet_id,)).fetchone()["n"]

    def drive(self):
        return self.journeys.depart(self.owner.user_id, self.owner.pet_id, self.owner.home_id, "local:drive_trip", self.clock.now)


class VoucherWiringPresenceTests(VoucherWiringBase):
    """依赖与装配都必须在。缺了就是失败，不跳过。"""

    def test_the_collection_service_offers_the_same_transaction_consumption(self) -> None:
        consume_in = getattr(self.web.collection, "consume_in", None)
        self.assertIsNotNone(consume_in, "收藏服务必须提供同事务核销 consume_in（包 A 已交付）")
        self.assertTrue(callable(consume_in))

    def test_the_composition_wires_the_fee_waiver_callback(self) -> None:
        self.assertIsNotNone(self.journeys.fee_waiver_in,
                             "装配必须把 fee_waiver_in 接上；没接上等于用券路径只能被拒，不是可接受状态")

    def test_the_wired_callback_actually_reaches_the_collection_service(self) -> None:
        """不是"接了个什么东西"就算数：它必须真的落到收藏服务的同事务核销上。"""
        self.give_voucher()
        seen: list[tuple[str, str]] = []
        real = self.web.collection.consume_in

        def watched(conn, pet_id: str, kind: str, now=None) -> bool:
            seen.append((pet_id, kind))
            return real(conn, pet_id, kind, now)

        self.web.collection.consume_in = watched
        self.addCleanup(lambda: setattr(self.web.collection, "consume_in", real))

        self.drive()

        self.assertEqual(seen, [(self.owner.pet_id, "car_voucher")], "装配的回调要打到收藏服务的 consume_in 上")


class VoucherTransactionTests(VoucherWiringBase):
    """用装配好的真实回调走完整条路，不安装任何替身。"""

    def test_the_voucher_and_the_journey_commit_together(self) -> None:
        self.give_voucher()
        before = self.web.economy.wallet(self.owner.pet_id).balance

        self.drive()

        self.assertEqual((self.vouchers_left(), self.journeys_count()), (0, 1), "券核销了、行程也建了")
        self.assertEqual(self.web.economy.wallet(self.owner.pet_id).balance, before, "用券这次不扣租车费")

    def test_a_failure_after_the_voucher_is_consumed_rolls_both_back(self) -> None:
        """同事务的意义：**券已经在本事务里核销之后**再失败，券也要跟着回滚。

        故障点必须在核销之后、提交之前——放在 `repo.insert` 之后是不够的，那时 `_settle_fare` 还没跑，券根本没动。
        这里包住装配好的那个回调：先让它真的核销，确认"这个事务里看得到 consumed_at 已写"，再抛错。
        """
        self.give_voucher()
        wired = self.journeys.fee_waiver_in
        self.assertIsNotNone(wired, "前提：装配已接上")
        seen_consumed: list[bool] = []

        def consume_then_explode(conn, pet_id: str, key: str) -> bool:
            used = wired(conn, pet_id, key)
            row = conn.execute("SELECT consumed_at FROM web_collection_items WHERE pet_id = ? AND kind = 'car_voucher'", (pet_id,)).fetchone()
            seen_consumed.append(bool(used) and row is not None and row["consumed_at"] is not None)
            raise RuntimeError("券已经核销，提交之前炸了")

        self.journeys.fee_waiver_in = consume_then_explode

        with self.assertRaises(RuntimeError):
            self.drive()

        self.assertEqual(seen_consumed, [True], "前提：抛错之前，券在这个事务里确实已经核销")
        self.assertEqual((self.vouchers_left(), self.journeys_count()), (1, 0), "回滚之后券退回来了，行程也没留下")

    def test_a_voucher_used_elsewhere_falls_back_to_paying(self) -> None:
        """券在这中间被别处用掉了：照既定费用规则付钱，不能白走。"""
        self.give_voucher()
        with self.app.state.storage.connect() as conn:
            conn.execute("UPDATE web_collection_items SET consumed_at = ? WHERE pet_id = ? AND kind = 'car_voucher'",
                         (self.clock.now.isoformat(), self.owner.pet_id))
        before = self.web.economy.wallet(self.owner.pet_id).balance

        self.drive()

        self.assertEqual(self.journeys_count(), 1)
        self.assertLess(self.web.economy.wallet(self.owner.pet_id).balance, before, "没券就照常扣租车费")

    def test_a_missing_callback_refuses_instead_of_half_writing(self) -> None:
        """万一将来装配被改坏（回调没接上）：宁可拒掉，也不留下"券用了、行程没建"。"""
        self.give_voucher()
        self.journeys.fee_waiver_in = None  # 故意模拟装配坏掉

        with self.assertRaises(JourneyError) as refused:
            self.drive()

        self.assertEqual(refused.exception.reason, "waiver_unavailable")
        self.assertEqual((self.vouchers_left(), self.journeys_count()), (1, 0), "券没动，行程也没建")


if __name__ == "__main__":
    unittest.main()
