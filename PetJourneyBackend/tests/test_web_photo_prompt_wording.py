"""写实照片提示词的措辞（P 在真图上吃过亏的两条；A 的 photo_prompts.py）。纯函数，不联网、0 次付费调用。

钉的是：
  - 名字不进提示词（自拍、证件照）：名字最容易被画成招牌上的字；证件照是以后每一张的身份参考，名字被画成字会一路传下去；
  - 自拍**只读 scene**：place、city 是给界面和导演的真名（B 全仓核过读者），传进来也进不了提示词；
  - 自拍里招牌与文字用正面写法，诱发词（招牌、商标、品牌、可读的文字）不出现；
  - 证件照不再用「没有文字」那句否定写法。
**这些措辞未经出图验证**（P：正面写法是押注）——这里钉的是「按约定写了」，不是「画出来就对」。
"""

from __future__ import annotations

import unittest

from app.web_journey.photo_prompts import build_portrait_prompt, build_prompt, build_selfie_prompt

NAME = "年糕"
PLACE, CITY = "维多利亚公园旁的邮局", "香港"  # 真名：给界面和导演的，不该进提示词
SCENE = "在高楼林立、街道干净的城市街区的新家附近，对着镜头眨眼睛"
INDUCING = ("招牌", "商标", "品牌", "可读的文字")
SIGNS = "牌子和显示屏保持空白，或被前景挡住，画面里物件的表面都是素面的"


class SelfiePromptWordingTests(unittest.TestCase):
    def prompt(self, **overrides) -> str:
        kwargs = {"species": "cat", "name": NAME, "place": PLACE, "city": CITY, "scene": SCENE, "with_reference": True}
        kwargs.update(overrides)
        return build_selfie_prompt(**kwargs)

    def test_only_the_scene_description_goes_in(self) -> None:
        text = self.prompt()
        self.assertIn(f"一只真实的猫，{SCENE}。", text)
        self.assertIn("必须是参考图里的同一只猫", text)
        for proper in (NAME, PLACE, CITY):
            self.assertNotIn(proper, text, "名字、地名都不进提示词")

    def test_signs_are_asked_for_in_the_positive_and_the_inducing_words_are_gone(self) -> None:
        for with_reference in (True, False):
            with self.subTest(with_reference=with_reference):
                text = self.prompt(with_reference=with_reference)
                self.assertIn(SIGNS, text)
                for word in INDUCING:
                    self.assertNotIn(word, text)


class AdventurePromptWordingTests(unittest.TestCase):
    """英文冒险插画：名字不进（故事由调用方用「这只{种类}」渲染，见 illustrations._render），招牌与文字用正面写法。"""

    def test_the_name_stays_out_and_signs_are_asked_for_in_the_positive(self) -> None:
        for with_reference in (True, False):
            with self.subTest(with_reference=with_reference):
                text = build_prompt(species="cat", name=NAME, personality="安静", title="咖啡馆小侦探",
                                    story="这只猫顺着桌脚的奶泡印一路找。", with_reference=with_reference)
                self.assertNotIn(NAME, text)
                self.assertIn("Main subject: a cat, a real animal", text)
                self.assertIn("Any signs or screens are blank or hidden behind foreground objects; object surfaces are plain.", text)
                for word in ("No text", "no letters", "readable signs", "logos", "brands"):
                    self.assertNotIn(word, text)


class PortraitPromptWordingTests(unittest.TestCase):
    def test_the_identity_reference_carries_no_name_and_no_text_wording(self) -> None:
        for personality in ("安静", None):
            with self.subTest(personality=personality):
                text = build_portrait_prompt(species="cat", name=NAME, personality=personality)
                self.assertNotIn(NAME, text)
                self.assertNotIn("文字", text)
                self.assertIn("正面半身像", text)


if __name__ == "__main__":
    unittest.main()
