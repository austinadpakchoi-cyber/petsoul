"""照片导演：六种镜头模式互斥、各自的现场前提，以及主人明确点名时的处理。全程禁网。

旧链路的毛病是不管哪种情形都统一追加第一人称自拍，于是驾驶舱里的宠物
也被要求腾出一只前爪举相机。这里盯的就是那件事不会再发生。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "photo_director"))

from dataclasses import replace  # noqa: E402

import builders  # noqa: E402
from harness import ALL_SCENE_KEYS, OfflineCase  # noqa: E402

from app.web_photo_director import PhotoDirectorError  # noqa: E402
from app.web_photo_director.catalog import (  # noqa: E402
    CAMERA_CONFLICTING_HABITS,
    CAMERA_DEVICE,
    CAMERAS,
    HABIT_TEXT,
)
from app.web_photo_director.compiler import _dna_clauses  # noqa: E402
from app.web_photo_director.draft import eligible_recipes  # noqa: E402
from app.web_photo_director.recipes import RECIPES  # noqa: E402

SIX_MODES = frozenset({
    "front_selfie", "mirror_selfie", "friend_camera",
    "fixed_companion_camera", "fixed_cockpit", "detail_pov",
})


class CameraCoverageTests(OfflineCase):
    def test_catalog_offers_exactly_the_six_modes(self):
        self.assertEqual(set(CAMERAS), SIX_MODES)
        self.assertEqual(set(CAMERA_DEVICE), SIX_MODES)

    def test_every_mode_is_reachable_from_some_recipe(self):
        """词表里有一种镜头，却没有任何配方用得上，等于没实现。"""
        used = {recipe.camera for recipe in RECIPES.values()}
        self.assertEqual(used, SIX_MODES)

    def test_fixture_scenes_actually_exercise_most_modes(self):
        chosen = {self.direct(key).draft.camera for key in ALL_SCENE_KEYS}
        self.assertGreaterEqual(len(chosen), 4, chosen)

    def test_each_mode_states_where_the_device_is(self):
        for key in ALL_SCENE_KEYS:
            with self.subTest(scene=key):
                photo = self.direct(key)
                self.assertIn(CAMERA_DEVICE[photo.draft.camera], photo.prompt)
                self.assertIn("camera_mode_exclusive", photo.prompt_checks)

    def test_modes_do_not_bleed_into_each_other(self):
        """固定机位的照片里不能出现"举着拍"，同伴拍的不能出现手机。"""
        cockpit = self.direct("flight_adventure")
        self.assertEqual(cockpit.draft.camera, "fixed_cockpit")
        self.assertNotIn("它自己举着拍", cockpit.prompt)
        self.assertIn("画面里没有手机", cockpit.prompt)

        friend = self.direct("workshop")
        self.assertEqual(friend.draft.camera, "friend_camera")
        self.assertNotIn("它自己举着拍", friend.prompt)
        self.assertIn("画面里没有拍摄者", friend.prompt)


class CameraPreconditionTests(OfflineCase):
    def test_friend_camera_needs_a_photographer_who_was_there(self):
        """没有同伴在场就不能说"同伴拍的"——不能虚构一个摄影者。"""
        scene = builders.build_scene(
            "workshop", "fx-pet-amber",
            facts=["at_workshop", "parked_vehicle", "hand_tool", "work_outfit"],
        )
        context = builders.build_context("workshop", scene=scene)
        self.assertEqual(eligible_recipes(context), ())
        with self.assertRaises(PhotoDirectorError) as caught:
            self.director.direct(context, builders.build_access(context))
        self.assertEqual(str(caught.exception), "no_recipe_for_verified_facts")

    def test_mirror_selfie_needs_a_mirror_and_its_own_device(self):
        scene = builders.build_scene("gym", "fx-pet-amber", facts=["at_gym", "own_device"])
        context = builders.build_context("gym", scene=scene)
        self.assertEqual(eligible_recipes(context), ())

        scene = builders.build_scene("gym", "fx-pet-amber", facts=["at_gym", "gym_mirror"])
        context = builders.build_context("gym", scene=scene)
        self.assertEqual(eligible_recipes(context), ())

    def test_photographer_is_a_precondition_not_picture_content(self):
        """同伴在场是条件；画面里恰恰不该出现拍摄者。"""
        photo = self.direct("workshop")
        self.assertNotIn("photographer_present", photo.draft.visible_facts)
        self.assertNotIn("确实有一位同伴在场", photo.prompt)


class RequestedCameraTests(OfflineCase):
    def test_requested_mode_is_honoured_where_it_is_possible(self):
        photo = self.direct("home", requested_camera="fixed_companion_camera")
        self.assertEqual(photo.draft.camera, "fixed_companion_camera")

    def test_requested_selfie_is_refused_while_it_is_flying(self):
        """它在驾驶时腾不出前爪举相机——宁可拒绝，也不画一件做不到的事。"""
        context = builders.build_context("flight_adventure", requested_camera="front_selfie")
        self.assertEqual(eligible_recipes(context), ())
        with self.assertRaises(PhotoDirectorError) as caught:
            self.director.direct(context, builders.build_access(context))
        self.assertEqual(str(caught.exception), "no_recipe_for_verified_facts")

    def test_unknown_requested_camera_yields_nothing(self):
        context = builders.build_context("cafe", requested_camera="drone_orbit")
        self.assertEqual(eligible_recipes(context), ())


class DetailPovTests(OfflineCase):
    def _detail_photo(self):
        # 只留下让特写成为唯一可选的事实组合
        scene = builders.build_scene("cafe", "fx-pet-amber", facts=["at_cafe", "coffee_cup"])
        context = builders.build_context("cafe", scene=scene, requested_camera="detail_pov")
        return self.director.direct(context, builders.build_access(context))

    def test_detail_pov_is_selectable(self):
        photo = self._detail_photo()
        self.assertEqual(photo.draft.camera, "detail_pov")
        self.assertEqual(photo.draft.recipe, "cafe_detail_pov")

    def test_detail_pov_relaxes_the_face_claim(self):
        """脸可能不入镜，就不能硬说"脸型一致"，否则模型会把脸塞进特写。"""
        photo = self._detail_photo()
        self.assertIn("画面里出现的部分必须", photo.prompt)
        self.assertNotIn("脸型、口鼻长度", photo.prompt)
        self.assertIn("identity_locked", photo.prompt_checks)

    def test_full_frame_modes_keep_the_face_claim(self):
        photo = self.direct("cafe")
        self.assertIn("脸型、口鼻长度", photo.prompt)


if __name__ == "__main__":
    unittest.main()


class GazeDirectionTests(OfflineCase):
    """镜头把视线定在哪，配方与 DNA 就不能同时把它引开。

    `train_watch_selfie` 原本是 `front_selfie`（要求脸朝镜头）配「趴着从车窗往外看」
    （要求脸朝窗外），两者不可能同时成立；DNA 的「喜欢往窗外看」又在末尾再拉一次。
    模型当时选了镜头、丢了动作——**它选对了，是我们的要求自相矛盾**。

    这里盯的是那组矛盾不会再出现。**只证明提示词内部不再打架，不证明成图会更好**。
    """

    GAZE_AWAY = ("往外看", "看向窗外", "望向远处", "别过脸")

    def test_no_front_selfie_recipe_asks_the_gaze_to_leave_the_lens(self):
        for name, recipe in RECIPES.items():
            if recipe.camera != "front_selfie":
                continue
            with self.subTest(recipe=name):
                for phrase in self.GAZE_AWAY:
                    self.assertNotIn(phrase, recipe.action,
                                     f"{name} 要求脸朝镜头，动作却把视线引开：{recipe.action}")

    def test_the_train_selfie_puts_the_scenery_behind_the_subject(self):
        """改成包里已有的范式：landmark / aurora 的自拍都是「……在身后」。"""
        photo = self.direct("train")
        self.assertEqual(photo.draft.camera, "front_selfie", "镜头模式保持不变")
        self.assertIn("身后", photo.prompt)
        for phrase in self.GAZE_AWAY:
            self.assertNotIn(phrase, photo.prompt)

    def test_a_window_habit_is_not_emitted_under_a_front_selfie(self):
        """`affinity` 只管配方排序（rules.py），不控制出句——所以要在这里挡。"""
        context = builders.build_context("train")
        self.assertIn("look_out_window", context.dna.habits, "这只宠物本来就带这个习惯，否则挡不挡都看不出来")
        photo = self.direct("train")
        self.assertNotIn(HABIT_TEXT["look_out_window"], photo.prompt)

    def test_the_same_habit_still_reaches_a_camera_that_does_not_fight_it(self):
        """正向对照：挡掉的只是冲突组合，不是把这个习惯从词表里删了。"""
        context = builders.build_context("train")
        photo = self.direct("train")
        free = replace(photo.draft, camera="fixed_companion_camera")
        self.assertNotIn("fixed_companion_camera", CAMERA_CONFLICTING_HABITS)
        self.assertIn(HABIT_TEXT["look_out_window"], "；".join(_dna_clauses(context, free)))

    def test_the_same_pet_still_gets_the_habit_in_a_non_selfie_scene(self):
        """端到端正向对照：**同一只**带这个习惯的宠物，换到不冲突的镜头，整条编译链仍然发出它。

        上面那条正向对照只测到 `_dna_clauses` 这一层；没有这一条，
        把抑制写成"无条件删掉这个习惯"也会全绿。
        """
        for scene, camera in (("home", "fixed_companion_camera"),
                              ("flight_adventure", "fixed_cockpit")):
            with self.subTest(scene=scene):
                context = builders.build_context(scene)
                self.assertIn("look_out_window", context.dna.habits, "这只宠物本来就带这个习惯")
                photo = self.direct(scene)
                self.assertEqual(photo.draft.camera, camera)
                self.assertIn(HABIT_TEXT["look_out_window"], photo.prompt,
                              f"{scene} 的镜头不与它冲突，这一句不该被挡掉")

    def test_the_verified_train_facts_survive_the_wording_change(self):
        """改的只是措辞：核验过的火车事实一个都不能少。"""
        recipe = RECIPES["train_watch_selfie"]
        self.assertEqual(recipe.requires, frozenset({"on_train", "train_window"}))
        photo = self.direct("train")
        self.assertIn("on_train", photo.draft.visible_facts)
        self.assertIn("train_window", photo.draft.visible_facts)
