"""出门前按作息复核（真实验收 E2 的确定性版本）。

真实验收里那趟“原计划 06:21 出门、TA 还在睡”的港澳行程，要到自然时间才判得了。
这里用假时钟把同一条规则钉死：**已经定好的远行，如果出门时刻落在 TA 睡觉的时段，
出门前复核必须改到 TA 醒着能赶上的班次；实在成不了就取消并把旅费退回，家庭频道恰好说明一次。**

构造方式和真实那趟一样：定行程的时候按的是当时的作息（能早起），之后作息变回平常（07:30 起），
复核时就要按新的作息重新安排——不会半夜把 TA 叫起来出门。
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.schemas import EconomyTransactionType
from app.web_providers.geo import PlaceCandidate
from web_base import WebPlatformTestBase, FakeClock
from web_provider_fakes import FakeGeo

HK = ZoneInfo("Asia/Hong_Kong")
HK_NIGHT = datetime(2026, 9, 23, 14, 30, tzinfo=timezone.utc)  # 香港 22:30：当天已经来不及往返，只能排第二天早上
CAFE = PlaceCandidate(provider="amap", place_id="amap:TESTCAFE", name="测试老城咖啡", address="议事亭前地附近", lat=22.1937, lng=113.5391,
                      category="咖啡厅", attribution="地点资料：高德地图", fetched_at="2026-09-23T14:29:00Z")
SQUARE = PlaceCandidate(provider="amap", place_id="amap:TESTSQUARE", name="议事亭前地", address=None, lat=22.1935, lng=113.5393,
                        category="广场", attribution="地点资料：高德地图")


class MacauGeo(FakeGeo):
    def __init__(self, minutes: int = 8, fail: bool = False) -> None:
        super().__init__(place=CAFE, minutes=minutes, fail=fail)
        self.known = {"议事亭前地": SQUARE}

    def route(self, region, mode, origin, destination, max_age=None):
        return None if self.fail else super().route(region, mode, origin, destination)


class PreDepartureReviewTests(WebPlatformTestBase):
    """E2 的规则，不等自然时间。"""

    demo_catalog = False
    settle_on_read = True  # 读接口是纯读：这组按“任务进程跟得上”验证

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(HK_NIGHT).install(self)
        self.geo = MacauGeo()

    def _scheduled_while_asleep(self, name: str):
        """定下一趟出门时刻落在 TA 睡觉时段的远行：定的时候当作 TA 能早起，之后恢复平常作息。"""
        user = self.user(name)
        user.upload_pet("小海", "cat")
        user.move_in()
        self.web.journeys.geo = self.geo
        self.web.economy.apply(user.pet_id, 180, EconomyTransactionType.web_reward, f"test:grant:{user.pet_id}", reason="测试补给", source="test")
        real_awake = self.web.journeys.awake_at
        self.web.journeys.awake_at = lambda pet_id, at: True  # 定行程时：按“那时的作息”最早一班也能赶上
        try:
            trip = user.post("/journey/depart", {"destination_key": "macau_ferry"}).json()
        finally:
            self.web.journeys.awake_at = real_awake  # 复核时：平常作息（23:30 睡、07:30 起）
        departed = datetime.fromisoformat(trip["legs"][0]["times"]["planned_departure_utc"].replace("Z", "+00:00"))
        self.assertFalse(real_awake(user.pet_id, departed), "前提：原计划的出门时刻确实落在 TA 睡觉的时段")
        return user, trip["journey_id"], departed

    def _family_replan_notes(self, user) -> list[str]:
        items = user.get(f"/communicator/{user.pet_id}/messages").json()["items"]
        return [m["text"] for m in items if m["channel"] == "family" and ("改成" in m["text"] or "去不成" in m["text"])]

    def test_departure_while_asleep_is_moved_to_a_sailing_the_pet_can_catch_awake(self) -> None:
        user, journey_id, departed = self._scheduled_while_asleep("e2-asleep")
        self.clock.now = departed - timedelta(minutes=30)  # 进入出门前 45 分钟的复核窗口

        changed = self.web.journeys.refresh_scheduled(self.clock.now, stale_after=timedelta(minutes=5))

        self.assertEqual(changed, 1, "出门前复核了这趟")
        snapshot = user.get("/journey/map").json()
        new_departure = datetime.fromisoformat(snapshot["legs"][0]["times"]["planned_departure_utc"].replace("Z", "+00:00"))
        self.assertTrue(self.web.journeys.awake_at(user.pet_id, new_departure),
                        f"改签后的出门时刻要在 TA 醒着的时候：{new_departure.astimezone(HK):%H:%M}")
        self.assertGreater(new_departure, departed, "只会往后改，不会把 TA 提前叫起来")
        self.assertGreaterEqual(snapshot["itinerary_version"], 2, "改签要换一个行程版本")
        self.assertEqual(len(self._family_replan_notes(user)), 1, "家庭频道恰好说明一次")
        self.assertEqual(self.web.journeys.refresh_scheduled(self.clock.now, stale_after=timedelta(minutes=5)), 0, "同一版本只复核一次")

    def test_when_it_cannot_be_rescheduled_the_fare_is_refunded_exactly_once(self) -> None:
        user, journey_id, departed = self._scheduled_while_asleep("e2-cancel")
        fee = user.get("/journey/map").json().get("fee")
        before = user.home()["wallet"]["balance"]
        self.clock.now = departed - timedelta(minutes=30)
        self.geo.fail = True  # 复核时资料完全拿不到：今天成不了

        self.assertEqual(self.web.journeys.replan(journey_id, self.clock.now), "cancelled")

        after = user.home()["wallet"]["balance"]
        self.assertEqual(after - before, fee or 40, "旅费原样退回")
        bank = next(c for c in user.get(f"/credentials?pet_id={user.pet_id}").json() if c["kind"] == "bank_card")
        ledger = user.get(f"/credentials/{bank['credential_id']}").json()["ledger"]
        refunds = [e for e in ledger if e.get("ref_kind") == "journey" and e.get("ref_id") == journey_id and e["delta"] > 0]
        self.assertEqual(len(refunds), 1, "退款恰好记一笔，指回这趟行程")
        self.assertEqual(len(self._family_replan_notes(user)), 1, "家庭频道恰好说明一次")
        self.assertEqual(user.home()["presence"], "at_home", "取消之后 TA 还在家")
        self.assertEqual(user.home()["wallet"]["balance"], after, "再读一次不会重复退款")

    def test_review_does_not_touch_trips_outside_the_window_or_already_departed(self) -> None:
        user, journey_id, departed = self._scheduled_while_asleep("e2-window")
        self.clock.now = departed - timedelta(hours=3)  # 离出门还早
        self.assertEqual(self.web.journeys.refresh_scheduled(self.clock.now, stale_after=timedelta(minutes=5)), 0, "还没进窗口就不动它")
        self.assertEqual(user.get("/journey/map").json()["itinerary_version"], 1)

        self.clock.now = departed + timedelta(minutes=5)  # 已经出门了
        self.assertEqual(self.web.journeys.refresh_scheduled(self.clock.now, stale_after=timedelta(minutes=5)), 0, "已经出门的不再改签")
        self.assertEqual(self.web.journeys.replan(journey_id, self.clock.now), "unchanged")


if __name__ == "__main__":
    unittest.main()
