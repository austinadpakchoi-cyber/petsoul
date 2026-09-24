"""有效期边界：一律左闭右开 `[valid_from, valid_until)`（合同 §29.3，I 裁定；仓里先例是 `leg_in_progress` 的 `starts_at <= now < ends_at`）。
不联网、0 次付费调用。

钉三处边界，每处正反两边都钉（只钉一边的话，比较号朝哪边其实没被验过）：
  - 研究结果核对（`facts.review`）：有效期截止在此刻的事实算 expired，晚一微秒的算有效；
  - 覆盖出行时刻：出行时刻只是一个点（只给起点）时，截止在那一刻不算覆盖，晚一微秒算覆盖；
  - 出发时逐条复核（`stale_facts_in`）：到期那一刻已经过期，早一微秒还有效。
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import timedelta

from travel_wish_fakes import TravelResearchTestBase, good_result

from app.utils import iso, utcnow
from app.web_platform.uow import unit_of_work
from app.web_travel import facts
from app.web_travel.ports import ResearchFact

TICK = timedelta(microseconds=1)
PRIMARY = ("hk-repulse-bay", "浅水湾")


def weather(valid_from, valid_until) -> ResearchFact:
    return ResearchFact("weather", "weather", "浅水湾", {"suitable": True, "summary": "多云"}, ("s-weather",),
                        valid_from=iso(valid_from), valid_until=iso(valid_until), verification="weather_api")


def judged(fact: ResearchFact, now, window=(None, None)) -> tuple[str, str | None]:
    verdict = facts.review(replace(good_result(), facts=(fact,)), now=now, primary=PRIMARY, window=window).verdicts[fact.key]
    return verdict.verdict, verdict.reason


class ReviewBoundaryTests(unittest.TestCase):
    def test_a_fact_ending_exactly_now_has_expired(self) -> None:
        now = utcnow()
        self.assertEqual(judged(weather(now - timedelta(hours=1), now), now), ("stale", "expired"))
        self.assertEqual(judged(weather(now - timedelta(hours=1), now + TICK), now), ("verified", None), "对照：晚一微秒仍有效")

    def test_a_point_in_time_trip_is_not_covered_by_a_window_ending_at_it(self) -> None:
        now = utcnow()
        start = now + timedelta(days=1)
        window = (iso(start), None)  # 只给了起点：出行时刻是一个点
        self.assertEqual(judged(weather(now, start), now, window), ("stale", "not_covering_window"))
        self.assertEqual(judged(weather(now, start + TICK), now, window), ("verified", None), "对照：晚一微秒就覆盖")


class DepartureBoundaryTests(TravelResearchTestBase):
    def test_a_precondition_expires_at_the_instant_it_ends(self) -> None:
        now = utcnow()
        until = now + timedelta(hours=2)
        windowed = tuple(replace(f, observed_at=None, valid_from=iso(now - timedelta(hours=1)), valid_until=iso(until))
                         if f.key == "weather" else f for f in good_result().facts)
        self.port.result = replace(good_result(), facts=windowed)
        self.propose()
        self.research.run_pending()
        with self.storage.connect() as conn:
            plan = self.wishes.ready_plan_in(conn, "pet-1")
        self.assertEqual(len(plan.preconditions), 1, "前提：带有效期的天气成了出发前置条件")

        with unit_of_work(self.storage) as conn:
            self.assertEqual(self.wishes.stale_facts_in(conn, plan.preconditions, until), plan.preconditions, "到期那一刻已经过期")
            self.assertEqual(self.wishes.stale_facts_in(conn, plan.preconditions, until - TICK), (), "对照：早一微秒仍有效")


if __name__ == "__main__":
    unittest.main()
