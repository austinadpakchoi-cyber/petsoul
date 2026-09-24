"""证件照（CR-6C2B-IDPHOTO）整链：**真实装配 ＋ 假供应商**，不联网、**0 次付费调用**。

用户 2026-09-24 定：新宠物**自动生成、默认开**；存量**不批量补**（只有主人点重画才生成；眼下没有换照片的入口）。
这里钉的是链路本身——上传与领取、两条路线、没照片的宠物复用基准照、领养、重画、认领、额度车道、纯读。
各道门（自动只排一次、开关只管自动、物种、没确认的调用、发布前复核、新旧轮次）在 `test_web_id_photo_gates.py`，
装置在 `id_photo_chain_base.py`；纯函数（提示词、5 条校验、合成与裁切）在 `test_web_id_photo_images.py`。
"""

from __future__ import annotations

import unittest
from unittest import mock

from character_fakes import transparent_png
from id_photo_chain_base import FLAT, HEAD, IdPhotoChainBase
from web_base import PREFIX, tiny_png

from app.schemas.web.common import WebErrorCode
from app.web_character import ImageWorkPump, prompts, raster, validate
from app.web_character.id_photo import BACKDROP


class IdPhotoChainTests(IdPhotoChainBase):
    # ---- ① 上传即登记，同一事务；角色的泵不领它 ----
    def test_an_upload_queues_one_id_photo_and_reading_never_draws(self) -> None:
        self.assertEqual([row["state"] for row in self.rows()], ["queued"], "上传成功的同一事务里登记了一张")
        self.assertEqual(len(self.tasks()), 1)
        for _ in range(3):
            self.assertEqual(self.state()["status"], "queued", "读多少次都只是读")
        self.assertEqual(self.illustrator.id_calls, [], "看页面、刷新不触发生成")

    def test_the_character_worker_leaves_id_photos_to_the_pump(self) -> None:
        """`character.run_pending` 只领角色任务（Q 的合同与角色用例都靠这一点）；证件照由生图泵顺带领取。"""
        self.web.character.run_pending(limit=10)
        self.assertEqual(self.illustrator.id_calls, [], "角色的泵不领证件照")
        self.assertEqual(self.rows()[0]["state"], "queued")

        ImageWorkPump(self.web.illustrations, self.web.character).run_pending()

        self.assertEqual(len(self.illustrator.id_calls), 1, "生图泵照 `pumped_with` 顺带领了它")
        self.assertEqual(self.rows()[0]["state"], "ready")

    # ---- ② 透明路线：合成到界面常量 ----
    def test_the_transparent_route_composites_onto_the_ui_backdrop(self) -> None:
        self.draw()

        call = self.illustrator.id_calls[0]
        self.assertEqual((call["background"], call["size"]), ("transparent", "1024x1536"))
        self.assertEqual(call["prompt"], prompts.build_id_photo_prompt("cat"), "提示词里没有底色词")
        self.assertEqual(call["reference"], self.web.character.reference_photo_of(self.pet_id), "参考是主人原照")
        row = self.rows()[0]
        self.assertEqual((row["state"], row["backdrop"], row["width"], row["height"]), ("ready", "#DCE8F2", 96, 128))
        photo = (self.web.character.root / row["rel_path"]).read_bytes()
        self.assertEqual(validate._header(photo)[3], 2, "证件用图是 8 位真彩，没有 alpha")
        self.assertEqual(tuple(raster.decode(photo)[2][0:3]), BACKDROP, "透明处合成的是界面底色，分毫不差")
        self.assertEqual((self.web.character.root / row["source_rel_path"]).read_bytes(), HEAD, "透明原图私下保留：换底色不用重画")
        body = self.state()
        self.assertEqual((body["status"], body["source"]), ("ready", "generated"))
        self.assertEqual(self.owner.get(body["url"].removeprefix("/api/v1/web")).status_code, 200)
        self.assertEqual(self.owner.get(body["avatar_url"].removeprefix("/api/v1/web")).status_code, 200)
        stranger = self.user("id-stranger")
        self.assertEqual(stranger.get(body["url"].removeprefix("/api/v1/web")).status_code, 404, "越权读挡下")
        self.assertEqual(stranger.get(body["avatar_url"].removeprefix("/api/v1/web")).status_code, 404, "头像同样挡下")
        self.assertEqual(self.id_photo.avatar_url_of(self.pet_id), body["avatar_url"])

    def test_a_full_body_picture_is_refused_and_not_retried(self) -> None:
        """拍成了全身（四边留空）：胸口没到底，按 §4.2 不发布；校验不过不自动重画——再画一次就是再花一次钱。"""
        self.illustrator.photo = transparent_png(96, 144)
        self.draw()
        self.clock.advance(minutes=10)  # 过了重试延迟：要是判成可重试，这一轮就会再画
        self.draw()

        self.assertEqual(len(self.illustrator.id_calls), 1)
        # 光数付费次数挡不住"判成可重试"：重试时成功结果恢复找不到小票（校验没过就不写），会拦下、不重发。
        # 所以直接看任务：判成不可重试＝只领过一次、当场落定，没有排第二轮
        task = self.tasks()[0]
        self.assertEqual((task["status"], task["attempts"]), ("failed", 1))
        self.assertEqual(self.state()["status"], "failed")
        self.assertEqual(self.state()["reason"], validate.PHOTO_NOT_TO_BOTTOM)

    # ---- ③ 不透明备选路线 ----
    def test_the_opaque_route_when_the_adapter_cannot_ask_for_transparency(self) -> None:
        self.web.character.transparency_requested = False
        self.illustrator.photo = FLAT
        self.draw()

        call = self.illustrator.id_calls[0]
        self.assertIsNone(call["background"])
        self.assertEqual(call["prompt"], prompts.build_id_photo_prompt("cat", opaque=True))
        row = self.rows()[0]
        self.assertEqual((row["state"], row["backdrop"], row["width"], row["height"]), ("ready", None, 512, 682))

    # ---- ④ 没照片的宠物：复用基准照，不另付费 ----
    def test_a_pet_without_a_photo_reuses_its_companion_portrait(self) -> None:
        created = self.owner.upload_pet("小灰", "cat", photo=None, household_id=self.household_id)
        pet_id = created.json()["pet_id"]
        self.assertEqual(self.rows(pet_id), [], "没照片：不排任务、不付费")
        self.assertIsNone(self.state(pet_id), "基准照画出来之前是 absent，前端退回原照或占位")

        self.web.pets.set_portrait(pet_id, tiny_png(), "image/png")  # 插画链路第一次给它画照片时存下的基准证件照

        body = self.state(pet_id)
        self.assertEqual((body["status"], body["source"], body["url"]), ("ready", "companion_portrait", f"/api/v1/web/media/pets/{pet_id}/photo"))
        self.assertIsNone(body["avatar_url"], "它不是服务端裁好的头像：给 null，不拿整图冒充")
        self.assertIsNone(self.id_photo.avatar_url_of(pet_id))
        self.assertFalse(self.id_photo.regenerate(pet_id, self.owner.user_id)[0], "点重画也不另付费：基准照就是它的证件照")
        self.assertEqual(self.rows(pet_id), [])
        self.assertEqual(self.illustrator.id_calls, [])

    # ---- ⑤ 领养：同一事务里登记证件照（只管证件照） ----
    def test_adopting_a_resident_with_an_archive_photo_queues_its_id_photo(self) -> None:
        pet_id = self.resident_with_archive_photo()
        with self.app.state.storage.connect() as conn:
            self.assertIsNone(self.id_photo.request_in(conn, pet_id, self.owner.user_id), "还在驿站、没有家：不排")

        response = self.owner.post("/adoption/adopt", {"candidate_id": f"cand-{pet_id}", "household_id": self.household_id})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([row["state"] for row in self.rows(pet_id)], ["queued"])
        self.assertEqual(self.query("SELECT COUNT(*) AS n FROM web_pet_characters WHERE pet_id = ?", (pet_id,))[0]["n"], 0,
                         "角色的触发范围不变：领养不排角色")

    # ---- ⑥ 重画：显式、新一轮；在建时拒绝；旧的照常显示 ----
    def test_regenerate_is_refused_while_one_is_pending_and_keeps_the_old_one_visible(self) -> None:
        self.assertEqual(self.id_photo.regenerate(self.pet_id, self.owner.user_id)[2], "already_queued")
        self.draw()
        first = self.state()

        accepted, _, task_id = self.id_photo.regenerate(self.pet_id, self.owner.user_id)

        self.assertTrue(accepted)
        self.assertEqual(self.state()["url"], first["url"], "新一轮在画：旧的照常显示，证件上不会忽然没了照片")
        self.assertEqual(self.id_photo.regenerate(self.pet_id, self.owner.user_id)[2], "already_queued", "连点不会多排一轮")
        self.draw()
        self.assertEqual(self.state()["revision"], first["revision"] + 1)
        self.assertEqual(len(self.illustrator.id_calls), 2)

    def test_the_regenerate_route_needs_an_idempotency_key(self) -> None:
        response = self.owner.post(f"/pets/{self.pet_id}/id-photo/regenerate", {}, key="id-redo-1")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["reason"], "already_queued", "上传时那一张还在排")
        bare = self.owner.client.post(f"{PREFIX}/pets/{self.pet_id}/id-photo/regenerate", json={},
                                      headers={"X-CSRF-Token": self.owner.csrf})
        self.assertEqual((bare.status_code, bare.json()["error"]["code"]),
                         (400, WebErrorCode.idempotency_key_required.value), "不带幂等键：挡下，不排也不读")

    # ---- ⑦ 换了原照：旧的作废；额度走自己的车道；付费成功没写进去就认领 ----
    def test_a_changed_owner_photo_voids_the_pending_id_photo(self) -> None:
        with self.app.state.storage.connect() as conn:
            conn.execute("UPDATE web_pet_profiles SET photo_ref = ? WHERE pet_id = ?", ("pets/x/swapped.png", self.pet_id))
        self.draw()
        self.assertEqual(self.illustrator.id_calls, [], "0 次发送")
        self.assertEqual((self.rows()[0]["state"], self.rows()[0]["reason"]), ("failed", "reference_changed"))

    def test_budget_goes_to_its_own_lane(self) -> None:
        self.draw()
        row = self.query("SELECT purpose, subject_scope, status, outcome FROM web_budget_reservations WHERE operation_id LIKE ?",
                         (f"id_photo:{self.rows()[0]['task_id']}:%",))
        self.assertEqual([tuple(r) for r in row], [("id_photo", f"pet:{self.pet_id}", "settled", "succeeded")])
        used = {r["scope_key"] for r in self.query("SELECT scope_key FROM web_budget_counters WHERE used_units > 0")}
        self.assertIn(f"pet:{self.pet_id}:id_photo", used)
        self.assertNotIn(f"pet:{self.pet_id}:character", used, "没占角色车道：不打乱「每宠 12 ＝ 一天两套」")

    def test_a_paid_id_photo_that_failed_to_publish_is_reclaimed(self) -> None:
        real, count = self.id_photo._publish_in, []

        def flaky(conn, task, rendered):
            count.append(1)
            if len(count) == 1:
                raise RuntimeError("写入失败（测试注入）")
            return real(conn, task, rendered)

        with mock.patch.object(self.id_photo, "_publish_in", flaky):
            self.id_photo.run_pending(limit=1)
            self.assertEqual(len(self.illustrator.id_calls), 1, "前提：第一次真的调了")
            self.assertNotEqual(self.rows()[0]["state"], "ready", "前提：结果确实没写进去")
            self.clock.advance(minutes=10)
            self.id_photo.run_pending(limit=1)

        self.assertEqual(len(self.illustrator.id_calls), 1, "重试没有再付一次")
        self.assertEqual(self.rows()[0]["state"], "ready")
        self.assertTrue(self.rows()[0]["source_rel_path"].endswith("-1.png"), "认领的是第一次那张")


if __name__ == "__main__":
    unittest.main()
