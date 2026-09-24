"""场景键与已核验事实的映射（照片导演正式接线的第一块，CR-P-to-B）。

这两件事必须分开判。混在一起的后果是：地点类目没拿到，就被当成"这事不归导演管"而回落旧模板——
那等于把"缺事实"偷偷降级成"非目标"，主人看到的是一张按旧模板画的照片，而不是"这次先不画"。
口径（COORD-B-INTERFACE）：**目标场景被 readiness 拒绝必须 hold**，只有本来不在目标集合的才走旧路。

纯函数，不建库、不联网、不产生付费调用。
"""

from __future__ import annotations

import unittest

from app.web_agent.photo_scene import (canonical_category, missing_fact_reason, place_timezone,
                                        scene_key_of, verified_facts)


def place(**fields) -> dict:
    """一条到访地点记录，字段名与 web_journey/planning.py::visit_place 的产出一致。"""
    return {"provider": "world", "name": "示例·海边咖啡馆", "category": "咖啡馆", "timezone": "Asia/Hong_Kong", **fields}


class SceneKeyTests(unittest.TestCase):
    def test_a_cafe_outing_is_a_target_scene(self) -> None:
        for key in ("local:cafe", "harbour_cafe"):
            with self.subTest(destination=key):
                self.assertEqual(scene_key_of(key), "cafe")

    def test_a_trip_that_ends_at_a_cafe_is_also_a_cafe_photo(self) -> None:
        """按**拍照当刻的实际到访地**判，不按整趟的交通方式（COORD-B-SCENE）：
        坐船去澳门、在街角咖啡馆坐下来拍的那张，就是一张咖啡馆照片。
        不能因为 destination 写着轮渡 / 飞行就说这事不归导演管。"""
        for key in ("macau_ferry", "tokyo_flight"):
            with self.subTest(destination=key):
                self.assertEqual(scene_key_of(key), "cafe")

    def test_other_outings_are_not_the_directors_business(self) -> None:
        """散步、进城、兜风这些没有对应场景键：不传，照旧走模板，这是**正常**的旧路。"""
        for key in ("local:stroll", "local:city_trip", "local:drive_trip", "work:cafe_helper"):
            with self.subTest(destination=key):
                self.assertIsNone(scene_key_of(key))

    def test_a_missing_destination_is_not_a_target(self) -> None:
        self.assertIsNone(scene_key_of(None))
        self.assertIsNone(scene_key_of(""))


class VerifiedFactsTests(unittest.TestCase):
    def test_a_verified_cafe_category_asserts_at_cafe(self) -> None:
        self.assertEqual(verified_facts("cafe", place()), ("at_cafe",))
        self.assertEqual(verified_facts("cafe", place(category="cafe")), ("at_cafe",))

    def test_recognised_categories_survive_limited_normalisation(self) -> None:
        """只做大小写、首尾空白与全角空格的归一化，**不做模糊匹配**。
        高德适配器把 `poi["type"]` 按 `;` 取末段，实际会出现"咖啡厅"。"""
        for category in ("咖啡厅", "CAFE", " cafe ", "　咖啡馆　"):
            with self.subTest(category=category):
                self.assertEqual(verified_facts("cafe", place(category=category)), ("at_cafe",))
                self.assertIsNone(missing_fact_reason("cafe", place(category=category)))

    def test_normalisation_does_not_become_fuzzy_matching(self) -> None:
        """“咖啡馆旁边的面包店”不是咖啡馆。放宽成包含匹配就会把一次普通到访说成“它在咖啡馆里”。"""
        for category in ("咖啡馆旁边的面包店", "cafeteria", "coffee"):
            with self.subTest(category=category):
                self.assertIsNone(canonical_category(category))
                self.assertEqual(verified_facts("cafe", place(category=category)), ())

    def test_a_hold_says_why(self) -> None:
        """目标场景缺事实要 hold，而 hold 在日志里长得和"没到时间"一样——原因要能一眼看出来。"""
        self.assertEqual(missing_fact_reason("cafe", None), "place_missing")
        self.assertEqual(missing_fact_reason("cafe", place(category=None)), "category_missing")
        self.assertEqual(missing_fact_reason("cafe", place(category="   ")), "category_missing")
        self.assertEqual(missing_fact_reason("cafe", place(category="餐厅")), "category_not_recognised:餐厅")
        self.assertIsNone(missing_fact_reason(None, place(category="餐厅")), "非目标场景没有“缺事实”一说")

    def test_an_unrecognised_category_asserts_nothing(self) -> None:
        """供应商给的类目认不出就不断言——宁可 hold，也不要把一次普通到访说成"它在咖啡馆里"。
        **注意**：这只是不给事实，场景仍然是目标场景，由 readiness 判 hold，不会回落旧模板。"""
        for category in ("餐厅", "restaurant", "商场", "", "   ", None):
            with self.subTest(category=category):
                self.assertEqual(verified_facts("cafe", place(category=category)), ())

    def test_a_place_without_a_category_asserts_nothing(self) -> None:
        missing = {key: value for key, value in place().items() if key != "category"}

        self.assertEqual(verified_facts("cafe", missing), ())

    def test_facts_are_only_given_for_the_scene_they_belong_to(self) -> None:
        self.assertEqual(verified_facts(None, place()), (), "非目标场景不该带出任何事实")
        self.assertEqual(verified_facts("train", place()), (), "咖啡馆类目不能拿去给列车场景当事实")

    def test_nothing_is_invented_when_there_is_no_place(self) -> None:
        self.assertEqual(verified_facts("cafe", None), ())


class PlaceTimezoneTests(unittest.TestCase):
    def test_the_timezone_comes_from_the_place_itself(self) -> None:
        self.assertEqual(place_timezone(place(timezone="Asia/Tokyo")), "Asia/Tokyo")

    def test_a_missing_timezone_is_reported_as_missing_not_defaulted(self) -> None:
        """取不到就是取不到。**不回落任何默认城市**——按宿主机或家的时区换算，
        会让夜里拍的照片变成白天，这一条真图上已经验证过差别。"""
        for zone in (None, "", "   "):
            with self.subTest(timezone=zone):
                self.assertIsNone(place_timezone(place(timezone=zone)))
        self.assertIsNone(place_timezone(None))


if __name__ == "__main__":
    unittest.main()
