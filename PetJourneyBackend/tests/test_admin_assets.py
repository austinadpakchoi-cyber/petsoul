"""运营素材库：原件、缩略图、来源、使用范围、哈希，以及那条硬规则。

最重要的一条：**玩家的宠物参考照不能被收进公共素材库**。这里用真实的上传流程验证——
先让玩家上传一张参考照，再把**同一份文件**当素材上传，必须被按哈希挡下并留 denied 审计。
"""

from __future__ import annotations

import hashlib
import importlib.util
import struct
import sys
import unittest
import zlib
from unittest import mock

from admin_base import AdminTestBase
from web_base import PREFIX, tiny_png

PILLOW_INSTALLED = importlib.util.find_spec("PIL") is not None


def png_bytes(red: int, green: int, blue: int) -> bytes:
    """一张 1x1 的纯色 PNG。换颜色就是换文件，用来造"确实不是同一张图"的素材。"""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    body = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    body += chunk(b"IDAT", zlib.compress(bytes([0, red, green, blue])))
    body += chunk(b"IEND", b"")
    return bytes([0x89]) + b"PNG" + bytes([13, 10, 26, 10]) + body


class AssetLibraryTests(AdminTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.editor = self.staff("asset-editor", ["content_editor"])
        self.editor.login_ok()

    def upload(self, data: bytes, *, scope: str = "public", source: str = "own_work",
               note: str = "本批运营自制的插图", name: str = "banner.png", key: str | None = None):
        return self.editor.upload("/assets", files={"file": (name, data, "image/png")},
                                  data={"source": source, "source_note": note, "usage_scope": scope}, key=key)

    # ---- 基本入库 ----
    def test_upload_records_original_thumbnail_source_scope_and_hash(self):
        data = png_bytes(10, 20, 30)
        response = self.upload(data)
        self.assertEqual(response.status_code, 201, response.text)
        asset = response.json()["asset"]
        self.assertEqual(asset["source"], "own_work")
        self.assertEqual(asset["usage_scope"], "public")
        self.assertEqual(asset["status"], "active")
        self.assertEqual(asset["sha256"], hashlib.sha256(data).hexdigest(), "哈希按清洗后的原件算；这张图没有要剥的元数据")
        self.assertEqual(asset["byte_size"], len(data))
        # 尺寸与缩略图都靠 Pillow。它不在 requirements.txt 里：按那份文件装出来的干净环境（2026-09-23 的
        # Linux 容器实测）就没有它。所以这里按环境分两种断言，而不是把"装了 Pillow"当成前提。
        if PILLOW_INSTALLED:
            self.assertEqual((asset["width"], asset["height"]), (1, 1))
            self.assertTrue(asset["has_thumbnail"], asset)
        else:
            self.assertEqual((asset["width"], asset["height"]), (None, None), "量不出来就是空，不猜")
            self.assertFalse(asset["has_thumbnail"])
            self.assertIn("Pillow", asset["thumb_note"])

        detail = self.editor.get(f"/assets/{asset['asset_id']}")
        self.assertEqual(detail.status_code, 200, detail.text)
        original = self.editor.get(f"/assets/{asset['asset_id']}/file")
        self.assertEqual(original.status_code, 200)
        self.assertEqual(original.content, data)
        if asset["has_thumbnail"]:
            thumb = self.editor.get(f"/assets/{asset['asset_id']}/file?thumb=true")
            self.assertEqual(thumb.status_code, 200)
            self.assertTrue(thumb.content)

    def test_without_pillow_the_upload_still_lands_and_says_what_is_missing(self):
        """强制走"没有 Pillow"那条路：装着 Pillow 的机器上它本来一次都不会被执行。"""
        data = png_bytes(40, 50, 60)
        with mock.patch.dict(sys.modules, {"PIL": None, "PIL.Image": None}):
            response = self.upload(data, name="no-pillow.png")
        self.assertEqual(response.status_code, 201, response.text)
        asset = response.json()["asset"]
        self.assertFalse(asset["has_thumbnail"])
        self.assertIn("Pillow", asset["thumb_note"])
        self.assertEqual((asset["width"], asset["height"]), (None, None))
        self.assertEqual(asset["sha256"], hashlib.sha256(data).hexdigest(), "原件与哈希照常记录")
        self.assertEqual(self.editor.get(f"/assets/{asset['asset_id']}/file").content, data)
        self.assert_admin_error(self.editor.get(f"/assets/{asset['asset_id']}/file?thumb=true"), 404, "NOT_FOUND")

    def test_source_and_scope_are_required_and_checked(self):
        data = png_bytes(1, 2, 3)
        self.assertEqual(self.upload(data, source="whatever").status_code, 422)
        self.assertEqual(self.upload(data, scope="everyone").status_code, 422)
        self.assertEqual(self.upload(data, note="x").status_code, 422)  # 来源说明太短

    def test_non_image_and_duplicate_are_rejected(self):
        bad = self.editor.upload("/assets", files={"file": ("notes.txt", b"just text", "text/plain")},
                                 data={"source": "own_work", "source_note": "试一个非图片", "usage_scope": "public"})
        self.assertEqual(bad.status_code, 422, bad.text)
        self.assertIn("JPEG", bad.json()["error"]["message"])

        data = png_bytes(7, 7, 7)
        self.assertEqual(self.upload(data).status_code, 201)
        again = self.upload(data, name="same-again.png")
        self.assert_admin_error(again, 409, "CONFLICT")

    def test_upload_needs_permission(self):
        support = self.staff("asset-support", ["support"])
        support.login_ok()
        response = support.upload("/assets", files={"file": ("x.png", png_bytes(5, 5, 5), "image/png")},
                                  data={"source": "own_work", "source_note": "越权上传", "usage_scope": "public"})
        self.assert_admin_error(response, 403, "FORBIDDEN")

    # ---- 硬规则：玩家参考照进不来 ----
    def test_owner_reference_photo_cannot_become_a_public_asset(self):
        owner = self.user("photo-owner")
        created = owner.upload_pet("小满", photo=tiny_png())
        self.assertEqual(created.status_code, 201, created.text)

        # 取玩家参考照在磁盘上的那一份，原样当素材上传
        with self.app.state.storage.connect() as conn:
            row = conn.execute("SELECT pet_id, photo_ref FROM web_pet_profiles WHERE user_id = ?", (owner.user_id,)).fetchone()
        stored = (self.settings.web_private_media_dir / row["photo_ref"]).read_bytes()

        response = self.upload(stored, name="looks-nice.png")
        error = self.assert_admin_error(response, 403, "FORBIDDEN")
        self.assertEqual(error["details"]["reason"], "owner_reference_photo")
        self.assertEqual(error["details"]["pet_id"], row["pet_id"])

        with self.app.state.storage.connect() as conn:
            count = conn.execute("SELECT COUNT(*) AS n FROM admin_assets").fetchone()["n"]
        self.assertEqual(count, 0, "被挡下的上传不能留下素材行")

        owner_staff = self.owner()
        denied = [e for e in owner_staff.get("/audit?action=asset.upload").json()["entries"] if e["status"] == "denied"]
        self.assertTrue(denied, "被挡下的这次要留痕")
        self.assertEqual(denied[0]["outcome"], "owner_reference_photo")

    def test_the_raw_upload_of_a_reference_photo_is_also_caught(self):
        """玩家上传时会被剥元数据，所以磁盘上的那份与玩家原文件不同字节；两份都要比。"""
        owner = self.user("photo-owner-2")
        raw = tiny_png(with_text_chunk=True)
        self.assertEqual(owner.upload_pet("小雪", photo=raw).status_code, 201)
        response = self.upload(raw, name="raw-copy.png")
        self.assert_admin_error(response, 403, "FORBIDDEN")

    # ---- 玩家侧消费 ----
    def test_public_assets_are_served_to_anyone_and_internal_ones_are_not(self):
        public = self.upload(png_bytes(9, 1, 1)).json()["asset"]
        internal = self.upload(png_bytes(1, 9, 1), scope="internal", name="internal.png").json()["asset"]

        served = self.client.get(f"{PREFIX}/assets/{public['asset_id']}")
        self.assertEqual(served.status_code, 200, served.text)
        self.assertEqual(served.headers["content-type"], "image/png")

        hidden = self.client.get(f"{PREFIX}/assets/{internal['asset_id']}")
        self.assertEqual(hidden.status_code, 404, "内部素材对玩家一律当不存在")
        self.assertEqual(self.client.get(f"{PREFIX}/assets/AS-0000000000000000").status_code, 404)
        # 员工带权限时照常能取内部素材
        self.assertEqual(self.editor.get(f"/assets/{internal['asset_id']}/file").status_code, 200)

    def test_announcement_can_carry_a_public_asset_and_players_get_the_url(self):
        asset = self.upload(png_bytes(3, 3, 9)).json()["asset"]
        publisher = self.staff("asset-publisher", ["content_publisher"])
        publisher.login_ok()
        body = {"title": "海边咖啡馆周", "body": "这周海边咖啡馆开到晚上十点。", "severity": "notice",
                "audience": "all", "image_asset_id": asset["asset_id"]}
        created = publisher.post("/content", {"content_type": "announcement", "slug": "cafe-week",
                                              "title": body["title"], "body": body})
        self.assertEqual(created.status_code, 201, created.text)
        item = created.json()["item"]
        published = publisher.post(f"/content/{item['item_id']}/publish",
                                   {"revision": 1, "expected_version": item["version"], "reason": "配图公告上线"})
        self.assertEqual(published.status_code, 200, published.text)

        seen = self.client.get(f"{PREFIX}/announcements").json()["announcements"]
        self.assertEqual(seen[0]["image_asset_id"], asset["asset_id"])
        self.assertEqual(seen[0]["image_url"], f"/api/v1/web/assets/{asset['asset_id']}")
        self.assertEqual(self.client.get(seen[0]["image_url"]).status_code, 200)

        # 还挂在已发布公告上的素材不许下架
        latest = self.editor.get(f"/assets/{asset['asset_id']}").json()["asset"]
        blocked = self.editor.post(f"/assets/{asset['asset_id']}/retire",
                                   {"reason": "想换一张", "expected_version": latest["version"]})
        error = self.assert_admin_error(blocked, 409, "CONFLICT")
        self.assertTrue(error["details"]["used_by"], error)

    def test_internal_asset_cannot_be_published_in_an_announcement(self):
        internal = self.upload(png_bytes(2, 8, 8), scope="internal", name="draft.png").json()["asset"]
        publisher = self.staff("asset-publisher-2", ["content_publisher"])
        publisher.login_ok()
        created = publisher.post("/content", {"content_type": "announcement", "slug": "internal-pic",
                                              "title": "内部图公告",
                                              "body": {"title": "内部图公告", "body": "正文", "severity": "info",
                                                       "audience": "all", "image_asset_id": internal["asset_id"]}})
        self.assertEqual(created.status_code, 201, created.text)
        item = created.json()["item"]
        published = publisher.post(f"/content/{item['item_id']}/publish",
                                   {"revision": 1, "expected_version": item["version"], "reason": "尝试发内部图"})
        self.assertEqual(published.status_code, 422, published.text)
        issues = published.json()["error"]["details"]["issues"]
        self.assertEqual(issues[0]["field"], "image_asset_id")
        self.assertIn("内部素材", issues[0]["message"])

    def test_retired_asset_disappears_from_the_player_side(self):
        asset = self.upload(png_bytes(4, 4, 4)).json()["asset"]
        self.assertEqual(self.client.get(f"{PREFIX}/assets/{asset['asset_id']}").status_code, 200)
        retired = self.editor.post(f"/assets/{asset['asset_id']}/retire",
                                   {"reason": "版权到期，先下架", "expected_version": asset["version"]})
        self.assertEqual(retired.status_code, 200, retired.text)
        self.assertEqual(self.client.get(f"{PREFIX}/assets/{asset['asset_id']}").status_code, 404)
        with self.app.state.storage.connect() as conn:
            row = conn.execute("SELECT status, sha256, retired_reason FROM admin_assets WHERE asset_id = ?",
                               (asset["asset_id"],)).fetchone()
        self.assertEqual(row["status"], "retired")
        self.assertTrue(row["sha256"], "文件与哈希保留，作为审计依据")
        self.assertEqual(row["retired_reason"], "版权到期，先下架")

    def test_a_bad_asset_id_in_a_draft_is_caught_by_validation(self):
        publisher = self.staff("asset-publisher-3", ["content_publisher"])
        publisher.login_ok()
        check = publisher.post("/content/validate", {
            "content_type": "announcement", "slug": "bad-asset-id", "title": "x",
            "body": {"title": "t", "body": "b", "severity": "info", "audience": "all",
                     "image_asset_id": "https://example.com/pic.png"}}).json()
        self.assertFalse(check["ok"])
        self.assertEqual(check["issues"][0]["field"], "image_asset_id")


if __name__ == "__main__":
    unittest.main()
