"""撤回用途授权要让在途的结论作废（验收 CR-Q13）。

家人在设置里关掉"模型回信"，是一次**授权变化**。提交前那道复核靠的是语义版本代数：
设置写进去了、代数没动，等于这次撤权对已经在途的提案完全不起作用——
旧提案照样出发、照样被记成"TA 自己决定的"。
所以设置变更与代数递增必须在**同一个事务**里完成，而且只影响这位家人真正参与照顾的那些家。

这里全部走正式接口 `PATCH /settings`，不手工 bump epoch。
"""

from __future__ import annotations

import unittest

from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class ConsentEpochTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("consent-owner")
        self.owner.adopt_and_move_in("adopt-lan")

    def epoch(self, pet_id: str | None = None) -> int:
        row = self.web.projector.runtime.row(pet_id or self.owner.pet_id) or {}
        return int(row.get("privacy_epoch") or 0)

    def versions(self, pet_id: str | None = None):
        return self.web.projector.versions(pet_id or self.owner.pet_id)

    def patch_settings(self, **body) -> None:
        response = self.owner.patch("/settings", body)
        self.assertEqual(response.status_code, 200, response.text)

    def test_turning_model_replies_on_and_off_moves_the_authorization_version(self) -> None:
        start = self.epoch()

        self.patch_settings(model_replies=True)
        after_on = self.epoch()
        self.patch_settings(model_replies=False)
        after_off = self.epoch()

        self.assertGreater(after_on, start, "开启也是一次授权变化")
        self.assertGreater(after_off, after_on, "撤回更是")

    def test_an_in_flight_proposal_is_stale_after_the_owner_revokes(self) -> None:
        """这正是 Q 复现的那条：提案依据的版本，在撤权之后必须被判为变了。"""
        self.patch_settings(model_replies=True)
        in_flight = self.versions()  # 决策开始时记下的版本

        self.patch_settings(model_replies=False)  # 思考期间家人在设置里关掉了

        self.assertEqual(tuple(in_flight.stale_fields(self.versions())), ("privacy_epoch",),
                         "撤权之后旧提案必须被判为过期，否则提交前那道复核形同虚设")

    def test_pet_messages_on_the_personal_settings_also_counts(self) -> None:
        before = self.epoch()

        self.patch_settings(pet_messages=False)

        self.assertGreater(self.epoch(), before, "TA 能不能主动来信也是用途授权")

    # ---- 家庭级的授权（写实照片、家庭频道来信）走另一个接口，同样要换代 ----
    def household_settings(self, **body) -> None:
        household_id = self.owner.get("/onboarding").json()["households"][0]["household_id"]
        response = self.owner.patch(f"/households/{household_id}/settings", body)
        self.assertEqual(response.status_code, 200, response.text)

    def test_household_level_authorization_moves_the_version(self) -> None:
        before = self.epoch()

        self.household_settings(generated_photos=True)

        self.assertGreater(self.epoch(), before, "写实照片是家庭级的用途授权")

    def test_renaming_the_household_is_not_an_authorization_change(self) -> None:
        before = self.epoch()

        self.household_settings(name="小海的家")

        self.assertEqual(self.epoch(), before, "改名字不该让在途的结论作废")

    def test_changing_only_the_timezone_is_not_an_authorization_change(self) -> None:
        before = self.epoch()

        self.patch_settings(timezone="Asia/Tokyo")

        self.assertEqual(self.epoch(), before, "时区只是显示口径，不该让在途的结论作废")

    def test_writing_the_same_value_again_does_not_move_the_version(self) -> None:
        self.patch_settings(model_replies=True)
        before = self.epoch()

        self.patch_settings(model_replies=True)

        self.assertEqual(self.epoch(), before, "值没变就不是一次授权变化")

    def test_the_revocation_covers_every_pet_in_the_household(self) -> None:
        household_id = self.owner.get("/onboarding").json()["households"][0]["household_id"]
        created = self.owner.upload_pet("小豆", "cat", household_id=household_id)
        self.assertEqual(created.status_code, 201, created.text)
        second = created.json()["pet_id"]
        self.assertEqual(self.owner.post("/onboarding/move-in", {"pet_id": second}).status_code, 200)
        before = (self.epoch(), self.epoch(second))

        self.patch_settings(model_replies=True)

        self.assertEqual((self.epoch() > before[0], self.epoch(second) > before[1]), (True, True), "一个家里的每只宠物都要换代")

    def test_another_household_is_not_affected(self) -> None:
        stranger = self.user("consent-stranger")
        stranger.adopt_and_move_in("adopt-mochi")
        before = self.epoch(stranger.pet_id)

        self.patch_settings(model_replies=True)

        self.assertEqual(self.epoch(stranger.pet_id), before, "别人家的宠物不该被波及")


if __name__ == "__main__":
    unittest.main()
