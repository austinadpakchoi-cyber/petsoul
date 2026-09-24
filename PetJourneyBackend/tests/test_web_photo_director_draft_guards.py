"""`draft.py` 的拒绝路径：每一条守卫都要有一次**真的被触发**的证据。全程禁网。

为什么单开一份：自测覆盖实测发现，186 项全绿之下本包仍有 49 种拒绝原因码
一次都没被执行过。对一个「宁可不画也不编」的包来说**拒绝路径就是产品本身**——
一条从未被触发过的守卫，和一条写错了的守卫，在测试证据上无法区分。

这份只覆盖 `draft.py` 的点位（`validation.py` 那批在另一份里）。
两类用例分开放：

- `DraftRejectionTests`：**真的走到那一行 raise**，并断言原因码字面；
- `StructurallyUnreachableTests`：这几条守卫在公开路径上**当前不可达**，
  因为另一条更早的检查必然先拦下。这里不假装触发它们，而是**钉住让它们不可达的那条结构不变量**——
  将来谁加了一条破坏该不变量的配方，守卫就变成可达的，这里会当场失败并指出来。
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "photo_director"))

import builders  # noqa: E402
from harness import OfflineCase  # noqa: E402

from app.web_photo_director import PhotoDirectorError  # noqa: E402
from app.web_photo_director.contracts import SceneDraft  # noqa: E402
from app.web_photo_director.draft import (  # noqa: E402
    CAMERA_PRECONDITION,
    _camera_possible,
    assert_fact_source,
    eligible_recipes,
    parse_model_draft,
    validate_draft,
)
from app.web_photo_director.catalog import CAMERAS  # noqa: E402
from app.web_photo_director.recipes import RECIPES  # noqa: E402


class DraftRejectionTests(OfflineCase):
    """每条都必须真的走到那一行 raise，不靠"恰好也报这个码"的近路。"""

    def draft_for(self, recipe_name: str, **overrides) -> SceneDraft:
        """按配方补齐镜头与构图，再让调用方只改它想改的那一项。"""
        recipe = RECIPES[recipe_name]
        fields = {"recipe": recipe_name, "camera": recipe.camera,
                  "composition": recipe.composition, "expression": recipe.expression,
                  "visible_facts": ()}
        fields.update(overrides)
        return SceneDraft(**fields)

    def rejects(self, draft: SceneDraft, context, code: str) -> None:
        with self.assertRaises(PhotoDirectorError) as caught:
            validate_draft(draft, context)
        self.assertEqual(str(caught.exception), code)

    # ---- assert_fact_source ----
    def test_a_scene_outside_the_catalogue_is_refused(self):
        context = builders.build_context("cafe")
        unknown = replace(context, scene=replace(context.scene, scene="no_such_scene"))
        with self.assertRaises(PhotoDirectorError) as caught:
            assert_fact_source(unknown)
        self.assertEqual(str(caught.exception), "scene_not_supported")

    def test_a_fixture_only_scene_is_refused_on_a_real_world_event(self):
        """`gym` 只在评测输入里可选；标成世界事件就必须被拦下。"""
        context = builders.build_context("gym")
        faked = replace(context, scene=replace(context.scene, origin="world_event"))
        with self.assertRaises(PhotoDirectorError) as caught:
            assert_fact_source(faked)
        self.assertEqual(str(caught.exception), "scene_has_no_fact_source")

    def test_no_recipe_is_offered_when_the_world_cannot_produce_the_facts(self):
        context = builders.build_context("gym")
        faked = replace(context, scene=replace(context.scene, origin="world_event"))
        self.assertEqual(eligible_recipes(faked), ())

    # ---- 配方与镜头 ----
    def test_a_recipe_whose_story_mode_does_not_fit_the_event_is_refused(self):
        context = builders.build_context("flight_adventure")
        daily = replace(context, scene=replace(context.scene, narrative="daily_life"))
        recipe = eligible_recipes(context)[0]
        self.rejects(self.draft_for(recipe), daily, "recipe_story_mode_mismatch")

    def test_a_camera_that_does_not_belong_to_the_recipe_is_refused(self):
        context = builders.build_context("cafe")
        recipe = eligible_recipes(context)[0]
        # 不写死某个镜头：写死会在它恰好就是这条配方自己的镜头时静默失效
        other = next(c for c in sorted(CAMERAS) if c != RECIPES[recipe].camera)
        self.rejects(self.draft_for(recipe, camera=other), context,
                     "camera_not_for_recipe")

    def test_a_composition_that_does_not_belong_to_the_recipe_is_refused(self):
        context = builders.build_context("cafe")
        recipe = eligible_recipes(context)[0]
        self.rejects(self.draft_for(recipe, composition="window_journey"), context,
                     "composition_not_for_recipe")

    def test_an_expression_outside_the_closed_vocabulary_is_refused(self):
        context = builders.build_context("cafe")
        recipe = eligible_recipes(context)[0]
        self.rejects(self.draft_for(recipe, expression="smug"), context,
                     "expression_not_allowed")

    def test_a_recipe_is_refused_when_one_of_its_facts_was_never_verified(self):
        """`cafe_drink_selfie` 要那杯咖啡；没点单就不能用这条配方。"""
        scene = builders.build_scene("cafe", "fx-pet-amber", facts=("at_cafe",))
        context = builders.build_context("cafe", scene=scene)
        self.rejects(self.draft_for("cafe_drink_selfie"), context,
                     "recipe_requires_unverified_fact")

    # ---- 同伴 ----
    def test_a_two_subject_recipe_without_a_companion_is_refused(self):
        context = builders.build_context("landmark")
        duo = next(k for k, r in RECIPES.items() if r.scene == "landmark" and r.subjects == 2)
        self.rejects(self.draft_for(duo, visible_facts=("at_landmark",)), context,
                     "companion_required_for_recipe")

    def test_a_single_subject_recipe_with_a_companion_present_is_refused(self):
        context = builders.build_context("cafe", companion_key="fx-pet-mochi")
        solo = next(k for k, r in RECIPES.items() if r.scene == "cafe" and r.subjects == 1)
        self.rejects(self.draft_for(solo), context, "companion_not_allowed_for_recipe")

    # ---- 画面内容 ----
    def test_more_visible_facts_than_the_ceiling_are_refused(self):
        context = builders.build_context("cafe")
        recipe = eligible_recipes(context)[0]
        too_many = ("at_cafe", "coffee_cup", "weather_sunny", "at_cafe", "coffee_cup", "at_cafe")
        self.rejects(self.draft_for(recipe, visible_facts=too_many), context,
                     "too_many_visible_facts")

    def test_a_repeated_visible_fact_is_refused(self):
        context = builders.build_context("cafe")
        recipe = eligible_recipes(context)[0]
        self.rejects(self.draft_for(recipe, visible_facts=("at_cafe", "at_cafe")), context,
                     "duplicate_visible_fact")

    def test_a_visible_fact_that_does_not_belong_to_this_scene_is_refused(self):
        context = builders.build_context("cafe")
        recipe = eligible_recipes(context)[0]
        self.rejects(self.draft_for(recipe, visible_facts=("at_cafe", "gym_bench")), context,
                     "visible_fact_not_for_scene")

    def test_a_recipe_fact_missing_from_the_frame_is_refused(self):
        """配方点名要画的东西，不能只写在 requires 里却不进画面。"""
        context = builders.build_context("cafe")
        self.rejects(self.draft_for("cafe_drink_selfie", visible_facts=("at_cafe",)), context,
                     "recipe_fact_not_visible")

    def test_a_precondition_is_refused_as_visible_content(self):
        """同伴在场是前提，不是画面内容——画面里不该出现拍摄者。"""
        scene = builders.build_scene(
            "cafe", "fx-pet-amber", facts=("at_cafe", "coffee_cup", "photographer_present"))
        context = builders.build_context("cafe", scene=scene)
        self.rejects(self.draft_for("cafe_drink_selfie",
                                    visible_facts=("at_cafe", "coffee_cup", "photographer_present")),
                     context, "precondition_is_not_visible_content")

    def test_two_weather_tokens_in_one_frame_are_refused(self):
        scene = builders.build_scene(
            "cafe", "fx-pet-amber", facts=("at_cafe", "weather_sunny", "weather_rainy"))
        context = builders.build_context("cafe", scene=scene)
        self.rejects(self.draft_for("cafe_observe_selfie",
                                    visible_facts=("at_cafe", "weather_sunny", "weather_rainy")),
                     context, "conflicting_weather")

    # ---- 模型回复解析 ----
    def test_an_empty_model_reply_is_refused(self):
        context = builders.build_context("cafe")
        with self.assertRaises(PhotoDirectorError) as caught:
            parse_model_draft("   ", context)
        self.assertEqual(str(caught.exception), "model_output_empty")

    def test_a_model_reply_that_is_not_an_object_is_refused(self):
        context = builders.build_context("cafe")
        with self.assertRaises(PhotoDirectorError) as caught:
            parse_model_draft("[1, 2]", context)
        self.assertEqual(str(caught.exception), "model_output_not_object")

    def test_a_model_reply_whose_facts_are_not_a_list_is_refused(self):
        context = builders.build_context("cafe")
        with self.assertRaises(PhotoDirectorError) as caught:
            parse_model_draft('{"recipe": "x", "expression": "curious", '
                              '"visible_facts": "at_cafe"}', context)
        self.assertEqual(str(caught.exception), "model_output_facts_not_list")

    def test_a_model_reply_with_a_non_string_value_is_refused(self):
        context = builders.build_context("cafe")
        with self.assertRaises(PhotoDirectorError) as caught:
            parse_model_draft('{"recipe": 7, "expression": "curious"}', context)
        self.assertEqual(str(caught.exception), "model_output_value_not_string")


class StructurallyUnreachableTests(OfflineCase):
    """这几条守卫**当前不可达**：更早的一条检查必然先拦下。

    不假装触发它们（那只能靠 monkeypatch 词表，证明不了产品行为），
    而是钉住**让它们不可达的那条结构不变量**。将来谁破坏了不变量，
    守卫就变成可达的——那时这里会失败，并告诉他"现在该给它补一条真的触发用例了"。

    这几条原因码因此在本批**有意留空**，不是漏做：
    `photographer_not_present`、`mirror_not_present`、`own_device_not_present`、
    以及 `draft.py` 里的 `camera_not_allowed`。
    """

    def test_every_camera_precondition_is_also_listed_in_the_recipe_requires(self):
        """这条不变量成立 → `draft.py:112-115` 永远轮不到（`requires` 检查在它前面）。"""
        for name, recipe in RECIPES.items():
            precondition = CAMERA_PRECONDITION.get(recipe.camera)
            if precondition is None:
                continue
            with self.subTest(recipe=name):
                self.assertIn(
                    precondition[0], recipe.requires,
                    f"{name} 的镜头需要 {precondition[0]}，却没写进 requires——"
                    f"守卫 {precondition[1]} 从此可达，请为它补一条真的触发用例")

    def test_every_mirror_recipe_also_requires_the_pets_own_device(self):
        """这条不变量成立 → `draft.py:116-118`（`own_device_not_present`）永远轮不到。"""
        for name, recipe in RECIPES.items():
            if recipe.camera != "mirror_selfie":
                continue
            with self.subTest(recipe=name):
                self.assertIn("own_device", recipe.requires,
                              f"{name} 是镜中自拍却不要求 own_device——"
                              f"守卫 own_device_not_present 从此可达，请补真触发用例")

    def test_every_recipe_camera_is_inside_the_closed_vocabulary(self):
        """这条不变量成立 → `draft.py:101-102` 的 `camera_not_allowed` 永远轮不到：
        上一行已强制 `draft.camera == recipe.camera`。"""
        for name, recipe in RECIPES.items():
            with self.subTest(recipe=name):
                self.assertIn(recipe.camera, CAMERAS)

    def test_the_camera_helper_itself_still_rejects_a_missing_precondition(self):
        """守卫不可达不等于判断写错了：直接测这个辅助函数，把它的两条 False 分支钉住。

        **这不能替代真触发用例**——它证明的是函数对，不是产品路径会走到它。
        """
        self.assertFalse(_camera_possible("friend_camera", frozenset()))
        self.assertFalse(_camera_possible("mirror_selfie", frozenset({"gym_mirror"})))
        self.assertTrue(_camera_possible("front_selfie", frozenset()))
