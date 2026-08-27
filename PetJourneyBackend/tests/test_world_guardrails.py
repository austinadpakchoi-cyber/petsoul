from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.meal_rules import is_place_plausible_at, meal_window
from app.place_display import display_name
from app.route_planner import enforce_transport_reality
from app.schemas import JourneyPlan, RouteSegment, TransportDecision, TravelMode
from app.story_ticker import build_story_ticker


def _at_hour(hour: int) -> datetime:
    # meal_rules 约定：无时区 datetime 表示墙上时间本身（TA 所在地当地钟点），
    # 与宿主机时区无关；带时区的 instant 才需要城市名换算。
    return datetime(2026, 7, 4, hour, 30)


class MealWindowTests(unittest.TestCase):
    def test_meal_windows_cover_the_day(self) -> None:
        self.assertEqual(meal_window(_at_hour(8)), "breakfast")
        self.assertEqual(meal_window(_at_hour(12)), "lunch")
        self.assertEqual(meal_window(_at_hour(15)), "tea")
        self.assertEqual(meal_window(_at_hour(19)), "dinner")
        self.assertEqual(meal_window(_at_hour(23)), "late_night")

    def test_heavy_meal_blocked_in_the_morning(self) -> None:
        self.assertFalse(is_place_plausible_at(_at_hour(8), "老张火锅城"))
        self.assertFalse(is_place_plausible_at(_at_hour(7), "海鲜大排档"))
        self.assertTrue(is_place_plausible_at(_at_hour(8), "转角咖啡店"))

    def test_breakfast_place_blocked_late_night(self) -> None:
        self.assertFalse(is_place_plausible_at(_at_hour(23), "莲香楼早茶"))
        self.assertTrue(is_place_plausible_at(_at_hour(23), "深夜便利店"))

    def test_normal_hours_are_permissive(self) -> None:
        self.assertTrue(is_place_plausible_at(_at_hour(19), "老张火锅城"))


class PlaceDisplayTests(unittest.TestCase):
    def test_strips_latin_brand_prefix_when_chinese_is_complete(self) -> None:
        self.assertEqual(display_name("LONE STAR孤星汉堡"), "孤星汉堡")

    def test_keeps_pure_latin_names(self) -> None:
        self.assertEqual(display_name("Blue Bottle Coffee"), "Blue Bottle Coffee")

    def test_keeps_pure_chinese_names(self) -> None:
        self.assertEqual(display_name("沙坡尾猫街"), "沙坡尾猫街")

    def test_removes_parentheticals_and_clamps_length(self) -> None:
        self.assertEqual(display_name("孤星汉堡（中山路旗舰店）"), "孤星汉堡")
        long_name = "特别特别长的一个店名超过十八个字符的示例名称测试"
        self.assertTrue(display_name(long_name).endswith("…"))
        self.assertLessEqual(len(display_name(long_name)), 19)

    def test_handles_empty(self) -> None:
        self.assertEqual(display_name(None), "")
        self.assertEqual(display_name("  "), "")


class TransportFloorTests(unittest.TestCase):
    def _plan_with_segment(self, segment: RouteSegment) -> JourneyPlan:
        return JourneyPlan(
            pet_id="pet-1",
            city="厦门",
            generated_at=datetime.now(timezone.utc),
            provider="test",
            horizon_hours=24,
            summary="测试计划",
            current_activity="walk",
            transport_decision=TransportDecision(
                selected_mode=segment.mode,
                reason="测试",
                autonomy_note="测试",
            ),
            route_segments=[segment],
            stops=[],
            places=[],
        )

    def test_walk_duration_clamped_to_speed_floor(self) -> None:
        segment = RouteSegment(
            id="teleport",
            mode=TravelMode.walk,
            title="走路",
            detail="",
            from_place="A",
            to_place="B",
            distance_meters=3200,
            duration_seconds=60,
            provider="test",
        )
        plan = enforce_transport_reality(self._plan_with_segment(segment))
        self.assertGreaterEqual(plan.route_segments[0].duration_seconds, 2000)

    def test_plausible_duration_untouched(self) -> None:
        segment = RouteSegment(
            id="ok",
            mode=TravelMode.walk,
            title="走路",
            detail="",
            from_place="A",
            to_place="B",
            distance_meters=800,
            duration_seconds=900,
            provider="test",
        )
        plan = enforce_transport_reality(self._plan_with_segment(segment))
        self.assertEqual(plan.route_segments[0].duration_seconds, 900)

    def test_flight_has_absolute_minimum(self) -> None:
        segment = RouteSegment(
            id="hop",
            mode=TravelMode.flight,
            title="飞",
            detail="",
            from_place="A",
            to_place="B",
            distance_meters=90_000,
            duration_seconds=300,
            provider="test",
        )
        plan = enforce_transport_reality(self._plan_with_segment(segment))
        self.assertGreaterEqual(plan.route_segments[0].duration_seconds, 1800)


class StoryTickerTests(unittest.TestCase):
    def test_deterministic_within_the_same_hour(self) -> None:
        now = _at_hour(9)
        first = build_story_ticker(limit=5, now=now)
        second = build_story_ticker(limit=5, now=now)
        self.assertEqual([item.text for item in first.items], [item.text for item in second.items])

    def test_respects_limit_and_has_no_pet_names(self) -> None:
        response = build_story_ticker(limit=3, now=_at_hour(9))
        self.assertEqual(len(response.items), 3)
        for item in response.items:
            self.assertNotIn("小福", item.text)
            self.assertTrue(item.text)


if __name__ == "__main__":
    unittest.main()


class CityTimezoneTests(unittest.TestCase):
    """UI/UX 审计 P0-2：地图昼夜跟 TA 所在地的时间，而不是主人设备时区。"""

    def test_local_wall_time_xiamen_is_utc_plus_8(self) -> None:
        from datetime import datetime, timezone

        from app.city_timezones import local_wall_time

        utc_now = datetime(2026, 7, 4, 16, 30, tzinfo=timezone.utc)
        wall = local_wall_time(utc_now, "厦门")
        self.assertEqual((wall.hour, wall.minute), (0, 30))  # 16:30 UTC → 次日 00:30 厦门

    def test_local_wall_time_la_is_pacific(self) -> None:
        from datetime import datetime, timezone

        from app.city_timezones import local_wall_time

        utc_now = datetime(2026, 7, 4, 16, 30, tzinfo=timezone.utc)
        wall = local_wall_time(utc_now, "洛杉矶")
        self.assertEqual((wall.hour, wall.minute), (9, 30))  # 夏令时 PDT = UTC-7

    def test_unknown_city_falls_back_to_shanghai(self) -> None:
        from datetime import datetime, timezone

        from app.city_timezones import local_wall_time

        utc_now = datetime(2026, 7, 4, 16, 0, tzinfo=timezone.utc)
        wall = local_wall_time(utc_now, "某个不存在的小镇")
        self.assertEqual(wall.hour, 0)
