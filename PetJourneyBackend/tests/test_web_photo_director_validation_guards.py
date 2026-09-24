"""`validation.py` 里每一条拒绝守卫各一条用例，断言**具体是哪一个原因码**。全程禁网。

为什么单独补这一批：这些守卫此前**一条都没有被任何用例触发过**。
一条从未被触发过的守卫，和一条写错了的守卫，**在测试证据上无法区分**——
不是说它们坏了，是没有证据说明它们好。而本包的价值主张正是「宁可不画也不编」，
**拒绝路径就是产品本身**，不是边角。

两条写法约定：

1. **走完整路径**（`director.direct`），不直接调 `validate_*`——要证明的是真实调用链上会拒，
   不是那个函数单独拿出来会拒。
2. **断言原因码字面**，不只断言"抛了异常"。`assertRaises` 单独用分不清抛的是不是**该抛的那一条**；
   校验是有顺序的，构造稍有偏差就会先撞上前面的守卫，看起来红了其实测的是别的东西。

覆盖的是 `validation.py` 里的点位。同一个原因码在别的文件另有 raise 的
（`camera_not_allowed`、`conflicting_weather`、`reference_role_not_supported`），
**那一处不在本文件**——按点位而不是按原因码分工，否则两边各写一条、各覆盖一处，
断言字面还完全相同，互相看不出漏了。
"""
from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "photo_director"))

import builders  # noqa: E402

from harness import OfflineCase  # noqa: E402

from app.web_photo_director import PhotoDirectorError  # noqa: E402

OTHER_SHA = "b" * 64


class ValidationGuardTests(OfflineCase):
    def refuse(self, context, code: str, **access_overrides) -> None:
        """跑完整导演流程，断言它拒了，且拒的**正是** `code` 这一条。"""
        access = builders.build_access(context, **access_overrides)
        with self.assertRaises(PhotoDirectorError) as caught:
            self.director.direct(context, access)
        self.assertEqual(str(caught.exception), code)

    # ---- validate_context ----

    def test_config_version_that_is_not_an_identifier_is_refused(self):
        """标识符里混进空格/叹号——照抄进提示词就是一条注入面。"""
        context = replace(builders.build_context("cafe"), config_version="photo config v1!")
        self.refuse(context, "invalid_identifier")

    def test_a_negative_version_number_is_refused(self):
        context = builders.build_context("cafe", versions=builders.build_versions(activity=-1))
        self.refuse(context, "invalid_versions")

    def test_a_camera_outside_the_catalogue_is_refused(self):
        context = builders.build_context("cafe", requested_camera="drone_orbit")
        self.refuse(context, "camera_not_allowed")

    def test_dna_projected_at_another_version_is_refused(self):
        """DNA 投影的版本和上下文声明的版本对不上——不能拿旧投影配新版本。"""
        context = builders.build_context("cafe")
        context = replace(context, dna=replace(context.dna, version=context.versions.dna + 5))
        self.refuse(context, "dna_version_mismatch")

    # ---- validate_identity ----

    def test_an_identity_belonging_to_another_pet_is_refused(self):
        context = builders.build_context("cafe")
        context = replace(context, identity=replace(context.identity, pet_id="fx-pet-someone-else"))
        self.refuse(context, "identity_subject_mismatch")

    def test_an_unsupported_species_is_refused(self):
        context = builders.build_context("cafe")
        context = replace(context, identity=replace(context.identity, species="dragon"))
        self.refuse(context, "identity_kind_not_supported")

    def test_an_identity_digest_that_is_not_a_sha256_is_refused(self):
        context = builders.build_context("cafe")
        context = replace(context, identity=replace(context.identity, sha256="not-a-digest"))
        self.refuse(context, "identity_version_or_digest")

    def test_an_appearance_tag_outside_the_whitelist_is_refused(self):
        """外观标签是白名单，不是自由文本——否则主人的原话能顺着它进提示词。"""
        context = builders.build_context("cafe")
        context = replace(context, identity=replace(context.identity, appearance_tags=("neon_glow",)))
        self.refuse(context, "appearance_not_allowed")

    # ---- validate_scene ----

    def test_a_negative_event_revision_is_refused(self):
        scene = builders.build_scene("cafe", "fx-pet-amber", revision=-1)
        context = builders.build_context("cafe", scene=scene)
        self.refuse(context, "invalid_event_revision")

    def test_the_same_fact_twice_is_refused(self):
        scene = builders.build_scene("cafe", "fx-pet-amber", facts=["at_cafe", "at_cafe"])
        context = builders.build_context("cafe", scene=scene)
        self.refuse(context, "duplicate_fact")

    def test_a_fact_token_outside_the_scene_vocabulary_is_refused(self):
        """场景自己声明它认哪些事实词；词表之外的一律拒，不猜。"""
        scene = builders.build_scene("cafe", "fx-pet-amber", facts=["at_cafe", "weather_foggy"])
        context = builders.build_context("cafe", scene=scene)
        self.refuse(context, "fact_not_verified_or_allowed")

    def test_two_different_weathers_at_once_are_refused(self):
        """同一时刻不能既晴又雨——两条都"已核实"时，问题在事实源，不在照片。"""
        scene = builders.build_scene(
            "cafe", "fx-pet-amber", facts=["at_cafe", "weather_sunny", "weather_rainy"])
        context = builders.build_context("cafe", scene=scene)
        self.refuse(context, "conflicting_weather")

    # ---- validate_references ----

    def test_a_reference_digest_that_is_not_a_sha256_is_refused(self):
        context = builders.build_context("cafe")
        first = replace(context.references[0], sha256="0123")
        context = replace(context, references=(first,))
        self.refuse(context, "reference_digest_or_duplicate")

    def test_an_unsupported_reference_mime_is_refused(self):
        context = builders.build_context("cafe")
        first = replace(context.references[0], mime_type="image/gif")
        context = replace(context, references=(first,))
        self.refuse(context, "reference_mime_not_supported")

    def test_a_companion_reference_pointing_at_the_subject_is_refused(self):
        """"同伴"参考图指向主角自己——那不是同伴，是把主角算了两次。"""
        context = builders.build_context("cafe")
        first = replace(context.references[0], role="companion_identity")
        context = replace(context, references=(first,))
        self.refuse(context, "companion_reference_is_subject")

    def test_an_unknown_reference_role_is_refused(self):
        context = builders.build_context("cafe")
        first = replace(context.references[0], role="watermark_overlay")
        context = replace(context, references=(first,))
        self.refuse(context, "reference_role_not_supported")

    def test_an_identity_reference_that_is_not_the_canonical_one_is_refused(self):
        """摘要合法但不是身份登记的那一张——像对的，其实换了张脸。"""
        context = builders.build_context("cafe")
        first = replace(context.references[0], sha256=OTHER_SHA)
        context = replace(context, references=(first,))
        self.refuse(context, "canonical_identity_reference_mismatch")

    def test_more_than_three_references_are_refused(self):
        """身份 1 ＋ 地点 1 ＋ 同伴 1 是上限；再多模型分不清该照哪张脸。"""
        context = builders.build_context("cafe", with_place_reference=True)
        place = context.references[-1]
        extra = replace(place, reference_id=place.reference_id + "-2")
        another = replace(place, reference_id=place.reference_id + "-3")
        context = replace(context, references=(*context.references, extra, another))
        self.refuse(context, "too_many_references")

    # ---- validate_companions ----

    def test_two_companions_are_refused(self):
        companion = builders.build_companion("fx-pet-mochi", "fx-pet-amber")
        context = builders.build_context("cafe", companion_key="fx-pet-mochi")
        context = replace(context, companions=(context.companions[0], companion))
        self.refuse(context, "too_many_companions")

    def test_a_companion_from_another_household_is_refused(self):
        """同一个家庭不等于默认可以入镜，跨家庭更不行。"""
        context = builders.build_context("cafe", companion_key="fx-pet-mochi")
        companion = replace(context.companions[0], household_id="fx-home-elsewhere")
        context = replace(context, companions=(companion,))
        self.refuse(context, "companion_household_mismatch")

    def test_a_companion_of_an_unsupported_species_is_refused(self):
        context = builders.build_context("cafe", companion_key="fx-pet-mochi")
        companion = replace(context.companions[0], species="dragon")
        context = replace(context, companions=(companion,))
        self.refuse(context, "companion_kind_or_digest")

    def test_a_companion_appearance_tag_outside_the_whitelist_is_refused(self):
        context = builders.build_context("cafe", companion_key="fx-pet-mochi")
        companion = replace(context.companions[0], appearance_tags=("neon_glow",))
        context = replace(context, companions=(companion,))
        self.refuse(context, "companion_appearance_not_allowed")

    def test_a_companion_without_its_own_reference_is_refused(self):
        """同伴要有自己那张参考图——不能拿主角的脸去画第二只。"""
        context = builders.build_context(
            "cafe", companion_key="fx-pet-mochi",
            references=[builders.build_identity_media("fx-pet-amber")])
        self.refuse(context, "companion_reference_required")

    def test_a_companion_reference_that_does_not_match_the_companion_is_refused(self):
        context = builders.build_context("cafe", companion_key="fx-pet-mochi")
        companion_media = replace(context.references[1], sha256=OTHER_SHA)
        context = replace(context, references=(context.references[0], companion_media))
        self.refuse(context, "companion_reference_mismatch")


if __name__ == "__main__":
    unittest.main()
