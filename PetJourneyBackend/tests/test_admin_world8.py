"""第八批：社交与举报关联、旅程逐段明细、待领养居民、宠物的东西补全、家里的名字与订单。

和第七批一样：数据用真实的玩家流程造（发动态、评论、点赞、关注、拉黑、举报、出门、报名驾校、填口味），
每一块核权限、访问留痕，以及**私密内容不出现**。
"""

from __future__ import annotations

import json
import unittest
from datetime import timezone

from admin_base import AdminTestBase
from test_admin_belongings import WorldFixture

from app.web_admin import labels as L

COMMENT = "鲍勃的评论：这张照片拍得真好看"
ALLERGY = "花生过敏（只写给家人看）"


class SocialFixture(WorldFixture):
    def public_post_of(self, player) -> str:
        """照玩家的真实流程：出门 → 到店 → 回家，旅程会发一条公开动态。"""
        player.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.clock.advance(minutes=7)
        self.run_background()
        self.clock.advance(minutes=30)
        self.run_background()
        with self.app.state.storage.connect() as conn:
            row = conn.execute("SELECT post_id FROM web_posts WHERE user_id = ? AND visibility = 'public' ORDER BY created_at DESC LIMIT 1",
                               (player.user_id,)).fetchone()
        self.assertIsNotNone(row, "这段旅程应当发出一条公开动态")
        return row["post_id"]

    def bob_interacts_with(self, post_id: str) -> None:
        self.assertEqual(self.bob.post(f"/posts/{post_id}/comments", {"as_actor": "owner", "text": COMMENT}).status_code, 201)
        self.assertEqual(self.bob.post(f"/posts/{post_id}/reactions", {"as_actor": "owner"}).status_code, 200)
        self.assertEqual(self.bob.post(f"/pets/{self.alice.pet_id}/follow", {"follow": True}).status_code, 204)
        self.assertEqual(self.bob.post("/blocks", {"post_id": post_id}).status_code, 204)
        self.assertEqual(self.bob.post("/reports", {"target_kind": "post", "target_id": post_id, "reason": "内容看着不舒服"}).status_code, 204)


class SocialTests(SocialFixture):
    def test_social_shows_public_excerpts_relations_and_counts(self):
        post_id = self.public_post_of(self.alice)
        self.bob_interacts_with(post_id)
        support = self.staff("social-support", ["support"])
        support.login_ok()

        alice = support.get(f"/users/{self.alice.user_id}/social").json()
        mine = next(p for p in alice["posts"]["recent"] if p["post_id"] == post_id)
        self.assertTrue(mine["excerpt"] and len(mine["excerpt"]) <= 41, "公开动态只给前 40 个字")
        self.assertTrue(mine["reported"])
        self.assertEqual(alice["reports"]["against"], 1)
        self.assertGreaterEqual(alice["reactions"]["received"], 1)
        self.assertEqual([(b["user_id"], b["name"]["username"]) for b in alice["blocks"]["blocked_by"]], [(self.bob.user_id, "belong-bob")])
        self.assertEqual([f["pet_id"] for f in alice["follows"]["followers"]], [self.bob.pet_id])

        bob = support.get(f"/users/{self.bob.user_id}/social").json()
        self.assertIn(COMMENT[:10], bob["comments"]["recent"][0]["excerpt"], "评论发在公开动态下，给摘要")
        self.assertEqual([b["user_id"] for b in bob["blocks"]["blocked"]], [self.alice.user_id])
        self.assertEqual([f["pet_id"] for f in bob["follows"]["following"]], [self.alice.pet_id])
        self.assertEqual((bob["reports"]["filed"], bob["reactions"]["given"]), (1, 1))

        audit = support.get("/audit?action=user.social").json()["entries"]
        self.assertEqual({e["target_id"] for e in audit}, {self.alice.user_id, self.bob.user_id}, "看一次留一条")

    def test_followers_only_posts_give_no_text(self):
        """现在的代码只发公开动态；「仅关注者可见」在契约与表约束里都有。把一条动态改成仅关注者可见，确认后台不给内容——给将来的防线。"""
        post_id = self.public_post_of(self.alice)
        with self.app.state.storage.connect() as conn:
            text = conn.execute("SELECT text FROM web_posts WHERE post_id = ?", (post_id,)).fetchone()["text"]
            conn.execute("UPDATE web_posts SET visibility = 'followers' WHERE post_id = ?", (post_id,))
            conn.commit()
        support = self.staff("social-support-2", ["support"])
        support.login_ok()
        body = support.get(f"/users/{self.alice.user_id}/social").json()
        row = next(p for p in body["posts"]["recent"] if p["post_id"] == post_id)
        self.assertIsNone(row["excerpt"])
        self.assertNotIn(text[:12], json.dumps(body, ensure_ascii=False))

    def test_needs_user_read(self):
        editor = self.staff("social-editor", ["content_editor"])
        editor.login_ok()
        self.assert_admin_error(editor.get(f"/users/{self.alice.user_id}/social"), 403, "FORBIDDEN")


class ReportContextTests(SocialFixture):
    def test_the_queue_shows_how_the_two_are_related(self):
        post_id = self.public_post_of(self.alice)
        self.bob_interacts_with(post_id)
        moderator = self.staff("context-moderator", ["moderator"])
        moderator.login_ok()
        row = next(r for r in moderator.get("/reports?only_open=false").json()["reports"] if r["target_id"] == post_id)
        context = row["context"]
        self.assertEqual((context["author_user_id"], context["author_name"]["username"]), (self.alice.user_id, "belong-alice"))
        self.assertEqual((context["reporter_blocked_author"], context["author_blocked_reporter"]), (True, False),
                         "举报人早就把对方拉黑了——处理骚扰类举报时要知道")
        self.assertEqual((context["reports_against_author"], context["author_removed"], context["reporter_filed"]), (1, 0, 1))
        self.assertFalse(context["same_person"])
        self.assertEqual(row["reporter_name"]["username"], "belong-bob", "举报人也写名字")


class JourneyDetailTests(SocialFixture):
    def test_each_leg_and_the_visit_are_listed_in_plain_words(self):
        self.alice.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.clock.advance(minutes=7)
        self.run_background()
        support = self.staff("journey-support", ["support"])
        support.login_ok()
        journey = support.get(f"/pets/{self.alice.pet_id}/diagnosis").json()["journey"]
        self.assertTrue(journey["legs"], "出门之后应当列出逐段交通")
        for leg in journey["legs"]:
            self.assertTrue(leg["from"] and leg["to"], "每一段都写从哪到哪（站点名）")
            self.assertIn(leg["mode"], L.TRANSPORT_MODE)
            self.assertIn(leg["direction"], L.LEG_DIRECTION)
            self.assertIn(leg["time_basis"], L.TIME_BASIS)
        visit = journey["visits"][0]
        self.assertTrue(visit["place"])
        self.assertTrue(all(a["kind"] in L.VISIT_ACTIVITY for a in visit["activities"]))
        self.assertNotIn("result_text", json.dumps(journey), "店里活动的结果文字是写给玩家看的故事，不给")


class ResidentsTests(SocialFixture):
    def test_the_list_shows_who_adopted_whom(self):
        support = self.staff("residents-support", ["support"])
        support.login_ok()
        body = support.get("/residents").json()
        adopted = [r for r in body["residents"] if r["status"] == "adopted"]
        self.assertIn(("belong-alice", self.alice.pet_id), {((r["adopted_by_name"] or {}).get("username"), r["pet_id"]) for r in adopted},
                      "领养了谁、被哪位玩家领养，写名字")
        self.assertEqual(body["counts"].get("adopted"), len(adopted))
        for row in body["residents"]:
            self.assertIn(row["status"], L.RESIDENT_STATUS)
            self.assertIn(row["kind"], L.RESIDENT_KIND)

    def test_support_or_content_can_see_it_and_nobody_else(self):
        from app.web_admin.permissions import ROLE_PERMISSIONS, Permission, Role

        editor = self.staff("residents-editor", ["content_editor"])  # 只有 content.read
        editor.login_ok()
        seen = editor.get("/residents").json()
        adopted = [r for r in seen["residents"] if r["status"] == "adopted"]
        self.assertTrue(adopted)
        self.assertEqual({(r["adopted_by"], r["adopted_by_name"], r["adopted_home_id"]) for r in adopted}, {(None, None, None)},
                         "内容运营看得到档案与状态，看不到是哪位玩家领养的")
        self.assertIn("查用户与家庭", seen["adopters_note"])
        self.assertNotIn("belong-alice", json.dumps(seen, ensure_ascii=False))
        # 现有的每个角色都至少带着两条之一——「谁都看不了」这条拒绝路径按现在的角色配置走不到，先把这个事实钉住：
        wanted = {Permission.USER_READ, Permission.CONTENT_READ}
        self.assertEqual([role.value for role in Role if not (ROLE_PERMISSIONS[role] & wanted)], [])
        # 再临时把一个角色收紧到两条都没有，真实地走一次拒绝（结束时还原）
        original = ROLE_PERMISSIONS[Role.auditor]
        self.addCleanup(ROLE_PERMISSIONS.__setitem__, Role.auditor, original)
        ROLE_PERMISSIONS[Role.auditor] = frozenset(original - wanted)
        narrowed = self.staff("residents-narrowed", ["auditor"])
        narrowed.login_ok()
        self.assert_admin_error(narrowed.get("/residents"), 403, "FORBIDDEN")
        denied = [e for e in self.owner().get("/audit").json()["entries"]
                  if e["status"] == "denied" and e["actor_username"] == "residents-narrowed"]
        self.assertEqual(denied[0]["permission"], "user.read|content.read", "两条任一即可；被挡下的那次也留痕")


class MoreBelongingsTests(SocialFixture):
    def test_school_food_friends_media_without_content(self):
        self.assertEqual(self.alice.post("/driving/enroll").status_code, 200)
        preference = {"preference_id": "pref-owner-1", "subject": "owner", "pet_id": self.alice.pet_id, "version": 1, "label": "清淡",
                      "taste": {"spicy": -1}, "restrictions": [{"kind": "allergy", "label": ALLERGY}], "source": "explicit",
                      "updated_at": self.clock.now.astimezone(timezone.utc).isoformat()}
        saved = self.alice.put("/food/preferences/owner", preference)
        self.assertEqual(saved.status_code, 200, saved.text)

        support = self.staff("more-support", ["support"])
        support.login_ok()
        body = support.get(f"/pets/{self.alice.pet_id}/belongings").json()
        self.assertEqual(body["food"]["preferences"], {"owner": 1}, "口味只给数量")
        self.assertNotIn(ALLERGY, json.dumps(body, ensure_ascii=False), "过敏、忌口这类限制恒为私密，不出现")
        self.assertIsInstance(body["school"]["subjects"], list)
        self.assertIsInstance(body["friends"], list)
        self.assertEqual(body["media"]["count"], 0)


class HomeNamesTests(SocialFixture):
    def test_the_home_shows_player_names_and_orders_need_economy_read(self):
        self.steal_from_alice()
        support = self.staff("names-support", ["support"])
        support.login_ok()
        home = support.get(f"/homes/{self.alice.home_id}").json()
        self.assertEqual(home["people"][self.bob.user_id]["username"], "belong-bob", "来偷菜的是谁，写名字")
        self.assertIsInstance(home["orders"], list)
        audit = support.get("/audit?action=home.detail").json()["entries"]
        self.assertEqual(audit[0]["changes"]["sections"], ["farm", "steals", "pantry", "orders"], "看到了订单，留痕里也记上")
        moderator = self.staff("names-moderator", ["moderator"])
        moderator.login_ok()
        self.assertIsNone(moderator.get(f"/homes/{self.alice.home_id}").json()["orders"], "居民订单是游戏资产：没有 economy.read 不给")


class ContentPreviewWordsTests(AdminTestBase):
    """六种内容的预览：每一行都有说法（界面不显示字段代码）；玩家侧的接口路径只在 consumer_api（技术代码）里；
    交通方式、居民状态这些代码在预览正文里也换成说法。"""

    DRAFTS = (
        ("announcement", "maintenance-week", {"title": "维护通知", "body": "今晚会短暂维护。", "severity": "maintenance", "audience": "all"}),
        ("adventure", "cafe_detective", {"title": "咖啡馆小侦探", "badge": "侦探徽章", "story": "{pet}在咖啡馆找到了{keepsake}。"}),
        ("crop", "sun_pea", {"label": "太阳豌豆", "unit_value": 3, "grow_seconds": 240}),
        ("job", "florist", {"label": "在花店帮忙", "pay": 30, "hours": 2}),
        ("destination", "harbour_cafe", {"title": "海边咖啡馆", "city": "香港", "summary": "看海喝咖啡", "fee": 8}),
        ("resident", "adopt-lan", {"personality": "慢热", "dream": "看海"}),
    )

    def test_every_preview_line_has_plain_words(self):
        editor = self.staff("preview-editor", ["content_editor"])
        editor.login_ok()
        for content_type, slug, body in self.DRAFTS:
            with self.subTest(content_type):
                created = editor.post("/content", {"content_type": content_type, "slug": slug, "title": f"{content_type} 预览", "body": body})
                self.assertEqual(created.status_code, 201, created.text)
                preview = editor.get(f"/content/{created.json()['item']['item_id']}/preview").json()
                self.assertEqual(sorted(set(preview["rendered"]) - set(L.CONTENT_FIELD)), [], "这些预览行在界面上会显示成代码")
                self.assertEqual(sorted({i["field"] for i in preview["issues"]} - set(L.CONTENT_FIELD)), [])
                self.assertNotIn("/", str(preview["rendered"].get("consumer")), "接口路径不进正文，只在 consumer_api 里")
                if content_type == "destination":
                    self.assertNotRegex(preview["rendered"]["modes"], r"[a-z]", "交通方式说中文")
                if content_type == "resident":
                    self.assertIsInstance(preview["rendered"]["identity"], str, "是谁：写成一句话，不给界面一个对象")
                    self.assertNotRegex(preview["rendered"]["identity"], r"available|adopted|reserved")


if __name__ == "__main__":
    unittest.main()
