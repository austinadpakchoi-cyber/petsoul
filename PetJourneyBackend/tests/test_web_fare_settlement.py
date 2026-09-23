"""这趟的钱和这趟行程同生共死：核销一张券，或者扣旅费，都在写行程的那个事务里（CR-C9）。

分两个事务写的话，进程死在中间就会留下一趟没付钱的行程，或者券已经核销而行程没建——
幂等键能防"扣两次"，防不了"根本没扣"。

生产上的驾校借车券由凭证侧装配注入；这里用一张自备的券验**旅程这一侧**的契约：
`waiver_available` 只查看，`fee_waiver_in(conn, pet_id, key)` 用调用方那个连接核销。
没装配同事务版本时，用券这条路要在动任何业务数据之前被拒掉。
用脚本化的假地图，不联网、不产生付费调用。
"""

from __future__ import annotations

import unittest

from app.schemas.base import EconomyTransactionType
from app.web_journey.errors import JourneyError
from test_web_commit_boundary import CommitBoundaryBase


class FareSettlementTests(CommitBoundaryBase):
    # ---- 券：用一张自备的券验"旅程这一侧"的契约 ----
    def grant_voucher(self) -> None:
        with self.app.state.storage.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS fare_voucher (voucher_id INTEGER PRIMARY KEY AUTOINCREMENT, pet_id TEXT NOT NULL, used_for TEXT)")
            conn.execute("INSERT INTO fare_voucher (pet_id, used_for) VALUES (?, NULL)", (self.owner.pet_id,))
        self.web.journeys.waiver_available = lambda pet_id, key: key == "harbour_cafe" and self.vouchers_left() > 0

    def vouchers_left(self) -> int:
        with self.app.state.storage.connect() as conn:
            return conn.execute("SELECT COUNT(*) AS n FROM fare_voucher WHERE pet_id = ? AND used_for IS NULL",
                                (self.owner.pet_id,)).fetchone()["n"]

    def wire_same_transaction_waiver(self, *, then_fail: bool = False):
        """装上同事务核销：**只用调用方给的那个连接**，这正是要请凭证侧实现的 `consume_in(conn, …)` 的形状。"""
        def consume_in(conn, pet_id: str, key: str) -> bool:
            row = conn.execute("SELECT voucher_id FROM fare_voucher WHERE pet_id = ? AND used_for IS NULL ORDER BY voucher_id LIMIT 1",
                               (pet_id,)).fetchone()
            if row is None:
                return False
            used = conn.execute("UPDATE fare_voucher SET used_for = ? WHERE voucher_id = ? AND used_for IS NULL",
                                (key, row["voucher_id"])).rowcount == 1
            if then_fail:
                raise RuntimeError("券已经核销，紧接着这一步出错了")
            return used

        self.web.journeys.fee_waiver_in = consume_in

    # ---- 行程与旅费同生共死（CR-C9） ----
    def test_the_journey_and_the_fare_are_written_together(self) -> None:
        self.coins(50)
        before = self.balance()

        journey = self.web.journeys.depart(self.owner.user_id, self.owner.pet_id, self.owner.home_id, "harbour_cafe", self.clock.now)

        self.assertEqual(self.fares(), [f"web:travel_fee:{journey.journey_id}"], "旅费的幂等键要绑定这一趟")
        self.assertEqual(self.balance(), before - 8)

    def test_a_crash_before_the_fare_is_written_leaves_no_journey(self) -> None:
        """进程在“写完行程、还没扣费”之间死掉：以前会留下一趟没付钱的行程，现在整笔一起回滚。"""
        self.coins(50)
        before = self.balance()

        def died(*args, **kwargs):
            raise RuntimeError("进程在写完行程之后、扣费之前死了")

        self.web.journeys.economy.apply_in = died
        try:
            with self.assertRaises(RuntimeError):
                self.web.journeys.depart(self.owner.user_id, self.owner.pet_id, self.owner.home_id, "harbour_cafe", self.clock.now)
        finally:
            del self.web.journeys.economy.apply_in

        self.assertEqual(self.journey_rows(), 0, "行程必须跟着一起回滚，不能留下一趟没付钱的")
        self.assertEqual(self.balance(), before)
        self.assertEqual(self.fares(), [])

    def test_money_spent_elsewhere_while_resolving_cancels_the_whole_departure(self) -> None:
        """出发前余额够，解析地点期间被别处花掉：事务里扣不上，行程也不该留下来。"""
        self.coins(50)
        self.during_resolve(lambda: self.web.economy.apply(self.owner.pet_id, -self.balance(), EconomyTransactionType.web_travel_fee,
                                                           "test:spent-elsewhere", reason="被别处花掉", source="test.commit_boundary",
                                                           now=self.clock.now))

        with self.assertRaises(JourneyError) as rejected:
            self.web.journeys.depart(self.owner.user_id, self.owner.pet_id, self.owner.home_id, "harbour_cafe", self.clock.now)

        self.assertEqual(rejected.exception.reason, "insufficient_funds")
        self.assertEqual(self.journey_rows(), 0, "回滚之后连一条取消掉的行程都不该留下")
        self.assertEqual(self.fares(), [])

    # ---- 券也要在同一个事务里核销（CR-C9） ----
    def test_the_voucher_path_is_refused_before_anything_is_written_when_it_is_not_wired(self) -> None:
        """同事务核销没装配：这条路直接拒掉——不能留下没付钱的行程，也不能闷声按原价扣钱。

        显式制造"没装配"，不依赖默认值：收藏服务提供 `consume_in` 之后正式装配就会接上（见
        `test_web_voucher_integration.py`），但"钩子缺席时必须拒绝"这条安全属性仍然要守住。
        """
        self.coins(50)
        self.grant_voucher()
        self.web.journeys.fee_waiver_in = None
        before = self.balance()

        with self.assertRaises(JourneyError) as refused:
            self.web.journeys.depart(self.owner.user_id, self.owner.pet_id, self.owner.home_id, "harbour_cafe", self.clock.now)

        self.assertEqual(refused.exception.reason, "waiver_unavailable")
        self.assertEqual(self.journey_rows(), 0, "拒绝要发生在任何业务写入之前")
        self.assertEqual(self.balance(), before, "也不能偷偷按原价出发")
        self.assertEqual(self.vouchers_left(), 1, "券一张都没动")
        self.assertEqual(self.fares(), [])

    def test_using_a_voucher_departs_without_charging(self) -> None:
        self.coins(50)
        self.grant_voucher()
        self.wire_same_transaction_waiver()
        before = self.balance()

        journey = self.web.journeys.depart(self.owner.user_id, self.owner.pet_id, self.owner.home_id, "harbour_cafe", self.clock.now)

        self.assertEqual(journey.destination_key, "harbour_cafe")
        self.assertEqual(self.balance(), before, "用券这趟不扣旅费")
        self.assertEqual(self.vouchers_left(), 0, "券核销了")
        self.assertEqual(self.fares(), [], "不花钱的那趟不在流水里记一笔")

    def test_a_failure_right_after_the_voucher_is_used_rolls_everything_back(self) -> None:
        self.coins(50)
        self.grant_voucher()
        self.wire_same_transaction_waiver(then_fail=True)
        before = self.balance()

        with self.assertRaises(RuntimeError):
            self.web.journeys.depart(self.owner.user_id, self.owner.pet_id, self.owner.home_id, "harbour_cafe", self.clock.now)

        self.assertEqual(self.vouchers_left(), 1, "券要跟着回滚，不能白白用掉一张")
        self.assertEqual(self.journey_rows(), 0)
        self.assertEqual(self.balance(), before)

    def test_replaying_the_same_operation_does_not_use_a_second_voucher(self) -> None:
        self.coins(50)
        self.grant_voucher()
        self.wire_same_transaction_waiver()

        first = self.web.journeys.depart(self.owner.user_id, self.owner.pet_id, self.owner.home_id, "harbour_cafe", self.clock.now,
                                         operation_key="op-voucher-1")
        again = self.web.journeys.depart(self.owner.user_id, self.owner.pet_id, self.owner.home_id, "harbour_cafe", self.clock.now,
                                         operation_key="op-voucher-1")

        self.assertEqual(again.journey_id, first.journey_id, "同一次操作重放还是那一趟")
        self.assertEqual(self.journey_rows(), 1)
        self.assertEqual(self.vouchers_left(), 0, "券只核销一次")
        self.assertEqual(self.fares(), [], "也不能改成扣一次钱")

    def test_a_voucher_taken_by_someone_else_while_resolving_falls_back_to_paying(self) -> None:
        """出发前券还在，解析地点期间被别处用掉：按既定费用规则付钱，事务照样完整。"""
        self.coins(50)
        self.grant_voucher()
        self.wire_same_transaction_waiver()
        before = self.balance()

        def used_elsewhere() -> None:
            with self.app.state.storage.connect() as conn:
                conn.execute("UPDATE fare_voucher SET used_for = '别处' WHERE pet_id = ? AND used_for IS NULL", (self.owner.pet_id,))

        self.during_resolve(used_elsewhere)

        journey = self.web.journeys.depart(self.owner.user_id, self.owner.pet_id, self.owner.home_id, "harbour_cafe", self.clock.now)

        self.assertEqual(self.balance(), before - 8, "券没了就照价付")
        self.assertEqual(self.fares(), [f"web:travel_fee:{journey.journey_id}"])
        self.assertEqual(self.journey_rows(), 1)

    def test_a_voucher_taken_by_someone_else_with_no_money_left_cancels_the_whole_departure(self) -> None:
        self.grant_voucher()
        self.wire_same_transaction_waiver()

        def used_elsewhere_and_broke() -> None:
            with self.app.state.storage.connect() as conn:
                conn.execute("UPDATE fare_voucher SET used_for = '别处' WHERE pet_id = ? AND used_for IS NULL", (self.owner.pet_id,))
            self.web.economy.apply(self.owner.pet_id, -self.balance(), EconomyTransactionType.web_travel_fee, "test:broke",
                                   reason="被别处花掉", source="test.commit_boundary", now=self.clock.now)

        self.during_resolve(used_elsewhere_and_broke)

        with self.assertRaises(JourneyError) as rejected:
            self.web.journeys.depart(self.owner.user_id, self.owner.pet_id, self.owner.home_id, "harbour_cafe", self.clock.now)

        self.assertEqual(rejected.exception.reason, "insufficient_funds")
        self.assertEqual(self.journey_rows(), 0, "券没了又付不起：整笔回滚，一条行程都不留")

if __name__ == "__main__":
    unittest.main()
