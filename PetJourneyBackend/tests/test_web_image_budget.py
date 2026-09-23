"""生图额度：全局上限之外，还要有**按宠物**的上限（走正式装配的那个预占口）。

只有全局一层时，一只宠物、或者一位主人反复点"重画"，就能把当天全局额度吃光，别人一张都画不成。
默认 20 个单位、没有参考照时一次请求占 2 个——整个部署一天也就约 10 张图。
两层都过账本的多作用域原子预占：任一层不够就整体不占，跨进程有效，不需要新机制。

用真实装配的 `web.illustrations.reserve`，不碰真实供应商、不产生付费调用。
"""

from __future__ import annotations

import unittest

from app.schemas.runtime_internal import BudgetDenied, BudgetReservation
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class ImageBudgetTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.reserve = self.web.illustrations.reserve
        self.assertIsNotNone(self.reserve, "前提：组合根接上了生图额度预占")
        self.per_pet = int(self.settings.web_image_per_pet_daily_cap)
        self.assertGreater(self.per_pet, 0, "前提：默认配了每宠上限")

    def take(self, pet_id: str, index: int, units: int = 1):
        return self.reserve(f"illustration:{pet_id}:{index}", pet_id, units)

    def test_one_pet_cannot_eat_the_whole_deployments_budget(self) -> None:
        """核心：占满自己那一份之后就被拦住，而不是一路吃到全局上限。"""
        for index in range(self.per_pet):
            with self.subTest(attempt=index):
                self.assertIsInstance(self.take("PJ-GREEDY", index), BudgetReservation)

        denied = self.take("PJ-GREEDY", self.per_pet)

        self.assertIsInstance(denied, BudgetDenied, f"第 {self.per_pet + 1} 次该被每宠上限拦住：{denied}")

    def test_another_pet_is_not_starved_by_it(self) -> None:
        """对照：上一只把自己的份额用完了，别的宠物照样画得成——这正是加这一层的目的。"""
        for index in range(self.per_pet):
            self.take("PJ-GREEDY", index)
        self.assertIsInstance(self.take("PJ-GREEDY", self.per_pet), BudgetDenied, "前提：那一只确实被拦住了")

        self.assertIsInstance(self.take("PJ-OTHER", 0), BudgetReservation, "别的宠物不该被它拖累")

    def test_it_still_limits_when_no_global_cap_is_configured(self) -> None:
        """**这才是最要紧的一条**：没接供应商计量表时 `image_cap` 是 0，
        改之前 `limits` 会是空列表——那一刻生图**一条限制都没有**，谁点谁画，画到天亮。
        每宠这一层是并列加上去的，所以即使全局那层缺席，它照样拦得住。"""
        meter = self.web.providers.meter
        self.assertIsNone(meter, "这个环境本来就没接计量表；接了的话这条要改成同时核两层")

        for index in range(self.per_pet):
            self.assertIsInstance(self.take("PJ-NOMETER", index), BudgetReservation)

        self.assertIsInstance(self.take("PJ-NOMETER", self.per_pet), BudgetDenied,
                              "全局上限缺席时，每宠上限必须仍然生效——否则就是完全不限")

    def test_the_per_pet_layer_is_added_not_substituted(self) -> None:
        """每宠那一层是**并列加上去**的：接了计量表时两层都要过，任一层不够就整体不占。
        这里只核"加上去了"这件事本身——用预占记录里的作用域对数说话。"""
        reservation = self.take("PJ-SCOPES", 0)
        self.assertIsInstance(reservation, BudgetReservation)

        with self.web.journeys.storage.connect() as conn:
            row = conn.execute("SELECT scope_pairs_json FROM web_budget_reservations WHERE operation_id = ?",
                               (reservation.operation_id,)).fetchone()

        self.assertIn("pet:PJ-SCOPES:illustration", row["scope_pairs_json"], "每宠那一层要真的占进去")

    def test_a_request_without_a_reference_photo_costs_two_units(self) -> None:
        """没有参考照时一次请求占 2 个单位（要先画基准照）——每宠上限按单位数算，不是按次数。"""
        half = self.per_pet // 2
        for index in range(half):
            self.assertIsInstance(self.take("PJ-NOREF", index, units=2), BudgetReservation)

        if self.per_pet % 2 == 0:
            self.assertIsInstance(self.take("PJ-NOREF", half, units=2), BudgetDenied, "单位数占满就该拦住")


if __name__ == "__main__":
    unittest.main()
