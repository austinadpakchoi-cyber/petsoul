"""照片导演：多宠身份隔离、参考图角色与顺序、双宠合影，以及 DNA 只改取景不改身份。全程禁网。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "photo_director"))

import builders  # noqa: E402
from harness import OfflineCase  # noqa: E402

from app.web_photo_director import PhotoDirectorError  # noqa: E402


class IdentityIsolationTests(OfflineCase):
    def test_two_pets_never_share_an_identity_anchor(self):
        amber = self.direct("home", "fx-pet-amber")
        mochi = self.direct("home", "fx-pet-mochi")
        self.assertNotEqual(amber.identity_reference_id, mochi.identity_reference_id)
        self.assertNotEqual(amber.identity_sha256, mochi.identity_sha256)
        self.assertNotEqual(amber.context_key, mochi.context_key)
        self.assertIn("猫", amber.prompt)
        self.assertIn("狗", mochi.prompt)

    def test_a_pets_appearance_does_not_leak_into_another(self):
        amber = self.direct("home", "fx-pet-amber")
        mochi = self.direct("home", "fx-pet-mochi")
        self.assertIn("虎斑花纹", amber.prompt)
        self.assertNotIn("虎斑花纹", mochi.prompt)
        self.assertIn("垂耳", mochi.prompt)
        self.assertNotIn("垂耳", amber.prompt)

    def test_identity_reference_is_sent_first(self):
        photo = self.direct("cafe", with_place_reference=True)
        self.assertEqual([slot.role for slot in photo.references],
                         ["pet_identity", "place_environment"])
        self.assertEqual(photo.references[0].position, 0)

    def test_missing_identity_reference_is_refused(self):
        with self.assertRaises(PhotoDirectorError) as caught:
            self.direct("cafe", references=[])
        self.assertEqual(str(caught.exception), "canonical_identity_reference_required")

    def test_unreadable_reference_is_not_replaced_by_another_animal(self):
        """原照读不出来必须报错，不能悄悄换一只动物顶上，也不能只留一张环境图。"""
        media = builders.build_identity_media("fx-pet-amber")
        unreadable = type(media)(
            reference_id=media.reference_id, sha256=media.sha256, role=media.role,
            source=media.source, pet_id=media.pet_id, household_id=media.household_id,
            mime_type=media.mime_type, ready=False, authorized=True,
        )
        with self.assertRaises(PhotoDirectorError) as caught:
            self.direct("cafe", references=[unreadable])
        self.assertEqual(str(caught.exception), "reference_unavailable")

        only_place = [builders.build_place_media("cafe", "fx-pet-amber")]
        with self.assertRaises(PhotoDirectorError) as caught:
            self.direct("cafe", references=only_place)
        self.assertEqual(str(caught.exception), "canonical_identity_reference_required")

    def test_reference_of_another_pet_is_refused(self):
        """同一个家庭里另一只宠物的参考照也不行：锚点按宠物隔离，不按家庭。"""
        sibling = builders.build_identity_media("fx-pet-mochi")
        self.assertEqual(sibling.household_id,
                         builders.build_identity_media("fx-pet-amber").household_id)
        with self.assertRaises(PhotoDirectorError) as caught:
            self.direct("cafe", "fx-pet-amber", references=[sibling])
        self.assertEqual(str(caught.exception), "reference_subject_mismatch")

    def test_unauthorized_reference_is_refused(self):
        media = builders.build_identity_media("fx-pet-amber")
        denied = type(media)(
            reference_id=media.reference_id, sha256=media.sha256, role=media.role,
            source=media.source, pet_id=media.pet_id, household_id=media.household_id,
            mime_type=media.mime_type, ready=True, authorized=False,
        )
        with self.assertRaises(PhotoDirectorError) as caught:
            self.direct("cafe", references=[denied])
        self.assertEqual(str(caught.exception), "reference_unavailable")

    def test_place_reference_must_match_this_event(self):
        wrong = builders.build_place_media("cafe", "fx-pet-amber", event_id="fx-evt-other")
        with self.assertRaises(PhotoDirectorError) as caught:
            self.direct("cafe", references=[builders.build_identity_media("fx-pet-amber"), wrong])
        self.assertEqual(str(caught.exception), "environment_reference_mismatch")

    def test_unseen_parts_get_no_invented_markings(self):
        photo = self.direct("cafe")
        self.assertIn("参考图没拍到的部位保持普通", photo.prompt)


class CompanionTests(OfflineCase):
    def _duo(self, **kwargs):
        context = builders.build_context("landmark", companion_key="fx-pet-mochi", **kwargs)
        return context, self.director.direct(context, builders.build_access(context))

    def test_duo_uses_a_two_subject_recipe_with_its_own_reference(self):
        _, photo = self._duo()
        self.assertEqual(photo.draft.recipe, "landmark_duo_selfie")
        self.assertEqual(photo.companion_pet_ids, ("fx-pet-mochi",))
        self.assertEqual([slot.role for slot in photo.references],
                         ["pet_identity", "companion_identity"])
        self.assertIn("companion_identity_separate", photo.prompt_checks)

    def test_the_two_subjects_are_told_apart_in_the_prompt(self):
        _, photo = self._duo()
        self.assertIn("第二只动物", photo.prompt)
        self.assertIn("不能和主角混成同一只", photo.prompt)
        self.assertIn("垂耳", photo.prompt)   # 同伴的特征
        self.assertIn("虎斑花纹", photo.prompt)  # 主角的特征

    def test_companion_without_its_own_consent_is_refused(self):
        """住在同一个家庭不等于默认允许被放进另一只宠物的照片里。"""
        context = builders.build_context(
            "landmark", companion_key="fx-pet-mochi", companion_consent="none")
        with self.assertRaises(PhotoDirectorError) as caught:
            self.director.direct(context, builders.build_access(context))
        self.assertEqual(str(caught.exception), "companion_consent_missing")

    def test_household_permission_is_still_required(self):
        context = builders.build_context("landmark", companion_key="fx-pet-mochi")
        access = builders.build_access(context, companion_photos=False)
        with self.assertRaises(PhotoDirectorError) as caught:
            self.director.direct(context, access)
        self.assertEqual(str(caught.exception), "companion_photos_not_permitted")

    def test_single_subject_scene_refuses_a_companion(self):
        context = builders.build_context("gym", companion_key="fx-pet-mochi")
        with self.assertRaises(PhotoDirectorError) as caught:
            self.director.direct(context, builders.build_access(context))
        self.assertEqual(str(caught.exception), "no_recipe_for_verified_facts")

    def test_companion_cannot_be_the_subject_itself(self):
        context = builders.build_context("landmark", companion_key="fx-pet-amber")
        with self.assertRaises(PhotoDirectorError) as caught:
            self.director.direct(context, builders.build_access(context))
        self.assertEqual(str(caught.exception), "companion_is_subject")


class DNATests(OfflineCase):
    CALM = {"personality": ["calm"], "habits": ["curl_up"],
            "interests": ["home_comfort"], "preferences": ["quiet_corner"]}
    FLYER = {"personality": ["playful"], "habits": [],
             "interests": ["flying"], "preferences": ["wide_view"]}

    def test_dna_changes_the_shot_not_the_place(self):
        plain = self.direct("flight_adventure")
        flyer = self.direct("flight_adventure", dna_raw=self.FLYER)
        self.assertNotEqual(plain.draft.recipe, flyer.draft.recipe)
        self.assertEqual(flyer.draft.recipe, "cockpit_helmet_actioncam")
        # 同一只宠物、同一个事件：身份与地点必须一模一样
        self.assertEqual(plain.identity_reference_id, flyer.identity_reference_id)
        self.assertEqual(plain.identity_sha256, flyer.identity_sha256)
        self.assertEqual(plain.scene, flyer.scene)
        self.assertIn("云上", flyer.prompt)
        self.assertIn("一架虚构的小型飞行器", flyer.prompt)

    def test_dna_changes_pose_and_framing(self):
        curious = self.direct("home")
        calm = self.direct("home", dna_raw=self.CALM)
        self.assertNotEqual(curious.prompt, calm.prompt)

    def test_interests_never_become_visible_objects(self):
        """"喜欢咖啡香"是它去咖啡馆的理由，不是画面里的东西。"""
        photo = self.direct("train", dna_raw={"personality": ["calm"], "habits": [],
                                              "interests": ["coffee_aroma"], "preferences": []})
        self.assertNotIn("咖啡", photo.prompt)

    def test_dna_cannot_add_a_possession(self):
        scene = builders.build_scene("home", "fx-pet-amber", facts=["at_home"])
        photo = self.direct("home", scene=scene, dna_raw=self.CALM)
        self.assertNotIn("毯子", photo.prompt)
        self.assertNotIn("home_blanket", photo.draft.visible_facts)


if __name__ == "__main__":
    unittest.main()
