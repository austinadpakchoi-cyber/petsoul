"""照片导演：缺必需事实/身份参考/授权时**暂不生成**，不靠规则默认补齐。

区分两类：
  - 可选偏好（表情、角度、天气、可选物件、地点参考）——规则导演可以给默认；
  - 必需事实、身份参考、授权——缺了就 hold，不编造。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "photo_director"))

import builders  # noqa: E402
from harness import OfflineCase  # noqa: E402

from app.web_photo_director import PhotoDirectorError, readiness, require_ready  # noqa: E402


class HoldOnMissingRequiredTests(OfflineCase):
    def _state(self, scene_key, **kwargs):
        access_overrides = kwargs.pop("access", {})
        context = builders.build_context(scene_key, **kwargs)
        return context, readiness(context, builders.build_access(context, **access_overrides))

    def test_no_facts_at_all_holds_instead_of_inventing_a_scene(self):
        scene = builders.build_scene("cafe", "fx-pet-amber", facts=[])
        _, state = self._state("cafe", scene=scene)
        self.assertFalse(state)
        self.assertEqual(state.reason, "hold_missing_required")
        self.assertIn("required_fact:at_cafe", state.missing_required)

    def test_rules_never_substitute_a_default_for_a_missing_required_fact(self):
        """走 direct() 也必须拒，而不是给一张"看起来合理"的图。"""
        scene = builders.build_scene("cafe", "fx-pet-amber", facts=[])
        with self.assertRaises(PhotoDirectorError) as caught:
            self.direct("cafe", scene=scene)
        self.assertIn(str(caught.exception),
                      {"scene_evidence_missing", "no_recipe_for_verified_facts"})

    def test_missing_identity_reference_holds(self):
        _, state = self._state("cafe", references=[])
        self.assertFalse(state)
        self.assertIn("identity_reference", state.missing_required)

    def test_unreadable_identity_reference_holds(self):
        media = builders.build_identity_media("fx-pet-amber")
        broken = type(media)(
            reference_id=media.reference_id, sha256=media.sha256, role=media.role,
            source=media.source, pet_id=media.pet_id, household_id=media.household_id,
            mime_type=media.mime_type, ready=False, authorized=True,
        )
        _, state = self._state("cafe", references=[broken])
        self.assertFalse(state)
        self.assertIn("identity_reference:unavailable", state.missing_required)

    def test_each_revoked_authorisation_is_named(self):
        for flag in ("can_access", "generated_photos", "photo_dna", "reference_use"):
            with self.subTest(flag=flag):
                _, state = self._state("cafe", access={flag: False})
                self.assertFalse(state)
                self.assertIn(f"authorisation:{flag}", state.missing_required)

    def test_scene_without_a_fact_source_holds(self):
        scene = builders.build_scene("gym", "fx-pet-amber", origin="world_event")
        _, state = self._state("gym", scene=scene)
        self.assertFalse(state)
        self.assertIn("fact_source", state.missing_required)

    def test_no_possible_shot_reports_what_is_needed(self):
        """场景成立但没有任何拍法条件齐：也是 hold，并说出差什么。"""
        scene = builders.build_scene(
            "workshop", "fx-pet-amber", facts=["at_workshop", "parked_vehicle", "hand_tool"])
        _, state = self._state("workshop", scene=scene)
        self.assertFalse(state)
        self.assertEqual(state.reason, "hold_no_shot_is_possible")
        self.assertIn("photographer_present", state.missing_required)

    def test_require_ready_raises_with_the_same_wording(self):
        scene = builders.build_scene("cafe", "fx-pet-amber", facts=[])
        context = builders.build_context("cafe", scene=scene)
        with self.assertRaises(PhotoDirectorError) as caught:
            require_ready(context, builders.build_access(context))
        self.assertIn("hold_missing_required", str(caught.exception))


class PrecheckMatchesFinalFenceTests(OfflineCase):
    """预检必须和最终围栏一致，否则会出现"预检说能拍、最终又拒"的误报。"""

    def assert_same_verdict(self, context, access, expected_code: str):
        state = readiness(context, access)
        self.assertFalse(state, f"预检应当挡下 {expected_code}")
        self.assertEqual(state.reason, "hold_validation_failed")
        self.assertEqual(state.missing_required, (expected_code,))
        with self.assertRaises(PhotoDirectorError) as caught:
            self.director.direct(context, access)
        self.assertEqual(str(caught.exception), expected_code)

    def test_stale_authorisation_version_is_caught_by_the_precheck(self):
        context = builders.build_context("cafe")
        access = builders.build_access(context, versions=builders.build_versions(privacy=99))
        self.assert_same_verdict(context, access, "versions_changed")

    def test_a_reference_belonging_to_another_pet_is_caught_by_the_precheck(self):
        sibling = builders.build_identity_media("fx-pet-mochi")
        context = builders.build_context("cafe", references=[sibling])
        self.assert_same_verdict(context, builders.build_access(context),
                                 "reference_subject_mismatch")

    def test_an_edited_source_event_is_caught_by_the_precheck(self):
        context = builders.build_context("cafe")
        access = builders.build_access(context, event_revision=context.scene.revision + 1)
        self.assert_same_verdict(context, access, "event_revision_changed")

    def test_a_companion_without_consent_is_caught_by_the_precheck(self):
        context = builders.build_context(
            "landmark", companion_key="fx-pet-mochi", companion_consent="none")
        self.assert_same_verdict(context, builders.build_access(context),
                                 "companion_consent_missing")

    def test_legitimate_input_still_passes_both(self):
        """正常对照：合法输入既过预检，也真的出得了指令。"""
        context = builders.build_context("cafe", with_place_reference=True)
        access = builders.build_access(context)
        self.assertTrue(readiness(context, access))
        self.assertTrue(self.director.direct(context, access).prompt)

    def test_a_legitimate_duo_still_passes_both(self):
        context = builders.build_context("landmark", companion_key="fx-pet-mochi")
        access = builders.build_access(context)
        self.assertTrue(readiness(context, access))
        self.assertEqual(self.director.direct(context, access).draft.recipe,
                         "landmark_duo_selfie")


class OptionalPreferencesTests(OfflineCase):
    def test_only_the_mandatory_fact_is_enough_to_shoot(self):
        """可选物件缺席不该拦住出图——这就是"偏好"和"必需"的分界。"""
        scene = builders.build_scene("cafe", "fx-pet-amber", facts=["at_cafe"])
        context = builders.build_context("cafe", scene=scene)
        state = readiness(context, builders.build_access(context))
        self.assertTrue(state)
        self.assertIn("optional_object:coffee_cup", state.optional_absent)

    def test_absent_optionals_are_listed_but_never_rendered(self):
        scene = builders.build_scene("cafe", "fx-pet-amber", facts=["at_cafe"])
        photo = self.direct("cafe", scene=scene)
        self.assertNotIn("那杯咖啡", photo.prompt)
        self.assertNotIn("coffee_cup", photo.draft.visible_facts)

    def test_missing_place_reference_is_optional_not_blocking(self):
        context = builders.build_context("cafe")
        state = readiness(context, builders.build_access(context))
        self.assertTrue(state)
        self.assertIn("optional:place_reference", state.optional_absent)

    def test_a_fully_supplied_context_reports_nothing_missing(self):
        context = builders.build_context("cafe", with_place_reference=True)
        state = readiness(context, builders.build_access(context))
        self.assertTrue(state)
        self.assertEqual(state.missing_required, ())
        self.assertNotIn("optional:place_reference", state.optional_absent)


if __name__ == "__main__":
    unittest.main()
