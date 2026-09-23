"""爪爪驾校的确定性驾驶模拟与复算（服务端判定的依据）。

测试驾驶员（tests/driving_bots.py）只通过操作影响结果，和真人一样；这里验证判定规则、失败条件、分段复算与操作记录校验。
"""

from __future__ import annotations

import unittest

from app.web_driving.courses import course_for
from app.web_driving.replay import InputError, Replay, validate
from driving_bots import Driver, curve_bot, reverse_park_bot, route_bot, side_park_bot


def kinds(driver: Driver) -> list[str]:
    return [e["k"] for e in driver.replay.events]


def penalties(driver: Driver) -> list[tuple[str, int]]:
    return [(e["k"], e["p"]) for e in driver.replay.events if e["p"]]


class TrainingGroundTests(unittest.TestCase):
    def test_each_item_can_be_completed_cleanly_in_both_variants(self) -> None:
        for variant, sign in (("a", 1), ("b", -1)):
            for item, bot in (("reverse_park", reverse_park_bot(2.8, 2.0, sign)), ("side_park", side_park_bot(3.8, 0.8, sign)), ("curve", curve_bot(sign))):
                with self.subTest(item=item, variant=variant):
                    driver = Driver(course_for(item, variant)).run(bot)
                    self.assertEqual((driver.replay.status, penalties(driver)), ("done", []))

    def test_a_continuous_line_press_counts_once_and_a_new_press_counts_again(self) -> None:
        course = course_for("reverse_straight", "a")
        replay = Replay(course)
        # 满舵前进：车头往左偏，压到左边线后一直压着，只算一次
        replay.apply([{"t": 0, "c": "s", "v": 12}, {"t": 0, "c": "t", "v": 1}], 90)
        lines = [e for e in replay.events if e["k"] == "line"]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["p"], 5)
        self.assertEqual(replay.pressed, 1, "还压着线")

    def test_each_cone_counts_once_and_leaving_the_field_fails(self) -> None:
        course = course_for("reverse_park", "a")
        course["cones"] = [{"id": "cone_in_the_way", "x": -7.0, "y": 9.0, "r": 0.25}]
        replay = Replay(course)
        replay.apply([{"t": 0, "c": "t", "v": 1}], 600)
        self.assertEqual([(e["k"], e["ref"], e["p"]) for e in replay.events if e["k"] == "cone"], [("cone", "cone_in_the_way", 10)])
        self.assertEqual(replay.status, "failed")
        self.assertEqual(replay.fail, "out_of_bounds", "一直往前开，最后开出训练场")
        self.assertEqual(replay.car.v, 0.0, "失败时自动制动")

    def test_timeout_fails_at_the_limit(self) -> None:
        course = course_for("reverse_park", "a")
        course["time_limit_ticks"] = 120
        replay = Replay(course)
        replay.apply([], 500)
        self.assertEqual((replay.status, replay.fail, replay.tick), ("failed", "timeout", 120))

    def test_gear_change_only_when_stopped(self) -> None:
        replay = Replay(course_for("reverse_park", "a"))
        replay.apply([{"t": 0, "c": "t", "v": 1}, {"t": 10, "c": "g", "v": -1}], 20)
        self.assertEqual(replay.car.gear, 1, "还在动，换挡无效")
        replay.apply([{"t": 20, "c": "t", "v": 0}, {"t": 20, "c": "b", "v": 1}, {"t": 60, "c": "g", "v": -1}], 61)
        self.assertEqual((replay.car.v, replay.car.gear), (0.0, -1), "停稳后换成倒挡")

    def test_chunked_replay_with_snapshots_equals_one_pass(self) -> None:
        course = course_for("side_park", "b")
        driver = Driver(course).run(side_park_bot(3.8, 0.8, -1))
        whole = Replay(course)
        whole.apply(driver.events, driver.tick)
        snapshot = Replay(course).snapshot()
        for start in range(0, driver.tick, 37):
            upto = min(driver.tick, start + 37)
            part = Replay(course, snapshot)
            part.apply([e for e in driver.events if start <= e["t"] < upto], upto)
            snapshot = part.snapshot()
        self.assertEqual(snapshot, whole.snapshot(), "分段复算（从快照接着算）与一次算完逐位一致")


class TownRouteTests(unittest.TestCase):
    def run_route(self, variant: str = "a", **kwargs) -> Driver:
        return Driver(course_for("route", variant)).run(route_bot(**kwargs))

    def test_careful_driver_completes_both_variants_without_deductions(self) -> None:
        for variant in ("a", "b"):
            with self.subTest(variant=variant):
                driver = self.run_route(variant)
                self.assertEqual((driver.replay.status, penalties(driver)), ("done", []))
                self.assertIn("invite_shown", kinds(driver), "路上收到了视频邀请，选择了稍后再看")

    def test_checks_signals_and_invite_are_scored(self) -> None:
        self.assertEqual(penalties(self.run_route(checks=False)), [("precheck_skipped", 10)])
        self.assertEqual(penalties(self.run_route(signals=False)), [("start_no_signal", 5), ("turn_no_signal", 10)])
        self.assertEqual(penalties(self.run_route(invite_open=True)), [("invite_opened", 10)])

    def test_running_the_red_light_is_a_red_line(self) -> None:
        driver = self.run_route(obey=False)
        self.assertEqual((driver.replay.status, driver.replay.fail), ("failed", "red_light"))
        self.assertEqual(driver.replay.events[-1]["f"], 1)

    def test_entering_an_occupied_crosswalk_is_a_red_line_and_rolling_a_stop_costs_points(self) -> None:
        course = course_for("route", "a")
        replay = Replay(course)
        replay.apply([{"t": 0, "c": "c", "v": 1}, {"t": 0, "c": "c", "v": 2}, {"t": 0, "c": "c", "v": 3}, {"t": 0, "c": "k", "v": -1}, {"t": 1, "c": "t", "v": 1}],
                     course["time_limit_ticks"])
        self.assertEqual(replay.fail, "crosswalk", "一路不减速：冲进了居民正在通过的人行横道")
        self.assertIn(("stop_rolled", 10), [(e["k"], e["p"]) for e in replay.events])
        self.assertIn(("speeding", 5), [(e["k"], e["p"]) for e in replay.events])


class InputValidationTests(unittest.TestCase):
    def test_rejects_out_of_range_unsorted_or_out_of_window_events(self) -> None:
        bad = [
            ([{"t": 5, "c": "s", "v": 13}], 0, 30),
            ([{"t": 5, "c": "t", "v": 2}], 0, 30),
            ([{"t": 5, "c": "x", "v": 1}], 0, 30),
            ([{"t": 9, "c": "t", "v": 1}, {"t": 5, "c": "b", "v": 1}], 0, 30),
            ([{"t": 30, "c": "t", "v": 1}], 0, 30),
            ([{"t": 3, "c": "t", "v": True}], 0, 30),
            ([], 0, 901),
            ([{"t": 1, "c": "g", "v": 0}], 0, 30),
        ]
        for events, start, upto in bad:
            with self.subTest(events=events, upto=upto), self.assertRaises(InputError):
                validate(events, start, upto, 12)
        self.assertEqual(validate([{"t": 0, "c": "s", "v": -12}, {"t": 0, "c": "g", "v": -1}], 0, 30, 12)[1], {"t": 0, "c": "g", "v": -1})


if __name__ == "__main__":
    unittest.main()
