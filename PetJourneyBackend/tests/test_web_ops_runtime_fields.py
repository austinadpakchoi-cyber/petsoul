"""`/ops/runtime` 暴露 `next_review_at`（CR-B11 的接口配合那一半，归 I）。

B 那边已经在写：`brain_life._commit` 的 stayed 分支写的是显式的 `next_review_at`
（"先留在家，到这个时刻再重新考虑"），不再是当初那个 `None`。
但运维只读接口的响应模型里没有这个字段，于是**写进去了却看不见**——排查"TA 为什么这么安静"时，
分不清"到点还没到"和"根本没写有效期"。这里只加一个可选字段把已有的值暴露出来，不改 B 的任何实现。

`next_review_at` 与 `next_check_at` 是两回事，这也是本文件要钉住的：
  `next_check_at`  —— **此刻**按当前事实算出来的下次查看时间（每次请求现算，不落库）；
  `next_review_at` —— **当时那次决定**留下的有效期（决定时落库，之后不随请求变）。

真实装配、真实库、假时钟；不联网、不产生付费调用。
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class OpsRuntimeFieldTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("ops-fields-owner")
        self.owner.adopt_and_move_in("adopt-lan")

    def runtime(self) -> dict:
        response = self.client.get(f"/api/v1/web/ops/runtime/{self.owner.pet_id}")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_a_decision_deadline_shows_up_in_ops_runtime(self) -> None:
        """写下"两小时后再看"之后，运维接口要能看见这个时刻。"""
        self.assertIsNone(self.runtime()["next_review_at"], "还没做过决定：这里应当是空的，不是缺字段")

        review_at = self.clock.now.replace(microsecond=0) + timedelta(hours=2)
        self.web.projector.runtime.record_decision(self.owner.pet_id, self.clock.now, by="rule", next_review_at=review_at)

        detail = self.runtime()
        self.assertEqual(detail["next_review_at"], review_at.isoformat().replace("+00:00", "Z"),
                         f"要原样回出决定时写下的时刻：{detail['next_review_at']}")
        self.assertEqual(detail["last_decision_by"], "rule", "同一次决定的其它字段也要对得上")

    def test_next_review_at_is_not_next_check_at(self) -> None:
        """两个字段不能混用：一个是当时那次决定的有效期，一个是此刻现算的下次查看时间。

        做法：先写一个**很远**的 `next_review_at`，然后看 `next_check_at`——
        如果两者相等，说明接口把同一个值填进了两处，那这个新字段就没有意义。
        """
        far = self.clock.now.replace(microsecond=0) + timedelta(days=7)
        self.web.projector.runtime.record_decision(self.owner.pet_id, self.clock.now, by="rule", next_review_at=far)

        detail = self.runtime()

        self.assertIsNotNone(detail["next_review_at"], "决定的有效期要在")
        self.assertNotEqual(detail["next_review_at"], detail["next_check_at"],
                            f"这两个字段必须是各自的含义，不能是同一个值：{detail['next_review_at']}")

    def test_the_field_is_optional_so_old_clients_keep_working(self) -> None:
        """新增的是**可选**字段（x-additive）：没做过决定时是 null，而不是接口报错或少一个键。"""
        detail = self.runtime()

        self.assertIn("next_review_at", detail, "字段本身要一直在，前端才好写判断")
        self.assertIsNone(detail["next_review_at"])


if __name__ == "__main__":
    unittest.main()
