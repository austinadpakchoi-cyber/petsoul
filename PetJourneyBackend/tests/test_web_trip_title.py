"""把行程标题接到「去」后面时的说法：`trip_titles.going_to`。

`brief()` 拼的是「TA 在去{标题}的路上」，而目录里的标题**本身就带方位词**：

    在家附近走走 / 在咖啡馆帮工 …  → 「TA 在去**在**家附近走走的路上」
    去附近喝一杯 / 去渔港帮忙收网 … → 「TA 在去**去**附近喝一杯的路上」

第二种是 6c2b 报缺陷时没提到的那一半，而 `local:cafe`（去附近喝一杯）恰恰是最常走的近处目的地。
`local.py:157,163` 早就在用 `.removeprefix('在').removeprefix('去')` 造地点名，这里沿用同一条口径。

**用例从真实目录取标题，不写死**：以后有人加一个带方位词的新岗位／新活动，这里会**自己**红，
不需要谁记得回来补。写死列表的话，新增那条永远不会被看见。
"""

from __future__ import annotations

import unittest

from app.web_journey.local import JOBS, LOCAL
from app.web_journey.trip_titles import going_to

SENTENCE = "TA 在去{}的路上"
BAD = ("去去", "在在", "去在")  # 拼出来会重复的三种


def catalog_titles() -> list[str]:
    return [k.title for k in LOCAL.values()] + [j.label for j in JOBS.values()]


class TripTitleTests(unittest.TestCase):
    def test_no_catalog_title_produces_a_doubled_word(self) -> None:
        """对**目录里每一条**标题拼一遍，都不该出现重复的方位词。"""
        self.assertTrue(catalog_titles(), "前提不成立：目录是空的，下面全是空转")
        for title in catalog_titles():
            with self.subTest(title=title):
                sentence = SENTENCE.format(going_to(title))
                for bad in BAD:
                    self.assertNotIn(bad, sentence, f"「{title}」拼出来成了「{sentence}」")

    def test_the_two_shapes_that_actually_occur(self) -> None:
        """两种真实形状各钉一条，出错时一眼看得出是哪一种。"""
        self.assertEqual(going_to("在咖啡馆帮工"), "咖啡馆帮工")
        self.assertEqual(going_to("去附近喝一杯"), "附近喝一杯")

    def test_titles_without_a_leading_word_are_untouched(self) -> None:
        """正向对照：不带方位词的标题一个字都不该被动。

        只验"去掉了什么"的话，一个把首字一律砍掉的实现也会通过上面两条。
        """
        for title in ("进城逛逛", "自己开车去兜风", "跟着护林员巡山", "帮骆驼队牵绳", "澳门一日游"):
            with self.subTest(title=title):
                self.assertEqual(going_to(title), title)

    def test_it_does_not_eat_a_word_that_merely_contains_them(self) -> None:
        """只削**开头**：标题中间的「去」「在」不动（`removeprefix` 的语义，这里把它钉住）。"""
        self.assertEqual(going_to("自己开车去兜风"), "自己开车去兜风")
        self.assertEqual(going_to("住在海边的朋友家"), "住在海边的朋友家")


if __name__ == "__main__":
    unittest.main()
