"""把还没进后台的管理项接进来：宠物的东西、家里的东西、系统运行（方案 §3）。

每一块都核四件事：真实数据能看到（用真实的玩家流程造，不往表里硬塞）；权限按段给；
查看会留访问审计；**私密正文一个字都不出现**（主人发的暗号、宠物写的字、证件完整号码）。
"""

from __future__ import annotations

import json
import unittest

from admin_base import AdminTestBase
from web_base import LUNCH_UTC, FakeClock

SECRET = "只有主人知道的暗号-7Q3"


class WorldFixture(AdminTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.alice = self.user("belong-alice")
        self.alice.adopt_and_move_in("adopt-lan")
        self.bob = self.user("belong-bob")
        self.bob.adopt_and_move_in("adopt-doudou")

    def steal_from_alice(self) -> None:
        """照玩家的真实流程：菜熟了 → 爱丽丝带宠物出门（没人守）→ 鲍勃来偷一份。"""
        self.clock.advance(seconds=181)
        ripe = next(p["plot"] for p in self.bob.get(f"/homes/{self.alice.home_id}").json()["plots"] if p["plot"]["stage"] == "ripe")
        departed = self.alice.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.assertEqual(departed.status_code, 200, departed.text)
        stolen = self.bob.post("/farm/steal", {"home_id": self.alice.home_id, "plot_id": ripe["plot_id"], "cycle_id": ripe["cycle_id"]})
        self.assertEqual(stolen.status_code, 200, stolen.text)


class PetBelongingsTests(WorldFixture):
    def test_support_sees_states_and_counts_but_no_private_text(self):
        sent = self.alice.post(f"/communicator/{self.alice.pet_id}/messages", {"client_message_id": "cm-secret-1", "text": SECRET})
        self.assertIn(sent.status_code, (200, 201), sent.text)
        self.alice.post("/journey/depart", {"destination_key": "harbour_cafe"})
        for minutes in (7, 30, 30):
            self.clock.advance(minutes=minutes)
            self.run_background()

        support = self.staff("belong-support", ["support"])
        support.login_ok()
        before = self.table_counts(["web_messages", "web_collection_items", "web_credentials", "web_pending_replies"])
        response = support.get(f"/pets/{self.alice.pet_id}/belongings")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(self.table_counts(["web_messages", "web_collection_items", "web_credentials", "web_pending_replies"]), before,
                         "看宠物的东西不写任何业务表")

        self.assertIn("owner", body["messages"]["by_sender"], "主人发过消息：只给条数与时间")
        self.assertEqual({c["kind"] for c in body["credentials"]} >= {"bank_card", "identity_card"}, True)
        self.assertIn("privacy_note", body)

        raw = json.dumps(body, ensure_ascii=False)
        self.assertNotIn(SECRET, raw, "主人发的消息正文不能出现在后台")
        with self.app.state.storage.connect() as conn:
            pet_texts = [r["text"] for r in conn.execute("SELECT text FROM web_messages WHERE pet_id = ? AND text IS NOT NULL",
                                                         (self.alice.pet_id,)) if r["text"] and len(r["text"]) >= 6]
            numbers = [r["number"] for r in conn.execute("SELECT number FROM web_credentials WHERE pet_id = ?", (self.alice.pet_id,))]
        self.assertTrue(pet_texts, "这段旅程应当产生宠物写的消息，否则这条断言没有意义")
        for text in pet_texts:
            self.assertNotIn(text, raw, "宠物写的消息正文也不能出现")
        for number in numbers:
            self.assertNotIn(number, raw, "证件只给末 4 位，不给完整号码")
            self.assertIn(number[-4:], raw)

        audit = support.get("/audit?action=pet.belongings").json()["entries"]
        self.assertEqual((audit[0]["actor_username"], audit[0]["target_id"]), ("belong-support", self.alice.pet_id), "查看留痕")

    def test_needs_pet_read(self):
        moderator = self.staff("belong-moderator", ["moderator"])
        moderator.login_ok()
        self.assert_admin_error(moderator.get(f"/pets/{self.alice.pet_id}/belongings"), 403, "FORBIDDEN")
        support = self.staff("belong-support-2", ["support"])
        support.login_ok()
        self.assert_admin_error(support.get("/pets/PJ-NOPE/belongings"), 404, "NOT_FOUND")


class HomeTests(WorldFixture):
    def test_steal_shows_on_both_homes_and_the_pantry_is_named(self):
        self.steal_from_alice()
        support = self.staff("home-support", ["support"])  # user.read + economy.read
        support.login_ok()

        victim = support.get(f"/homes/{self.alice.home_id}")
        self.assertEqual(victim.status_code, 200, victim.text)
        stolen = victim.json()["steals"]["from_this_home"]
        self.assertEqual((len(stolen), stolen[0]["thief_user_id"], stolen[0]["units"]), (1, self.bob.user_id, 1))

        thief = support.get(f"/homes/{self.bob.home_id}").json()
        self.assertEqual(thief["steals"]["by_this_household"][0]["victim_home_id"], self.alice.home_id)
        stock = {row["item_key"]: row for row in thief["pantry"]["stock"]}
        self.assertEqual((stock["sun_pea"]["qty"], stock["sun_pea"]["item_label"] is not None), (1, True), "物品名按作物目录取")
        self.assertIn("摘了", thief["pantry"]["moves"][0]["reason"], "变动原因是系统写的说明")
        self.assertTrue(thief["farm"]["plots"], "菜地一格一格列出来")

    def test_the_pantry_needs_economy_read(self):
        moderator = self.staff("home-moderator", ["moderator"])  # 有 user.read，没有 economy.read
        moderator.login_ok()
        body = moderator.get(f"/homes/{self.alice.home_id}").json()
        self.assertIsNone(body["pantry"], "仓库是游戏资产：没有 economy.read 就不给")
        self.assertIn("看星币流水与家里的库存", body["pantry_note"])
        self.assertIsNotNone(body["farm"], "菜地与偷菜记录 user.read 就能看")
        audit = [e for e in self.owner().get("/audit?action=home.detail").json()["entries"] if e["actor_username"] == "home-moderator"]
        self.assertEqual(audit[0]["changes"]["sections"], ["farm", "steals"], "留痕里记下看了哪几段")

    def test_user_detail_links_to_the_home(self):
        support = self.staff("home-support-2", ["support"])
        support.login_ok()
        homes = support.get(f"/users/{self.alice.user_id}").json()["homes"]
        self.assertEqual([h["home_id"] for h in homes], [self.alice.home_id])


class SystemStatusTests(WorldFixture):
    def test_system_status_reads_real_sources(self):
        self.alice.post("/journey/depart", {"destination_key": "harbour_cafe"})
        sre = self.staff("system-sre", ["sre"])
        sre.login_ok()
        response = sre.get("/system")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        with self.app.state.storage.connect() as conn:
            pending = conn.execute("SELECT COUNT(*) FROM web_outbox WHERE status = 'pending'").fetchone()[0]
            migrations = conn.execute("SELECT COUNT(*) FROM web_schema_migrations").fetchone()[0]
        self.assertEqual(body["outbox"]["pending_total"], pending, "待投递数与表里对得上")
        self.assertEqual(body["migrations"]["count"], migrations)
        self.assertEqual(body["backups"]["available"], False, "没有可读的备份记录：如实说未接入，不显示正常")
        self.assertEqual([s["key"] for s in body["switches"]], ["ai_calls"])
        self.assertIsInstance(body["workers"], list)

    def test_needs_ops_read(self):
        moderator = self.staff("system-moderator", ["moderator"])
        moderator.login_ok()
        self.assert_admin_error(moderator.get("/system"), 403, "FORBIDDEN")


if __name__ == "__main__":
    unittest.main()
