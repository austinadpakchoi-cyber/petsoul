"""「TA 现在在哪一段」只有一份判断：`snapshot.current_leg`（应统筹之请导出，供 W1 地图复用）。

W1 的 `world.py` 原先取的是**主段**（`kind == "main"` 的第一条）。多段行程里那是错的：
打车→飞机→火车，TA 还在打车去机场的路上，报的却是飞机那段——
地图会把位置点画到**航线上**、`mode` 显示成飞机。

回退顺序（换乘间隙取刚过去那段、都没到取第一段）是**产品判断**，不是能各写各的实现细节。
两处一旦漂开，地图上「TA 在哪一段」和行程详情页会各说一套，**而这种不一致不会报错**。
所以这一份判断在这里单独钉住：`map_snapshot`、`brief`、W1 都调它。

纯计算：不开库、不联网、不调供应商。
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.web_journey.repository import LegRecord
from app.web_journey.snapshot import current_leg, leg_in_progress

T0 = datetime(2026, 9, 24, 4, 0, tzinfo=timezone.utc)
PLACE = {"node_id": "n", "name": "某处", "kind": "stop", "timezone": "Asia/Hong_Kong", "lat": 22.3, "lng": 114.2, "verified": False}


def leg(seq: int, kind: str, mode: str, start_min: int, end_min: int) -> LegRecord:
    return LegRecord(leg_id=f"leg-{seq}", journey_id="j-1", sequence=seq, direction="outbound", kind=kind, mode=mode, role="passenger",
                     world_service_id=None, origin=dict(PLACE), destination=dict(PLACE),
                     starts_at=T0 + timedelta(minutes=start_min), ends_at=T0 + timedelta(minutes=end_min),
                     time_basis="scheduled", freshness="live", position_basis="interpolated")


# 打车去机场 → （间隙）→ 飞机 → 火车：W1 那个缺陷正是在这种行程上显形的
TAXI = leg(1, "connection", "taxi", 0, 40)
FLIGHT = leg(2, "main", "flight", 90, 210)
TRAIN = leg(3, "main", "train", 240, 300)
TRIP = [TAXI, FLIGHT, TRAIN]


class CurrentLegTests(unittest.TestCase):
    def test_it_returns_the_leg_actually_underway(self) -> None:
        self.assertIs(current_leg(TRIP, T0 + timedelta(minutes=20)), TAXI)
        self.assertIs(current_leg(TRIP, T0 + timedelta(minutes=150)), FLIGHT)

    def test_during_a_connection_gap_it_stays_on_the_leg_just_finished(self) -> None:
        """下了车、还没登机：TA 人在机场，**不是**在航线上——这正是 W1 取主段时画错点的那一刻。"""
        gap = T0 + timedelta(minutes=60)

        self.assertIsNone(leg_in_progress(TRIP, gap), "间隙里没有正在走的那一段")
        self.assertIs(current_leg(TRIP, gap), TAXI)
        self.assertNotEqual(current_leg(TRIP, gap).mode, "flight", "取主段的话这里会显示成飞机")

    def test_before_anything_starts_it_is_the_first_leg(self) -> None:
        self.assertIs(current_leg(TRIP, T0 - timedelta(minutes=5)), TAXI)

    def test_after_everything_is_over_it_is_the_last_leg(self) -> None:
        self.assertIs(current_leg(TRIP, T0 + timedelta(minutes=999)), TRAIN)

    def test_the_boundaries_belong_to_the_leg_that_is_starting(self) -> None:
        """闭开区间 `[starts_at, ends_at)`：结束那一刻已经不算在那一段里了。"""
        self.assertIs(leg_in_progress(TRIP, FLIGHT.starts_at), FLIGHT, "起飞那一刻算飞机这段")
        self.assertIsNone(leg_in_progress(TRIP, FLIGHT.ends_at), "落地那一刻已经不在飞机上")
        self.assertIs(current_leg(TRIP, FLIGHT.ends_at), FLIGHT, "但人还在那里，不会跳到火车")

    def test_an_empty_itinerary_has_no_current_leg(self) -> None:
        """空行程返回 None，而不是抛——调用方（W1 是纯读路由）拿到的是"不知道"，不是崩溃。"""
        self.assertIsNone(current_leg([], T0))
        self.assertIsNone(leg_in_progress([], T0))

    def test_it_does_not_touch_what_it_was_given(self) -> None:
        """纯函数：不改入参、不新建对象——返回的就是传进来的那一条。"""
        legs = list(TRIP)

        picked = current_leg(legs, T0 + timedelta(minutes=60))

        self.assertEqual(legs, TRIP, "入参列表不该被动过")
        self.assertIn(picked, TRIP)


if __name__ == "__main__":
    unittest.main()
