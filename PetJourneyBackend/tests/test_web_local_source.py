"""附近出门的地点类目要按**这次出门是什么种类**给，不按"家的栖息地"（COORD-I-LOCAL-SOURCE）。

拿不到真实地点、也不是演示环境时走 `world_rule`：名字是"星球居民开的小咖啡馆"、模板是 cafe、键是 `local:cafe`，
唯独**类目**被写成了家的栖息地词（城市栖息地 → "附近的公园"）。照片导演的封闭词表认不出，
`local:cafe` 的照片就一直 hold，原因是 `category_not_recognised:附近的公园`。

这要在源头修：cafe 明确给"咖啡馆"，散步仍按栖息地给（海边／公园／林子里……本来就对）。
**真实供应商没给类目时照旧留空，不伪造**——留空由导演那边 hold，是正确的保守行为。

纯单元测试：不建库、不联网、不调用供应商。
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.web_home.place import HomePlace
from app.web_journey.local import local_plan


def home(habitat: str = "city") -> HomePlace:
    return HomePlace(habitat=habitat, habitat_label="城市", area_key="demo", area_label="示例区",
                     city="香港", lat=22.2809, lng=114.1600, timezone="Asia/Hong_Kong", chosen=True)


class FakeGeo:
    """按需给出一个真实地点；`category` 由用例指定，可以是 None（供应商没给）。"""

    def __init__(self, category: str | None) -> None:
        self.category = category

    def configured(self, region: str) -> bool:
        return True

    def place_near(self, region, lat, lng, *, keyword, google_type, radius):
        return SimpleNamespace(place_id="amap:B0FF", name="真·某某咖啡", lat=lat + 0.001, lng=lng + 0.001,
                               category=self.category, address="某某路 1 号", attribution="高德")


class WorldPlaceCategoryTests(unittest.TestCase):
    def venue(self, key: str, *, habitat: str = "city", geo=None, demo: bool = False):
        plan = local_plan(key, home(habitat), geo=geo, demo=demo)
        self.assertIsNotNone(plan)
        return plan

    def test_a_world_cafe_is_categorised_as_a_cafe_not_as_the_habitat_spot(self) -> None:
        plan = self.venue("local:cafe")

        self.assertEqual(plan.basis, "world_rule", "前提：这一趟确实走的是星球内的地方")
        self.assertEqual(plan.destination.venue.name, "星球居民开的小咖啡馆")
        self.assertEqual(plan.destination.venue.category, "咖啡馆",
                         "名字是咖啡馆、模板是 cafe，类目不能变成家的栖息地词")

    def test_the_cafe_category_does_not_follow_the_habitat(self) -> None:
        for habitat in ("city", "seaside", "forest", "lakeside"):
            with self.subTest(habitat=habitat):
                self.assertEqual(self.venue("local:cafe", habitat=habitat).destination.venue.category, "咖啡馆")

    def test_a_stroll_still_takes_the_habitat_spot_word(self) -> None:
        """散步本来就是去家附近那类地方，按栖息地给是对的，别一起改掉。"""
        self.assertEqual(self.venue("local:stroll", habitat="city").destination.venue.category, "附近的公园")
        self.assertEqual(self.venue("local:stroll", habitat="seaside").destination.venue.category, "海边")

    def test_a_real_place_keeps_the_providers_own_category(self) -> None:
        plan = self.venue("local:cafe", geo=FakeGeo("咖啡厅"))

        self.assertEqual(plan.basis, "real")
        self.assertEqual(plan.destination.venue.category, "咖啡厅", "真实地点给了什么就是什么")

    def test_a_real_place_without_a_category_is_left_empty_not_invented(self) -> None:
        """供应商没给类目：留空，让导演那边 hold。伪造一个词会把"不知道"说成"知道"。"""
        plan = self.venue("local:cafe", geo=FakeGeo(None))

        self.assertEqual(plan.basis, "real")
        self.assertIsNone(plan.destination.venue.category, "不知道就留空，不拿栖息地词顶上")

    def test_working_a_shift_is_still_marked_as_work(self) -> None:
        plan = self.venue("work:fishing_port", habitat="seaside")

        self.assertEqual(plan.destination.venue.category, "打工")


if __name__ == "__main__":
    unittest.main()
