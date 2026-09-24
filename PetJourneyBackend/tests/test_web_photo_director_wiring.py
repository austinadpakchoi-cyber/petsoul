"""照片导演 P3：生产路径闸门与交付不静默丢字段。全程禁网、无供应商调用、无费用。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "photo_director"))

import builders  # noqa: E402
from harness import OfflineCase  # noqa: E402

from app.web_photo_director import (  # noqa: E402
    CURRENT_WEB_SINK,
    PhotoDirectorError,
    describe_gap,
    plan_delivery,
)
from app.web_photo_director import SinkCapabilities  # noqa: E402
from app.web_photo_director.delivery import TARGET_SINK  # noqa: E402
from app.web_photo_director.recipes import SCENES, TARGET_SCENES  # noqa: E402
from app.web_photo_director.validation import FICTIONAL_NARRATIVES  # noqa: E402


class FactSourceGateTests(OfflineCase):
    def test_only_four_scenes_are_wired_for_production(self):
        self.assertEqual(TARGET_SCENES, ("cafe", "flight_adventure", "home", "train"))

    def test_a_scene_without_a_fact_source_is_refused_on_real_events(self):
        """配方写好了不等于世界侧产得出它要的事实。正式事件走到它必须拒。"""
        scene = builders.build_scene("gym", "fx-pet-amber", origin="world_event")
        with self.assertRaises(PhotoDirectorError) as caught:
            self.direct("gym", scene=scene)
        self.assertEqual(str(caught.exception), "scene_has_no_fact_source")

    def test_the_same_scene_still_works_as_an_evaluation_fixture(self):
        photo = self.direct("gym")  # builders 按 fact_source 标成 evaluation_fixture
        self.assertEqual(photo.scene, "gym")
        self.assertEqual(photo.draft.camera, "mirror_selfie")

    def test_each_target_scene_is_recorded_with_an_honest_origin(self):
        """日常题材＝世界自己发生的事；虚构题材＝主人下令拍的，**不是**世界事件。

        这条原来写成"目标场景一律 world_event"，把虚构飞行也算了进去，
        等于固化了"想象出来的照片可以记成真事"。反面用例见 guards。
        """
        for key in TARGET_SCENES:
            with self.subTest(scene=key):
                context = builders.build_context(key)
                fictional = context.scene.narrative in FICTIONAL_NARRATIVES
                self.assertEqual(context.scene.origin, "owner_directed" if fictional else "world_event")
                self.assertTrue(self.director.direct(context, builders.build_access(context)).prompt)

    def test_every_scene_declares_a_known_fact_source(self):
        for key, spec in SCENES.items():
            with self.subTest(scene=key):
                self.assertIn(spec.fact_source, {"target", "fixture_only"})


class DeliveryTests(OfflineCase):
    def test_current_sink_cannot_carry_the_negative_prompt(self):
        """负面词整段消失是语义丢失，默认直接拒绝出图，而不是悄悄发出去。"""
        photo = self.direct("cafe")
        with self.assertRaises(PhotoDirectorError) as caught:
            plan_delivery(photo, CURRENT_WEB_SINK)
        self.assertIn("negative_prompt", str(caught.exception))

    def test_non_strict_mode_reports_exactly_what_is_lost(self):
        photo = self.direct("cafe")
        plan = plan_delivery(photo, CURRENT_WEB_SINK, strict=False)
        self.assertIn("negative_prompt", plan.dropped)
        self.assertFalse(plan.lossless)
        self.assertTrue(any("负面提示词" in note for note in plan.notes))
        self.assertIsNone(plan.negative_prompt)

    def test_companion_reference_is_flagged_not_silently_dropped(self):
        context = builders.build_context("landmark", companion_key="fx-pet-mochi")
        photo = self.director.direct(context, builders.build_access(context))
        plan = plan_delivery(photo, CURRENT_WEB_SINK, strict=False)
        self.assertIn("companion_identity", plan.dropped)
        self.assertTrue(any("companion_identity" in note for note in plan.notes))

    def test_a_single_reference_sink_must_not_drop_the_companion_quietly(self):
        """字段全支持、但只接一张参考：同伴照样会丢，strict 必须拒。

        这条曾经漏判过——超出张数上限记的是 `reference:<role>`，
        当时的语义丢失判定只看角色名本身，于是 strict 放行了。
        """
        single = SinkCapabilities(
            name="single-ref-but-full-featured", max_references=1,
            supports_negative_prompt=True,
            known_reference_roles=frozenset(
                {"pet_identity", "companion_identity", "place_environment"}),
            preserves_reference_order=True, allowed_sizes=frozenset({"2048x2048"}),
        )
        context = builders.build_context("landmark", companion_key="fx-pet-mochi")
        photo = self.director.direct(context, builders.build_access(context))
        self.assertEqual(len(photo.references), 2)
        with self.assertRaises(PhotoDirectorError) as caught:
            plan_delivery(photo, single)
        self.assertIn("reference:companion_identity", str(caught.exception))

        relaxed = plan_delivery(photo, single, strict=False)
        self.assertIn("reference:companion_identity", relaxed.dropped)
        self.assertEqual(len(relaxed.references), 1)

    def test_a_single_reference_sink_is_fine_when_there_is_no_companion(self):
        """单宠照片在单参考入口上没有任何丢失——不要把闸门收得太紧。"""
        single = SinkCapabilities(
            name="single-ref-but-full-featured", max_references=1,
            supports_negative_prompt=True,
            known_reference_roles=frozenset({"pet_identity", "place_environment"}),
            preserves_reference_order=True, allowed_sizes=frozenset({"2048x2048"}),
        )
        plan = plan_delivery(self.direct("cafe"), single)
        self.assertTrue(plan.lossless)

    def test_target_sink_carries_everything(self):
        context = builders.build_context("landmark", companion_key="fx-pet-mochi")
        photo = self.director.direct(context, builders.build_access(context))
        plan = plan_delivery(photo, TARGET_SINK)
        self.assertTrue(plan.lossless)
        self.assertEqual(plan.negative_prompt, photo.negative_prompt)
        self.assertEqual([slot[1] for slot in plan.references],
                         ["pet_identity", "companion_identity"])

    def test_identity_reference_stays_first(self):
        photo = self.direct("cafe", with_place_reference=True)
        plan = plan_delivery(photo, TARGET_SINK)
        self.assertEqual(plan.references[0][1], "pet_identity")

    def test_size_must_match_what_the_sink_accepts(self):
        photo = self.direct("cafe")
        self.assertEqual(photo.size, "2048x2048")  # 该模型要求约 369 万像素
        self.assertIn(photo.size, CURRENT_WEB_SINK.allowed_sizes)

    def test_gap_report_names_the_four_things_a_must_change(self):
        gap = describe_gap(CURRENT_WEB_SINK)
        self.assertEqual(gap["max_references"], {"now": 1, "needed": 3})
        self.assertEqual(gap["negative_prompt"], {"now": False, "needed": True})
        self.assertIn("companion_identity", gap["reference_roles"]["needed"])
        self.assertNotIn("companion_identity", gap["reference_roles"]["now"])
        self.assertEqual(gap["preserves_reference_order"], {"now": False, "needed": True})


if __name__ == "__main__":
    unittest.main()
