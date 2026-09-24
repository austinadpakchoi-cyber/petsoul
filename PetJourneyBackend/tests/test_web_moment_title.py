"""TA 此刻在做什么：把行程标题接到方位词后面时的说法（`web_agent/moment.py` 的 `:79` 与 `:91`）。

和 `test_web_trip_title.py` 同一个缺陷的第二个落点。目录里的标题本身带方位词：

    在花店帮忙   → 「在家收拾东西，14:20 出门去**在**花店帮忙」（:79）
                 → 「在去**在**花店帮忙的路上」（:91）
    去附近喝一杯 → 「出门去**去**附近喝一杯」「在去**去**附近喝一杯的路上」

**`:98` 有意不改，这里专门钉住它**：那一句拼的是 `leg.destination["name"]`——**地点名不是行程标题**。
真实地点里就有以方位词开头的（「在水一方咖啡」），在那里削前缀会**改掉一个真实地名**。
所以「走路去在水一方咖啡」是对的，不是缺陷；没有这条用例，下一个人照着 `:79`/`:91` 顺手就把它也"修"了。

`MomentBuilder` 是鸭子类型注入的，所以这一组**不开库、不联网**：喂一个只实现了用到的那几个方法的假 repo。
标题从**真实目录**取，不写死——以后新增带方位词的岗位/活动，这里自己会红。
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.schemas.web.pets import PetPresence
from app.web_agent.moment import MomentBuilder
from app.web_journey.local import JOBS, LOCAL
from app.web_journey.repository import LegRecord

NOW = datetime(2026, 9, 24, 6, 0, tzinfo=timezone.utc)
BAD = ("去去", "在在", "去在")
PLACE = {"node_id": "n", "name": "某处", "kind": "stop", "timezone": "Asia/Hong_Kong", "lat": 22.3, "lng": 114.2, "verified": False}


class FakeJourney:
    def __init__(self, title: str, departs_in_minutes: int = 0) -> None:
        self.title = title
        self.journey_id = "jn-fake"
        self.departed_at = NOW + timedelta(minutes=departs_in_minutes)


class FakeRepo:
    def __init__(self, journey, legs=()) -> None:
        self._journey, self._legs = journey, list(legs)

    def active_for_pet(self, pet_id): return self._journey
    def legs(self, journey_id): return self._legs
    def visit_for_journey(self, journey_id): return None


def builder(journey, legs=(), presence=PetPresence.at_home) -> MomentBuilder:
    journeys = type("J", (), {"repo": FakeRepo(journey, legs)})()
    return MomentBuilder(journeys, presence_of=lambda pet_id: presence)


def leg(mode: str, name: str) -> LegRecord:
    place = {**PLACE, "name": name}
    return LegRecord(leg_id="l1", journey_id="jn-fake", sequence=1, direction="outbound", kind="main", mode=mode, role="passenger",
                     world_service_id=None, origin=dict(PLACE), destination=place,
                     starts_at=NOW - timedelta(minutes=5), ends_at=NOW + timedelta(minutes=30),
                     time_basis="scheduled", freshness="live", position_basis="interpolated")


def catalog_titles() -> list[str]:
    return [k.title for k in LOCAL.values()] + [j.label for j in JOBS.values()]


class MomentTitleTests(unittest.TestCase):
    def test_no_catalog_title_doubles_a_word_while_getting_ready(self) -> None:
        """:79 出门前在家收拾：目录里每一条标题都不该拼出重复的方位词。"""
        self.assertTrue(catalog_titles(), "前提不成立：目录是空的，下面全是空转")
        for title in catalog_titles():
            with self.subTest(title=title):
                moment = builder(FakeJourney(title, departs_in_minutes=20)).build("pet-1", NOW)
                self.assertIn("出门去", moment.doing, "前提不成立：没走到 :79 那一支")
                for bad in BAD:
                    self.assertNotIn(bad, moment.doing, f"「{title}」拼成了「{moment.doing}」")

    def test_no_catalog_title_doubles_a_word_on_the_way(self) -> None:
        """:91 已经出门、还没上某一段交通：同样不该重复。"""
        for title in catalog_titles():
            with self.subTest(title=title):
                moment = builder(FakeJourney(title), presence=PetPresence.in_transit).build("pet-1", NOW)
                self.assertIn("的路上", moment.doing, "前提不成立：没走到 :91 那一支")
                for bad in BAD:
                    self.assertNotIn(bad, moment.doing, f"「{title}」拼成了「{moment.doing}」")

    def test_a_title_without_a_leading_word_is_untouched(self) -> None:
        """正向对照：不带方位词的标题一个字都不该被动。

        只验"去掉了什么"的话，一个把首字一律砍掉的实现也会通过上面两条。
        """
        for title in ("进城逛逛", "澳门一日游"):
            with self.subTest(title=title):
                self.assertIn(f"出门去{title}", builder(FakeJourney(title, 20)).build("p", NOW).doing)
                self.assertIn(f"在去{title}的路上", builder(FakeJourney(title), presence=PetPresence.in_transit).build("p", NOW).doing)

    def test_a_real_place_name_starting_with_a_word_is_kept(self) -> None:
        """:98 **有意不改**，这条钉住它：那里拼的是地点名，不是行程标题。

        真实地名就有以方位词开头的。在 `:98` 削前缀 ＝ 把「在水一方咖啡」改成「水一方咖啡」，
        **改掉一个真实存在的地名**。所以「走路去在水一方咖啡」是对的。
        """
        moment = builder(FakeJourney("在花店帮忙"), legs=[leg("walk", "在水一方咖啡")],
                         presence=PetPresence.in_transit).build("pet-1", NOW)

        self.assertEqual(moment.doing, "走路去在水一方咖啡", "地点名要原样保留，一个字都不许削")


if __name__ == "__main__":
    unittest.main()
