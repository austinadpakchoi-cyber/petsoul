"""照片导演：场景、地点、当地时间、已核验天气与叙事模式。全程禁网。

断言的是**行为差异**（换时间会换什么光、室内外怎么分层），
不是"提示词里包含几个关键词"。
"""
from __future__ import annotations

import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "photo_director"))

import builders  # noqa: E402
from harness import ALL_SCENE_KEYS, OfflineCase  # noqa: E402

from app.web_photo_director import PhotoDirectorError  # noqa: E402
from app.web_photo_director.recipes import RECIPES, SCENES  # noqa: E402


class AllScenesTests(OfflineCase):
    def test_every_fixture_scene_can_be_directed(self):
        for key in ALL_SCENE_KEYS:
            with self.subTest(scene=key):
                photo = self.direct(key)
                self.assertTrue(photo.prompt)
                self.assertEqual(RECIPES[photo.draft.recipe].scene, key)

    def test_scenes_do_not_all_look_the_same(self):
        """11 个场景不能编译成同一张：构图必须有足够多的不同。"""
        compositions = {key: self.direct(key).draft.composition for key in ALL_SCENE_KEYS}
        self.assertGreaterEqual(len(set(compositions.values())), 9, compositions)

    def test_place_and_city_come_from_the_event(self):
        photo = self.direct("train")
        self.assertIn("京都", photo.prompt)
        self.assertIn("开往北边的城际列车", photo.prompt)
        self.assertIn("place_anchored", photo.prompt_checks)

    def test_local_time_of_day_drives_the_light(self):
        """22:10 的家应该是夜景闪光，不是白天自然光；时间来自事件，不是生成时刻。"""
        self.assertIn("夜晚", self.direct("home").prompt)
        morning = self.direct("cafe")
        self.assertIn("上午", morning.prompt)
        self.assertNotIn("夜晚", morning.prompt)

    def test_same_scene_at_a_different_hour_changes_the_light(self):
        scene = builders.build_scene("cafe", "fx-pet-amber")
        late = builders.build_scene(
            "cafe", "fx-pet-amber", captured_at=scene.captured_at + timedelta(hours=13)
        )
        early_photo, late_photo = self.direct("cafe"), self.direct("cafe", scene=late)
        self.assertNotEqual(early_photo.prompt, late_photo.prompt)
        self.assertIn("上午", early_photo.prompt)
        self.assertIn("夜晚", late_photo.prompt)  # 09:20 + 13h = 22:20


class WeatherLayeringTests(OfflineCase):
    def test_indoor_scene_keeps_the_rain_outside_the_window(self):
        scene = builders.build_scene(
            "cafe", "fx-pet-amber", facts=["at_cafe", "coffee_cup", "weather_rainy"]
        )
        photo = self.direct("cafe", scene=scene)
        self.assertIn("窗外在下雨", photo.prompt)
        self.assertIn("保持干燥", photo.prompt)
        self.assertIn("indoor_weather_layered", photo.prompt_checks)
        self.assertNotIn("表面湿亮反光", photo.prompt)

    def test_outdoor_scene_lets_the_weather_reach_the_ground(self):
        photo = self.direct("snow_field")
        self.assertIn("地面积雪反光", photo.prompt)
        # 注意：DNA 里有"喜欢往窗外看"，所以不能直接断言没有"窗外"两个字；
        # 要断言的是没有用上室内那一套措辞。
        self.assertNotIn("窗外在下雪", photo.prompt)
        self.assertNotIn("保持干燥", photo.prompt)
        self.assertNotIn("indoor_weather_layered", photo.prompt_checks)

    def test_sealed_cabin_never_renders_ground_weather(self):
        """地面观测到的天气不等于巡航舱外天气，一次都不渲染。"""
        photo = self.direct("flight_adventure")
        self.assertNotIn("晴天", photo.prompt)
        self.assertNotIn("verified_weather_applied", photo.prompt_checks)
        self.assertIn("indoor_weather_layered", photo.prompt_checks)

    def test_night_never_gets_direct_sunlight(self):
        """23:15 的营地即使核验到"晴"，也只能是晴朗夜空，不能是阳光直射。"""
        photo = self.direct("aurora_camp")
        self.assertIn("夜空晴朗", photo.prompt)
        self.assertNotIn("阳光直接", photo.prompt)

    def test_unverified_weather_never_appears(self):
        scene = builders.build_scene("home", "fx-pet-amber", facts=["at_home", "home_blanket"])
        photo = self.direct("home", scene=scene)
        for token in ("下雨", "晴天", "多云", "下雪"):
            self.assertNotIn(token, photo.prompt)
        self.assertNotIn("verified_weather_applied", photo.prompt_checks)


class StoryModeTests(OfflineCase):
    def test_fiction_is_declared_and_daily_life_is_not(self):
        self.assertIn("虚构冒险剧情", self.direct("flight_adventure").prompt)
        self.assertIn("影视创作画面", self.direct("ship_deck").prompt)
        self.assertNotIn("虚构", self.direct("cafe").prompt)

    def test_a_cafe_cannot_be_relabelled_as_an_adventure(self):
        scene = builders.build_scene("cafe", "fx-pet-amber", narrative="fictional_adventure")
        with self.assertRaises(PhotoDirectorError) as caught:
            self.direct("cafe", scene=scene)
        self.assertEqual(str(caught.exception), "story_mode_not_for_scene")

    def test_a_cockpit_cannot_be_relabelled_as_daily_life(self):
        scene = builders.build_scene("flight_adventure", "fx-pet-amber", narrative="daily_life")
        with self.assertRaises(PhotoDirectorError) as caught:
            self.direct("flight_adventure", scene=scene)
        self.assertEqual(str(caught.exception), "story_mode_not_for_scene")

    def test_story_mode_is_carried_on_the_result(self):
        self.assertEqual(self.direct("ship_deck").story_mode, "film_scene")
        self.assertEqual(self.direct("cafe").story_mode, "daily_life")


class ShotStabilityTests(OfflineCase):
    def test_background_is_required_to_stay_legible(self):
        """与旧模板最大的差别：不能每张都是背景全虚化的证件照。"""
        for key in ALL_SCENE_KEYS:
            with self.subTest(scene=key):
                photo = self.direct(key)
                self.assertIn("background_legible", photo.prompt_checks)
                self.assertNotIn("背景虚化", photo.prompt)

    def test_directing_twice_is_stable(self):
        first, second = self.direct("cafe"), self.direct("cafe")
        self.assertEqual(first.prompt, second.prompt)
        self.assertEqual(first.context_key, second.context_key)

    def test_review_points_travel_with_the_photo(self):
        """人审要点要跟着照片走，但它是给人看的清单，不是程序结论。"""
        photo = self.direct("cafe")
        self.assertEqual(photo.review_points, RECIPES[photo.draft.recipe].acceptance)
        self.assertTrue(photo.review_points)

    def test_no_readable_text_or_interface_chrome_is_requested(self):
        photo = self.direct("cafe")
        for banned in ("文字", "商标", "可读的招牌", "截图黑边", "页码角标"):
            self.assertIn(banned, photo.negative_prompt)

    def test_every_scene_declares_a_space(self):
        for key, spec in SCENES.items():
            with self.subTest(scene=key):
                self.assertIn(spec.space, {"indoor", "outdoor", "sealed"})


if __name__ == "__main__":
    unittest.main()
