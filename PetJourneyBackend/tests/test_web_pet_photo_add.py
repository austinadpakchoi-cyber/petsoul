"""补照片 `PUT /pets/{pet_id}/photo`（6c2b 2026-09-24 巡检 P1：入住时写着「照片可以以后再补」，后端却没有补的接口）。

范围按 6c2b 收窄后的定稿：**只补不换**。
  · 只有这只宠物的照顾者能补；私有存储、剥离元数据（与建宠物同一条路径）；
  · 已有照片回 409 `photo_exists`——**包括没照片时生成的那张形象照**（换掉它就是「替换」，要等用户拍板），details.generated 说明是哪种；
  · 领养的伙伴回 409 `not_own_pet`（有自己设定的样子）；
  · **上传本身不触发任何生图**：不登记形象、不登记证件照（补照片要不要自动生成，等用户拍板）；
  · 同一个幂等键重放不重复存；两个请求并发补，只有一个成功。
"""

from __future__ import annotations

import unittest
import uuid

from web_base import PREFIX, WebPlatformTestBase, tiny_png
from web_provider_fakes import FakeIllustrator


class AddPetPhotoTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = self.user("photo-later")
        self.pet_id = self.owner.upload_pet("年糕", "cat").json()["pet_id"]  # 入住时没带照片
        self.owner.move_in()

    def put_photo(self, user=None, pet_id=None, data=None, key=None):
        user = user or self.owner
        return user.client.put(f"{PREFIX}/pets/{pet_id or self.pet_id}/photo", files={"photo": ("pet.png", data or tiny_png(), "image/png")},
                               headers={"X-CSRF-Token": user.csrf, "Idempotency-Key": key or f"t-{uuid.uuid4().hex[:16]}"})

    def profile_row(self, pet_id=None):
        with self.app.state.storage.connect() as conn:
            return conn.execute("SELECT photo_ref, photo_generated FROM web_pet_profiles WHERE pet_id = ?", (pet_id or self.pet_id,)).fetchone()

    def tasks(self) -> int:
        with self.app.state.storage.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM web_tasks").fetchone()[0]

    def test_a_photo_can_be_added_once_and_is_stored_privately_without_metadata(self) -> None:
        self.assertIsNone(self.profile_row()["photo_ref"], "前提：入住时没带照片")
        response = self.put_photo(data=tiny_png(with_text_chunk=True))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["photo_url"], "摘要里马上看得到照片")
        row = self.profile_row()
        self.assertEqual((row["photo_generated"], row["photo_ref"].startswith("pets/")), (0, True), "主人的真实照片、私有存储")
        path, _ = self.web.pets.photo_path(self.pet_id)
        self.assertNotIn(b"tEXt", path.read_bytes(), "元数据块剥掉了")
        self.assertEqual(self.owner.get(f"/media/pets/{self.pet_id}/photo").status_code, 200, "照顾者读得到")

    def test_adding_a_photo_does_not_start_any_image_generation(self) -> None:
        """装上（假的）画师，并先做正向对照：同一环境里带照片新建一只，任务数确实会涨——证明钩子一旦被调就会排上。
        没有这一步，「任务数不变」在没有生图服务的测试环境里恒真（变异实测：偷偷调钩子也照样绿）。"""
        self.web.character.illustrator = FakeIllustrator()
        household_id = self.owner.get("/onboarding").json()["households"][0]["household_id"]
        before_control = self.tasks()
        self.assertEqual(self.owner.upload_pet("对照", "cat", photo=tiny_png(), household_id=household_id).status_code, 201)
        self.assertGreater(self.tasks(), before_control, "对照：建宠物带照片时会自动登记形象与证件照")
        hooked: list = []
        original = self.web.pets.on_pet_photo_stored
        self.web.pets.on_pet_photo_stored = lambda *args: hooked.append(args) or original(*args)
        before = self.tasks()
        self.assertEqual(self.put_photo().status_code, 200)
        self.assertEqual((self.tasks(), hooked), (before, []), "补照片不登记形象、不登记证件照：要不要自动生成，等用户拍板")

    def test_an_existing_photo_is_not_replaced(self) -> None:
        self.assertEqual(self.put_photo().status_code, 200)
        first = self.profile_row()["photo_ref"]
        again = self.put_photo()
        self.assertEqual(again.status_code, 409, again.text)
        self.assertEqual(again.json()["error"]["details"], {"reason": "photo_exists", "generated": False})
        self.assertEqual(self.profile_row()["photo_ref"], first, "原来那张一个字节都没换")

    def test_a_generated_portrait_counts_as_an_existing_photo(self) -> None:
        self.assertTrue(self.web.pets.set_portrait(self.pet_id, tiny_png(with_text_chunk=False), "image/png"), "前提：没照片时生成过形象照")
        response = self.put_photo()
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["error"]["details"], {"reason": "photo_exists", "generated": True}, "换掉生成的形象照也是替换")

    def test_adopted_companions_keep_their_own_look(self) -> None:
        adopter = self.user("photo-adopter")
        adopter.adopt_and_move_in("adopt-lan")
        response = self.put_photo(user=adopter, pet_id=adopter.pet_id)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["error"]["details"]["reason"], "not_own_pet")

    def test_only_a_caregiver_can_add_it(self) -> None:
        stranger = self.user("photo-stranger")
        response = self.put_photo(user=stranger)
        self.assertIn(response.status_code, (403, 404), response.text)
        self.assertIsNone(self.profile_row()["photo_ref"])

    def test_the_same_key_replays_without_storing_twice(self) -> None:
        first = self.put_photo(key="t-photo-replay-001")
        again = self.put_photo(key="t-photo-replay-001")
        self.assertEqual((first.status_code, again.status_code), (200, 200))
        self.assertEqual(first.json(), again.json(), "同一个幂等键：原样重放")
        folder = self.web.pets.photo_path(self.pet_id)[0].parent
        self.assertEqual(len(list(folder.iterdir())), 1, "只存了一份文件")

    def test_when_two_requests_race_the_loser_gets_photo_exists_and_leaves_no_file(self) -> None:
        """在它存文件的那一刻，另一个请求抢先写进了照片：条件更新落空，回 photo_exists，并删掉自己刚存的那份文件。"""
        import app.web_pets.service as service
        from app.web_pets import PhotoNotAddable
        real_store, stored = service.store_private, []

        def racing_store(root, owner_id, data, content_type):
            with self.app.state.storage.connect() as conn:  # 另一个请求先提交了
                conn.execute("UPDATE web_pet_profiles SET photo_ref = 'pets/winner/first.png' WHERE pet_id = ?", (self.pet_id,))
            ref = real_store(root, owner_id, data, content_type)
            stored.append(ref)
            return ref

        service.store_private = racing_store
        try:
            with self.assertRaises(PhotoNotAddable) as refused:
                self.web.pets.add_photo(self.pet_id, tiny_png())
        finally:
            service.store_private = real_store
        self.assertEqual(refused.exception.reason, "photo_exists")
        self.assertEqual(self.profile_row()["photo_ref"], "pets/winner/first.png", "先到的那张留着")
        self.assertFalse((self.web.pets.media_root / stored[0]).exists(), "后到的那份文件删掉了，不留孤儿文件")

    def test_an_unusable_image_is_rejected(self) -> None:
        response = self.put_photo(data=b"not an image at all")
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["error"]["code"], "MEDIA_REJECTED")
        self.assertIsNone(self.profile_row()["photo_ref"])


if __name__ == "__main__":
    unittest.main()
