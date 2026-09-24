"""证件照（CR-6C2B-IDPHOTO）的各道门：**真实装配 ＋ 假供应商**，不联网、**0 次付费调用**。

每条用例钉一道门，并各自做过内存变异（把那道门拆掉，这条用例必须红）：
自动只排一次、开关只管自动、物种、没确认的调用说 `unknown` 且不重发、发布前复核原照、新旧轮次不倒挂。
后两条是**不变量**：眼下没有换照片的入口、在建时也不许重画，所以生产里走不到——钉住它们，是为了将来加入口时不静默失效。
链路本身在 `test_web_id_photo.py`，装置在 `id_photo_chain_base.py`。
"""

from __future__ import annotations

import unittest
from unittest import mock

from id_photo_chain_base import HEAD, IdPhotoChainBase
from web_base import tiny_png

from app.image_provider.models import GeneratedImage


class IdPhotoGateTests(IdPhotoChainBase):
    def test_the_same_photo_is_never_queued_twice_automatically(self) -> None:
        """同一张参考照已有在排或已生效的：自动触发给回那一轮，不另排——**多排就是多花一次钱**。"""
        first = self.rows()[0]["task_id"]
        with self.app.state.storage.connect() as conn:
            self.assertEqual(self.id_photo.request_in(conn, self.pet_id, self.owner.user_id), first, "在排")
        self.draw()
        with self.app.state.storage.connect() as conn:
            self.assertEqual(self.id_photo.request_in(conn, self.pet_id, self.owner.user_id), first, "已生效")
        self.assertEqual((len(self.rows()), len(self.tasks()), len(self.illustrator.id_calls)), (1, 1, 1))

    def test_switching_auto_off_stops_new_pets_but_not_an_explicit_redraw(self) -> None:
        """开关只管**自动**（用户定：默认开）；关掉以后主人点重画照样能画——那是主人自己要的。"""
        self.assertTrue(self.id_photo.auto, "默认开：装配时 config 没有这个字段就是开")
        self.id_photo.auto = False
        created = self.owner.upload_pet("小关", "cat", photo=tiny_png(), household_id=self.household_id)
        pet_id = created.json()["pet_id"]
        self.assertEqual(self.rows(pet_id), [], "关着：上传不排")

        accepted, status, _ = self.id_photo.regenerate(pet_id, self.owner.user_id)

        self.assertEqual((accepted, status), (True, "queued"))
        self.assertEqual([row["state"] for row in self.rows(pet_id)], ["queued"])

    def test_a_species_without_a_face_rule_gets_none(self) -> None:
        """规范只给六种动物写了取景；`other` 不排、不付费，状态是 absent（前端退回原照）。"""
        created = self.owner.upload_pet("小怪", "other", photo=tiny_png(), household_id=self.household_id)
        pet_id = created.json()["pet_id"]
        self.assertEqual(self.rows(pet_id), [])
        self.assertIsNone(self.state(pet_id))

    def test_an_unconfirmed_call_reads_unknown_and_is_never_resent(self) -> None:
        """发出去以后进程断了（预占停在 reserved）：重试**不重发**，状态说 `unknown`——说成没画成会让主人再付一次。"""
        real = self.illustrator.render

        def dies_after_sending(prompt, reference=None, size="2048x2048", background=None):
            real(prompt, reference, size=size, background=background)
            raise RuntimeError("发出后进程中断（测试注入）")

        with mock.patch.object(self.illustrator, "render", dies_after_sending):
            self.id_photo.run_pending(limit=1)
        self.assertEqual(len(self.illustrator.id_calls), 1, "前提：第一次真的发出了")
        self.clock.advance(minutes=10)
        self.id_photo.run_pending(limit=1)

        self.assertEqual(len(self.illustrator.id_calls), 1, "没有再发一次")
        self.assertEqual((self.rows()[0]["state"], self.state()["status"]), ("failed", "unknown"))

    def test_a_photo_swapped_during_the_call_is_not_published(self) -> None:
        """不变量（眼下没有换照片的入口）：付费调用期间原照换了，发布前的最终复核挡下，旧照片的证件照不挂上去。"""
        real = self.illustrator.render

        def swap_during_call(prompt, reference=None, size="2048x2048", background=None):
            with self.app.state.storage.connect() as conn:
                conn.execute("UPDATE web_pet_profiles SET photo_ref = ? WHERE pet_id = ?", ("pets/x/swapped.png", self.pet_id))
            return real(prompt, reference, size=size, background=background)

        with mock.patch.object(self.illustrator, "render", swap_during_call):
            self.draw()

        self.assertEqual(len(self.illustrator.id_calls), 1, "前提：确实发出并拿到了图")
        self.assertEqual((self.rows()[0]["state"], self.rows()[0]["reason"]), ("failed", "reference_changed"))
        self.assertEqual(self.query("SELECT COUNT(*) AS n FROM web_pet_id_photo_active")[0]["n"], 0)

    def test_an_older_round_never_replaces_a_newer_one(self) -> None:
        """不变量（在建时拒绝重画，眼下不会乱序）：切生效只认 revision 更大的，晚到的旧一轮换不下新的。"""
        self.draw()
        old = self.rows()[0]
        self.id_photo.regenerate(self.pet_id, self.owner.user_id)
        self.draw()
        newer = self.state()
        self.assertEqual(newer["revision"], old["revision"] + 1, "前提：新一轮已生效")
        task = mock.Mock(task_id=old["task_id"], payload={"pet_id": self.pet_id, "asset_id": old["asset_id"],
                                                          "reference_key": old["reference_key"], "revision": old["revision"]})
        photo = (self.web.character.root / old["rel_path"]).read_bytes()
        image = GeneratedImage(image_bytes=HEAD, mime_type="image/png", model="fake-id", provider="fake", source="b64")
        rendered = ((old["source_rel_path"], old["rel_path"], old["avatar_rel_path"], old["backdrop"],
                     old["width"], old["height"], photo), image)

        with self.app.state.storage.connect() as conn:
            self.id_photo._publish_in(conn, task, rendered)

        self.assertEqual((self.state()["revision"], self.state()["url"]), (newer["revision"], newer["url"]))


if __name__ == "__main__":
    unittest.main()
