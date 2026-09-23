"""主人主动拍的照片，**网页上看得到结果**（COORD-I-PHOTO-VISIBLE，归 I）。

命令本身（状态核验、幂等、恢复）在 `test_web_photo_request_command.py`；这里只管闭环的后半截：
拍完之后刷新页面能不能拿回来、`unknown` 辨不辨得出、读列表会不会顺手驱动任务、谁能看、怎么重画。

替身生图，不联网、不产生付费调用。
"""

from __future__ import annotations

import unittest

from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase
from web_provider_fakes import FakeIllustrator


class PhotoRequestViewTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("photo-view-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.owner.patch("/settings", {"generated_photos": True})
        self.illustrator = FakeIllustrator()
        self.web.illustrations.illustrator = self.illustrator
        # 同另一份文件：来源走正式装配，用真实 `set_portrait` 持久化基准照（同一条 UPDATE 置 photo_generated=1）。
        self.web.pets.set_portrait(self.owner.pet_id, b"reference-photo", "image/png")

    def ask(self, scene: str = "home", narrative: str = "daily_life"):
        return self.owner.post(f"/pets/{self.owner.pet_id}/photo-request", {"scene": scene, "narrative": narrative})

    def photos(self, who=None, pet_id: str | None = None):
        user = who or self.owner
        return user.get(f"/pets/{pet_id or self.owner.pet_id}/photo-requests")

    def test_a_finished_photo_shows_up_with_its_image(self) -> None:
        """正常路径：画好之后刷新页面，能看到 ready ＋ 图片地址 ＋ 首次那一刻的拍摄时刻。"""
        accepted = self.ask("home").json()
        self.web.illustrations.run_pending()

        listed = self.photos()

        self.assertEqual(listed.status_code, 200, listed.text)
        items = listed.json()
        self.assertEqual(len(items), 1)
        one = items[0]
        self.assertEqual(one["request_id"], accepted["request_id"], "受理时给的标识要能用来找回这条")
        self.assertEqual(one["photo_status"], "ready")
        self.assertEqual(one["image_url"], f"/api/v1/web/media/illustrations/{one['request_id']}")
        self.assertFalse(one["can_retry"], "画好了就不该给重画入口")
        self.assertEqual(one["captured_at"], accepted["captured_at"], "拍摄时刻来自首次登记")
        self.assertEqual((one["scene"], one["fictional"]), ("home", False))
        self.assertEqual(self.owner.client.get(one["image_url"]).status_code, 200, "图片真的拿得到")  # image_url 已含前缀

    def test_an_unconfirmed_result_is_distinguishable_from_a_failure(self) -> None:
        """**unknown 必须可辨**：超时那次不能显示成「没画成」，而且要给重画入口。"""
        self.illustrator.fail_reason = "timeout"
        self.ask("home")
        self.web.illustrations.run_pending()
        self.illustrator.fail_reason = None

        one = self.photos().json()[0]

        self.assertEqual(one["photo_status"], "unknown", "结果没确认就要说没确认，不能写成 failed")
        self.assertIsNone(one["image_url"])
        self.assertTrue(one["can_retry"], "没确认的要能重画")

    def test_reading_the_list_never_starts_a_call(self) -> None:
        """**读查询不驱动任何东西**：连读三次，替身一次都不该被调用，状态也不许自己变。"""
        self.illustrator.fail_reason = "daily_cap"
        self.ask("home")
        self.web.illustrations.run_pending()
        self.illustrator.fail_reason = None
        calls_before = len(self.illustrator.prompts)
        first = self.photos().json()[0]

        for _ in range(3):
            self.photos()

        self.assertEqual(len(self.illustrator.prompts), calls_before, "读列表不许发起任何调用")
        self.assertEqual(self.photos().json()[0]["photo_status"], first["photo_status"], "读几次状态都一样")

    def test_an_outsider_cannot_read_the_photo_list(self) -> None:
        stranger = self.user("photo-cmd-stranger3")
        stranger.adopt_and_move_in("adopt-yunduo")
        self.ask("home")

        response = self.photos(who=stranger, pet_id=self.owner.pet_id)

        self.assertEqual(response.status_code, 404, "不是这家的人，连存不存在都不告诉")

    def test_retrying_a_failed_photo_requeues_it_once(self) -> None:
        """没画成的可以重画；**已经画好的再点是 200 ＋ 当前状态，不是 404，也不许再发一次调用**。"""
        self.illustrator.fail_reason = "daily_cap"
        accepted = self.ask("home").json()
        self.web.illustrations.run_pending()
        self.illustrator.fail_reason = None
        self.assertEqual(self.photos().json()[0]["photo_status"], "failed")

        again = self.owner.post(f"/pets/{self.owner.pet_id}/photo-requests/{accepted['request_id']}/retry-image")

        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json()[0]["photo_status"], "processing", "重画之后回到正在画")
        self.web.illustrations.run_pending()
        calls_after_redraw = len(self.illustrator.prompts)
        ready_again = self.owner.post(f"/pets/{self.owner.pet_id}/photo-requests/{accepted['request_id']}/retry-image")
        self.assertEqual(ready_again.status_code, 200, "已经画好的再点也是 200，不是 404")
        self.web.illustrations.run_pending()
        self.assertEqual(len(self.illustrator.prompts), calls_after_redraw, "已经画好的重画不许再发一次调用")

    def test_retrying_something_that_is_not_ours_is_404(self) -> None:
        response = self.owner.post(f"/pets/{self.owner.pet_id}/photo-requests/il-nonexistent/retry-image")

        self.assertEqual(response.status_code, 404, response.text)



if __name__ == "__main__":
    unittest.main()
