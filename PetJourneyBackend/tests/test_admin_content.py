"""第二阶段：草稿 → 校验 → 预览 → 发布 → 撤下 → 回退，并且**玩家侧真的读到了发布的那一版**。

两种内容各走一条完整闭环：
- 公告：玩家 API `GET /api/v1/web/announcements` 按 live_revision 返回；
- 现有活动模板（咖啡馆小侦探）：发布新版本之后，**新发生**的冒险用新版本；
  已经发生过的那条消息一个字都不变——这就是"回滚不改历史"的证据。
"""

from __future__ import annotations

import unittest

from admin_base import AdminTestBase
from web_base import LUNCH_UTC, PREFIX, FakeClock
from web_provider_fakes import FakeIllustrator

ANNOUNCEMENT = {"title": "系统维护通知", "body": "本周四 02:00–04:00 星球通讯器会短暂休息。", "severity": "notice", "audience": "all"}


class AdminAnnouncementTests(AdminTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.editor = self.staff("content-editor-1", ["content_editor"])
        self.editor.login_ok()
        self.publisher = self.staff("content-publisher-1", ["content_publisher"])
        self.publisher.login_ok()
        self.player = self.user("reader-1")

    def player_sees(self, anonymous: bool = False) -> list[dict]:
        client = self.client if anonymous else self.player.client
        response = client.get(f"{PREFIX}/announcements")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["announcements"]

    def create(self, body: dict, slug: str = "maintenance-week") -> dict:
        # 请求体的 title 是给列表看的标签（必填）；body 里的 title 才是发给玩家的那一份，由内容校验负责。
        response = self.editor.post("/content", {"content_type": "announcement", "slug": slug,
                                                 "title": body["title"] or slug, "body": body})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["item"]

    def test_nothing_published_means_an_empty_list_not_a_placeholder(self):
        self.assertEqual(self.player_sees(), [])
        self.assertEqual(self.player_sees(anonymous=True), [])

    def test_validation_blocks_missing_facts_and_markup(self):
        bad = {"title": "", "body": "<script>alert(1)</script>", "severity": "urgent", "audience": "everyone"}
        check = self.editor.post("/content/validate", {"content_type": "announcement", "slug": "bad-one",
                                                       "title": "x", "body": bad}).json()
        self.assertFalse(check["ok"])
        fields = {issue["field"] for issue in check["issues"]}
        self.assertEqual(fields, {"title", "body", "severity", "audience"})

        item = self.create(bad, slug="bad-one")
        publish = self.publisher.post(f"/content/{item['item_id']}/publish",
                                      {"revision": 1, "expected_version": item["version"], "reason": "尝试发布不合格草稿"})
        self.assertEqual(publish.status_code, 422, publish.text)
        self.assertTrue(publish.json()["error"]["details"]["issues"])
        self.assertEqual(self.player_sees(), [], "校验失败不能有任何东西发出去")
        # 被拒绝的发布要留痕
        owner = self.owner()
        denied = [e for e in owner.get("/audit?action=content.publish").json()["entries"] if e["status"] == "denied"]
        self.assertTrue(denied, "被校验拦下的发布也要进审计")

    def test_full_publish_cycle_reaches_the_player(self):
        item = self.create(ANNOUNCEMENT)
        preview = self.editor.get(f"/content/{item['item_id']}/preview").json()
        self.assertTrue(preview["publishable"])
        self.assertEqual(preview["rendered"]["title"], ANNOUNCEMENT["title"])
        self.assertEqual(preview["consumer_api"], "GET /api/v1/web/announcements")
        # 新版玩家端没有首页公告栏了：入口是通讯器页顶部的细条和「全部公告」页（PetJourneyWeb/src/features/communicator）
        self.assertEqual(preview["rendered"]["consumer"], "玩家端通讯器页顶部的公告细条，以及「全部公告」页", "界面上写人话；接口路径只在技术代码里")

        published = self.publisher.post(f"/content/{item['item_id']}/publish",
                                        {"revision": 1, "expected_version": item["version"], "reason": "按维护窗口发布"})
        self.assertEqual(published.status_code, 200, published.text)
        self.assertEqual(published.json()["live_revision"], 1)

        seen = self.player_sees()
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["revision"], 1)
        self.assertEqual(seen[0]["title"], ANNOUNCEMENT["title"])
        self.assertEqual(seen[0]["body"], ANNOUNCEMENT["body"])

        # v2
        current = self.editor.get(f"/content/{item['item_id']}").json()["item"]
        v2_body = {**ANNOUNCEMENT, "title": "维护时间调整", "body": "改到本周五 02:00–03:00。"}
        saved = self.editor.put(f"/content/{item['item_id']}", {"body": v2_body, "expected_version": current["version"]})
        self.assertEqual(saved.status_code, 200, saved.text)
        v2_item = saved.json()["item"]
        self.assertEqual(v2_item["draft_revision"], 2)
        self.assertEqual(self.player_sees()[0]["revision"], 1, "只存草稿不能改变玩家看到的内容")

        published2 = self.publisher.post(f"/content/{item['item_id']}/publish",
                                         {"revision": 2, "expected_version": v2_item["version"], "reason": "维护窗口顺延"})
        self.assertEqual(published2.status_code, 200, published2.text)
        self.assertEqual(published2.json()["previous_revision"], 1)
        self.assertIn("改动字段", published2.json()["diff_summary"])
        seen2 = self.player_sees()
        self.assertEqual(seen2[0]["revision"], 2)
        self.assertEqual(seen2[0]["title"], "维护时间调整")

        # 撤下
        latest = self.editor.get(f"/content/{item['item_id']}").json()["item"]
        withdrawn = self.publisher.post(f"/content/{item['item_id']}/withdraw",
                                        {"expected_version": latest["version"], "reason": "维护取消"})
        self.assertEqual(withdrawn.status_code, 200, withdrawn.text)
        self.assertEqual(self.player_sees(), [], "撤下之后玩家立刻读不到")

        # 回退到 v1：发布的是**新版本号**，历史一条不少
        latest = self.editor.get(f"/content/{item['item_id']}").json()["item"]
        rolled = self.publisher.post(f"/content/{item['item_id']}/rollback",
                                     {"to_revision": 1, "expected_version": latest["version"], "reason": "恢复原定维护窗口"})
        self.assertEqual(rolled.status_code, 200, rolled.text)
        self.assertEqual(rolled.json()["rolled_back_from"], 1)
        self.assertEqual(rolled.json()["new_revision"], 3)
        back = self.player_sees()
        self.assertEqual(back[0]["revision"], 3, "回退是新版本号，不是回到旧号")
        self.assertEqual(back[0]["title"], ANNOUNCEMENT["title"])

        detail = self.editor.get(f"/content/{item['item_id']}").json()
        self.assertEqual([r["revision"] for r in detail["revisions"]], [3, 2, 1], "历史版本一条都不能少")
        self.assertEqual(detail["revisions"][0]["source_revision"], 1)
        actions = [p["action"] for p in detail["publications"]]
        self.assertEqual(sorted(actions), ["publish", "publish", "publish", "withdraw"])

    def test_revisions_are_immutable_and_publications_append_only(self):
        import sqlite3

        item = self.create(ANNOUNCEMENT, slug="immutable-check")
        self.publisher.post(f"/content/{item['item_id']}/publish",
                            {"revision": 1, "expected_version": item["version"], "reason": "发布以便检查不可变性"})
        with self.app.state.storage.connect() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE admin_content_revisions SET body_json = '{}'")
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE admin_content_publications SET reason = '改过了'")

    def test_audience_signed_in_is_hidden_from_visitors(self):
        item = self.create({**ANNOUNCEMENT, "audience": "signed_in"}, slug="members-only")
        self.publisher.post(f"/content/{item['item_id']}/publish",
                            {"revision": 1, "expected_version": item["version"], "reason": "只给已登录玩家"})
        self.assertEqual(self.player_sees(anonymous=True), [])
        self.assertEqual(len(self.player_sees()), 1)

    def test_editor_cannot_publish_and_publisher_change_needs_current_version(self):
        item = self.create(ANNOUNCEMENT, slug="permission-check")
        self.assert_admin_error(self.editor.post(f"/content/{item['item_id']}/publish",
                                                 {"revision": 1, "expected_version": item["version"], "reason": "越权发布"}),
                                403, "FORBIDDEN")
        self.assert_admin_error(self.publisher.post(f"/content/{item['item_id']}/publish",
                                                    {"revision": 1, "expected_version": 99, "reason": "版本冲突"}),
                                409, "VERSION_CONFLICT")

    def test_publishing_twice_with_the_same_operation_id_is_rejected(self):
        item = self.create(ANNOUNCEMENT, slug="replay-check")
        key = "publish-once-0001"
        body = {"revision": 1, "expected_version": item["version"], "reason": "重放检查"}
        first = self.publisher.post(f"/content/{item['item_id']}/publish", body, key=key)
        self.assertEqual(first.status_code, 200, first.text)
        replay = self.publisher.post(f"/content/{item['item_id']}/publish", body, key=key)
        self.assertEqual(replay.status_code, 200, replay.text)
        with self.app.state.storage.connect() as conn:
            count = conn.execute("SELECT COUNT(*) AS n FROM admin_content_publications WHERE item_id = ?",
                                 (item["item_id"],)).fetchone()["n"]
        self.assertEqual(count, 1, "同一个操作号只能留一条发布流水")


class AdminAdventureContentTests(AdminTestBase):
    """现有活动模板的发布：新发生的冒险用新版本，已经发生过的一个字都不改。"""

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.web.illustrations.illustrator = FakeIllustrator()
        self.player = self.user("adventurer")
        self.player.adopt_and_move_in("adopt-lan")
        self.publisher = self.staff("content-publisher-2", ["content_publisher"])
        self.publisher.login_ok()

    def top_up(self) -> None:
        """测试脚手架：给足旅费。走的是既有游戏账本（和后台补偿同一本账），不是直接改余额。"""
        import uuid as _uuid

        from app.schemas.base import EconomyTransactionType

        self.web.economy.apply(self.player.pet_id, 20, EconomyTransactionType.web_reward,
                               f"test:topup:{_uuid.uuid4().hex[:12]}", reason="用例准备旅费", source="test.setup")

    def cafe_adventure(self) -> str:
        """走一次真实的咖啡馆冒险，返回通讯器里那条冒险消息的正文。"""
        self.top_up()
        depart = self.player.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.assertEqual(depart.status_code, 200, depart.text)
        self.clock.advance(minutes=7)
        visit_id = self.player.get("/journey/map").json()["current_visit_id"]
        self.assertIsNotNone(visit_id, "这一刻应该已经到店了")
        greet = next(a for a in self.player.get(f"/visits/{visit_id}").json()["activities"] if a["kind"] == "greet_resident")
        self.player.post(f"/visits/{visit_id}/actions", {"activity_id": greet["activity_id"]})
        self.clock.advance(seconds=5)
        items = self.player.get(f"/communicator/{self.player.pet_id}/messages").json()["items"]
        adventure = [m for m in items if "侦探" in m["text"]]
        self.assertTrue(adventure, items)
        return adventure[-1]["text"]

    def finish_journey(self) -> None:
        self.clock.advance(hours=2)
        self.run_background()

    def test_story_placeholder_that_would_crash_the_world_engine_is_rejected(self):
        bad = {"title": "咖啡馆小侦探", "badge": "新勋章", "story": "{pet}和{owner}一起找到了杯垫。"}
        check = self.publisher.post("/content/validate", {"content_type": "adventure", "slug": "cafe_detective",
                                                          "title": bad["title"], "body": bad}).json()
        self.assertFalse(check["ok"])
        self.assertTrue(any("owner" in issue["message"] for issue in check["issues"]), check)

        created = self.publisher.post("/content", {"content_type": "adventure", "slug": "cafe_detective",
                                                   "title": bad["title"], "body": bad})
        self.assertEqual(created.status_code, 201, created.text)
        item = created.json()["item"]
        publish = self.publisher.post(f"/content/{item['item_id']}/publish",
                                      {"revision": 1, "expected_version": item["version"], "reason": "尝试发布有问题的故事"})
        self.assertEqual(publish.status_code, 422, publish.text)
        self.assertEqual(self.cafe_adventure().count("小侦探勋章"), 1, "没发布成功就还是内置模板")

    def test_unknown_adventure_key_cannot_be_invented(self):
        response = self.publisher.post("/content", {"content_type": "adventure", "slug": "brand-new-thing",
                                                    "title": "凭空造一个", "body": {"title": "x", "badge": "y", "story": "{pet}做了点事。"}})
        self.assertEqual(response.status_code, 422, response.text)

    def test_published_version_is_consumed_by_new_events_only(self):
        before = self.cafe_adventure()
        self.assertIn("咖啡馆小侦探", self.player.get(f"/communicator/{self.player.pet_id}/messages").text)
        self.assertIn("小侦探勋章", before)
        self.finish_journey()

        v2 = {"title": "咖啡馆见习侦探", "badge": "见习侦探徽章",
              "story": "鹦鹉居民的杯垫又不见了。{pet}{keepsake}这次在花盆后面找到了，鹦鹉给了它一枚见习侦探徽章。"}
        created = self.publisher.post("/content", {"content_type": "adventure", "slug": "cafe_detective",
                                                   "title": v2["title"], "body": v2})
        self.assertEqual(created.status_code, 201, created.text)
        item = created.json()["item"]
        published = self.publisher.post(f"/content/{item['item_id']}/publish",
                                        {"revision": 1, "expected_version": item["version"], "reason": "活动文案改版"})
        self.assertEqual(published.status_code, 200, published.text)

        after = self.cafe_adventure()
        self.assertIn("见习侦探徽章", after, "新发生的冒险必须用已发布的版本")
        messages = self.player.get(f"/communicator/{self.player.pet_id}/messages").json()["items"]
        old = [m["text"] for m in messages if "小侦探勋章" in m["text"] and "见习" not in m["text"]]
        self.assertTrue(old, "之前那条消息必须原样保留")
        self.assertEqual(old[0], before, "已经发生过的事实一个字都不能改")

        # 回退：再发生的冒险回到内置文案，历史两条都在
        self.finish_journey()
        latest = self.publisher.get(f"/content/{item['item_id']}").json()["item"]
        withdrawn = self.publisher.post(f"/content/{item['item_id']}/withdraw",
                                        {"expected_version": latest["version"], "reason": "改版回滚"})
        self.assertEqual(withdrawn.status_code, 200, withdrawn.text)
        third = self.cafe_adventure()
        self.assertIn("小侦探勋章", third)
        self.assertNotIn("见习侦探徽章", third)
        texts = [m["text"] for m in self.player.get(f"/communicator/{self.player.pet_id}/messages").json()["items"]]
        self.assertTrue(any("见习侦探徽章" in t for t in texts), "撤下不能抹掉已经发生过的那一条")


if __name__ == "__main__":
    unittest.main()
