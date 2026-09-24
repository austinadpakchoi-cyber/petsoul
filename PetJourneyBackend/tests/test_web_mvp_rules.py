"""网页 MVP 规则：稀有种子闭环、并发唯一（领养/出发）、会话吊销与登录限流、通讯延迟与隔离、
叮嘱更正/撤回停止使用、动态公开开关、旅费不足。"""

from __future__ import annotations

import threading
import unittest

from app.schemas import EconomyTransactionType
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class WebRulesTests(WebPlatformTestBase):
    settle_on_read = True  # 读接口已改为纯读：这组用例按“任务进程一直跟得上”验证（每次 GET 前先跑一轮后台）
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)

    def fund(self, pet_id: str, amount: int, key: str) -> None:
        self.web.economy.apply(pet_id, amount, EconomyTransactionType.web_reward, f"test:{key}", reason="测试补贴", source="test")

    def confirm_all(self, user, text: str, purposes=("home_interaction", "private_chat", "travel_preference")) -> dict:
        session = user.post("/reception/sessions", {"pet_id": user.pet_id, "branch": "own_pet"}).json()
        session = user.post(f"/reception/sessions/{session['session_id']}/turns", {"text": text, "expected_revision": session["draft_revision"]}).json()
        decisions = [{"candidate_id": c["candidate_id"], "text": c["text"], "target": "give_to_pet", "purposes": list(purposes),
                      "slot": c["suggested_slot"], "slot_value": c["suggested_slot_value"]} for c in session["candidates"]]
        response = user.post("/reception/confirmations", {"session_id": session["session_id"], "draft_revision": session["draft_revision"], "decisions": decisions})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_rare_seed_comes_home_and_is_consumed_when_planted(self) -> None:
        user = self.user("seed-owner")
        user.adopt_and_move_in("adopt-arong")
        self.assert_envelope(user.post("/journey/depart", {"destination_key": "macau_ferry"}), 409, "INSUFFICIENT_FUNDS")
        self.assert_envelope(user.post("/journey/depart", {"destination_key": "moon"}), 404, "NOT_FOUND")
        self.fund(user.pet_id, 40, "seed-trip")
        snapshot = user.post("/journey/depart", {"destination_key": "macau_ferry"}).json()
        self.assertIn("Otter", str(snapshot), "动物世界承运人与班次身份")
        self.assertEqual(user.home()["wallet"]["balance"], 20)
        empty = next(p for p in user.home()["plots"] if p["stage"] == "empty")
        plant = {"home_id": user.home_id, "plot_id": empty["plot_id"], "action": "plant", "crop_key": "sea_salt_pea"}
        self.assertEqual(user.post("/farm/actions", plant).json()["error"]["details"]["reason"], "no_seed")

        self.clock.advance(minutes=256)
        self.assertEqual(user.home()["presence"], "at_home")
        badges = [i["title"] for i in user.get("/collection").json() if i["kind"] == "badge"]
        self.assertEqual(badges, ["海上小水手勋章"], "轮渡到站触发冒险模板，勋章绑定宠物")
        seeds = [i for i in user.get("/collection").json() if i["kind"] == "seed"]
        self.assertEqual(len(seeds), 1)
        self.assertTrue(seeds[0]["tradable"])
        self.assertFalse(seeds[0]["bound_to_pet"])
        planted = user.post("/farm/actions", plant)
        self.assertEqual(planted.status_code, 200, planted.text)
        self.assertEqual(planted.json()["plot"]["crop_key"], "sea_salt_pea")
        self.assertFalse([i for i in user.get("/collection").json() if i["kind"] == "seed"], "种下即消耗")
        other = next(p for p in user.home()["plots"] if p["stage"] == "empty")
        again = user.post("/farm/actions", {**plant, "plot_id": other["plot_id"]})
        self.assertEqual(again.json()["error"]["details"]["reason"], "no_seed")

        # 成熟后收获进仓库；卖给杂货铺才进入统一账本
        self.clock.advance(seconds=901)
        harvested = user.post("/farm/actions", {"home_id": user.home_id, "plot_id": empty["plot_id"], "action": "harvest"})
        self.assertEqual(harvested.status_code, 200, harvested.text)
        self.assertEqual(harvested.json()["wallet"]["balance"], 20)
        pantry = {i["item_key"]: i["qty"] for i in user.home()["pantry"]}
        self.assertEqual(pantry["sea_salt_pea"], 6)
        self.assertEqual(user.post("/market/sell", {"item_key": "sea_salt_pea", "qty": 6}).json()["wallet"]["balance"], 20 + 6 * 4)

    def test_adoption_race_has_single_winner(self) -> None:
        users = [self.user(f"racer-{i}") for i in range(4)]
        results: list[int] = []
        barrier = threading.Barrier(len(users))

        def adopt(u) -> None:
            barrier.wait()
            results.append(u.post("/adoption/adopt", {"candidate_id": "adopt-mochi"}).status_code)

        threads = [threading.Thread(target=adopt, args=(u,)) for u in users]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(results), [200, 409, 409, 409])
        candidate = next(c for c in users[0].get("/adoption/candidates").json() if c["candidate_id"] == "adopt-mochi")
        self.assertNotEqual(candidate["availability"], "available")

    def test_concurrent_departures_charge_once(self) -> None:
        user = self.user("double-depart")
        user.adopt_and_move_in("adopt-doudou")
        codes: list[int] = []
        barrier = threading.Barrier(3)

        def depart() -> None:
            barrier.wait()
            codes.append(user.post("/journey/depart", {"destination_key": "harbour_cafe"}).status_code)

        threads = [threading.Thread(target=depart) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(codes), [200, 409, 409])
        self.assertEqual(user.home()["wallet"]["balance"], 12)

    def test_logout_revokes_session_and_login_is_rate_limited(self) -> None:
        user = self.user("session-user")
        self.assertEqual(user.post("/auth/logout").status_code, 204)
        self.assert_envelope(user.get("/home"), 401, "AUTH_REQUIRED")
        for _ in range(8):
            wrong = self.client.post("/api/v1/web/auth/login", json={"username": "session-user", "password": "wrong-password-1"})
            self.assertEqual(wrong.status_code, 401)
            self.assertEqual(wrong.json()["error"]["code"], "INVALID_CREDENTIALS")
        self.assert_envelope(self.client.post("/api/v1/web/auth/login", json={"username": "session-user", "password": "longpassword1"}), 429, "RATE_LIMITED")
        self.assert_envelope(self.client.post("/api/v1/web/auth/register", json={"username": "session-user", "password": "longpassword1"}), 409, "USERNAME_TAKEN")

    def test_revoked_cookie_cannot_be_replayed(self) -> None:
        user = self.user("replay-user")
        cookie = user.client.cookies.get("petsoul_session")
        user.post("/auth/logout")
        self.client.cookies.set("petsoul_session", cookie)
        self.assert_envelope(self.client.get("/api/v1/web/session"), 401, "SESSION_EXPIRED")

    def test_communicator_reply_waits_for_pet_and_uses_confirmed_title(self) -> None:
        owner = self.user("chat-owner")
        created = owner.upload_pet("年糕", "dog")
        owner.pet_id = created.json()["pet_id"]
        self.confirm_all(owner, "叫我姐姐就好。")
        owner.move_in(public_posts=False)
        sent = owner.post(f"/communicator/{owner.pet_id}/messages", {"client_message_id": "cm-00000001", "text": "今天乖不乖"})
        self.assertEqual(sent.status_code, 200, sent.text)
        self.assertEqual(sent.json()["state"], "awaiting_reply")
        replay = owner.post(f"/communicator/{owner.pet_id}/messages", {"client_message_id": "cm-00000001", "text": "今天乖不乖"})
        self.assertEqual(replay.json()["message_id"], sent.json()["message_id"])
        thread = owner.get(f"/communicator/{owner.pet_id}/messages").json()["items"]
        self.assertEqual([m["sender"] for m in thread], ["owner"], "回复按宠物状态延后可见")
        self.clock.advance(seconds=21)
        thread = owner.get(f"/communicator/{owner.pet_id}/messages").json()["items"]
        self.assertEqual([m["sender"] for m in thread], ["owner", "pet"])
        self.assertTrue(thread[1]["text"].startswith("姐姐"))
        stranger = self.user("chat-stranger")
        stranger.adopt_and_move_in("adopt-pudding")
        self.assert_envelope(stranger.get(f"/communicator/{owner.pet_id}/messages"), 404, "NOT_FOUND")
        self.assert_envelope(stranger.post(f"/communicator/{owner.pet_id}/messages", {"client_message_id": "cm-00000001", "text": "偷看"}), 404, "NOT_FOUND")

    def test_correction_supersedes_and_revoke_stops_use(self) -> None:
        owner = self.user("memory-owner")
        owner.pet_id = owner.upload_pet("汤圆", "cat").json()["pet_id"]
        result = self.confirm_all(owner, "叫我妈妈就好。")
        note = result["notes"][0]
        owner.move_in()
        self.assertIn("妈妈", str(owner.home()["welcome"]))
        corrected = owner.post(f"/care-notes/{note['note_id']}/corrections", {"action": "correct", "expected_version": note["version"], "new_text": "叫我姐姐就好。"})
        self.assertEqual(corrected.status_code, 200, corrected.text)
        new_note = corrected.json()["new_note"]
        self.assertEqual(new_note["supersedes_note_id"], note["note_id"])
        self.assertIn("姐姐", str(owner.home()["welcome"]))
        self.assertNotIn("妈妈", str(owner.home()["welcome"]))
        stale = owner.post(f"/care-notes/{note['note_id']}/corrections", {"action": "correct", "expected_version": note["version"], "new_text": "x"})
        self.assertEqual(stale.status_code, 409)
        revoked = owner.post(f"/care-notes/{new_note['note_id']}/corrections", {"action": "revoke", "expected_version": new_note["version"]})
        self.assertEqual(revoked.status_code, 200, revoked.text)
        self.assertIsNone(owner.home()["welcome"])
        self.assert_envelope(owner.get(f"/pets/{owner.pet_id}/home-welcome"), 404, "NOT_FOUND")

    def test_confirmed_wish_marks_matching_destination(self) -> None:
        owner = self.user("wish-owner")
        owner.pet_id = owner.upload_pet("海苔", "cat").json()["pet_id"]
        self.confirm_all(owner, "以后想带它去看海。")
        owner.move_in()
        options = {d["destination_key"]: d for d in owner.get("/journey/destinations").json()}
        self.assertIsNotNone(options["macau_ferry"]["wish_match"])
        self.assertIsNone(options["tokyo_flight"]["wish_match"])

    def test_public_posts_off_keeps_trip_private(self) -> None:
        quiet = self.user("quiet-owner")
        quiet.adopt_and_move_in("adopt-yunduo", public_posts=False)
        watcher = self.user("watcher")
        watcher.adopt_and_move_in("adopt-qiuqiu")
        quiet.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.clock.advance(minutes=33)
        self.assertEqual(quiet.home()["presence"], "at_home")
        self.assertFalse(watcher.get("/circle/feed").json()["items"])
        self.assertTrue(quiet.get("/collection").json(), "回忆照常进入自己的收藏")
        self.assertFalse(quiet.get("/settings").json()["public_posts"])
        self.assertTrue(quiet.patch("/settings", {"public_posts": True}).json()["public_posts"])

    def test_resident_orders_pay_premium_once_and_shop_rejects_overselling(self) -> None:
        user = self.user("market-owner")
        user.adopt_and_move_in("adopt-arong")
        market = user.get("/market").json()
        self.assertFalse(market["player_listing_enabled"], "玩家挂牌未开放")
        self.assertEqual(len(market["orders"]), 2)
        order = market["orders"][0]
        self.assertGreater(order["reward"], order["shop_value"], "居民订单出价高于杂货铺")
        self.assertFalse(order["can_fulfill"])
        self.assertEqual(user.post(f"/market/orders/{order['order_id']}/fulfill").json()["error"]["details"]["reason"], "not_enough")
        self.assertEqual(user.post("/market/sell", {"item_key": "sun_pea", "qty": 1}).json()["error"]["details"]["reason"], "not_enough")
        self.web.inventory.add(user.user_id, user.home()["home_id"], order["item_key"], order["qty"], "测试补给", "test:stock")  # 仓库属于家（0.4.0）
        self.assertTrue(user.get("/market").json()["orders"][0]["can_fulfill"])
        done = user.post(f"/market/orders/{order['order_id']}/fulfill", key="order-key-0001")
        self.assertEqual(done.status_code, 200, done.text)
        self.assertEqual(done.json()["wallet"]["balance"], 20 + order["reward"])
        replay = user.post(f"/market/orders/{order['order_id']}/fulfill")
        self.assertEqual(replay.json()["wallet"]["balance"], 20 + order["reward"], "同一订单只结算一次")
        self.assertTrue(user.get("/market").json()["orders"][0]["fulfilled"])
        self.clock.advance(days=1)
        self.assertNotEqual(user.get("/market").json()["orders"][0]["order_id"], order["order_id"], "第二天换新订单")

    def test_owner_patrol_guards_for_a_while_then_cools_down(self) -> None:
        owner = self.user("patrol-owner")
        owner.adopt_and_move_in("adopt-qiuqiu")
        visitor = self.user("patrol-visitor")
        visitor.adopt_and_move_in("adopt-yunduo")
        self.assertEqual(owner.post("/farm/patrol").json()["error"]["details"]["reason"], "pet_home")
        self.clock.advance(seconds=181)
        owner.post("/journey/depart", {"destination_key": "harbour_cafe"})
        ripe = next(p for p in owner.home()["plots"] if p["stage"] == "ripe")
        body = {"home_id": owner.home_id, "plot_id": ripe["plot_id"], "cycle_id": ripe["cycle_id"]}
        patrol = owner.post("/farm/patrol")
        self.assertEqual(patrol.status_code, 200, patrol.text)
        self.assertEqual(patrol.json()["guard"]["basis"], "owner_patrol")
        self.assertTrue(owner.home()["guard"]["guarding"])
        self.assertTrue(visitor.get(f"/homes/{owner.home_id}").json()["guarded"])
        self.assert_envelope(visitor.post("/farm/steal", body), 409, "FARM_GUARDED")
        self.clock.advance(minutes=11)
        self.assertFalse(owner.home()["guard"]["guarding"])
        self.assertEqual(owner.post("/farm/patrol").json()["error"]["details"]["reason"], "cooldown")
        self.assertEqual(visitor.post("/farm/steal", body).status_code, 200)

    def test_cafe_adventure_uses_confirmed_keepsake_and_grants_bound_badge(self) -> None:
        owner = self.user("hero-owner")
        owner.pet_id = owner.upload_pet("布丁", "dog").json()["pet_id"]
        # **授权用途改过一次（CR-IMAGE-MEMORY-PURPOSE-2026-09-24）**：原先这里只授
        # `private_chat` + `home_interaction`，却在末尾断言那件物件出现在**家庭故事**里——
        # **那正是 B 报、c84a 逐段核实的那条泄露**：只授权过私聊的叮嘱进了全家可见的频道。
        # 这条用例当时是在**保护那个缺陷**。入口修好后它理应变红，而它一直没红，
        # 只是因为没人跑到它（A 那批受影响套件 11 个不含本文件，我改完也只跑了四个套件）——
        # **第一次全量才暴露**。
        #
        # 现在按接收方授权：家庭故事的接收方是家庭频道 → 要 `public_story`。
        # 本条钉的产品规则**没变**——「出现在故事里的物件必须是主人确认过的，不能凭空编」；
        # 变的只是「确认」要覆盖到哪个用途。
        # 反向那半（只授 `private_chat` 时两处都不得使用）由 Q 的 C32 覆盖，这里不重复。
        self.confirm_all(owner, "它最喜欢那条蓝色的毯子。",
                         purposes=("private_chat", "home_interaction", "public_story"))
        owner.move_in(public_posts=False)
        owner.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.clock.advance(minutes=7)
        visit_id = owner.get("/journey/map").json()["current_visit_id"]
        visit = owner.get(f"/visits/{visit_id}").json()
        greet = next(a for a in visit["activities"] if a["kind"] == "greet_resident")
        done = owner.post(f"/visits/{visit_id}/actions", {"activity_id": greet["activity_id"]}).json()
        self.assertIn("小侦探", next(a for a in done["activities"] if a["kind"] == "greet_resident")["result_text"])
        owner.post(f"/visits/{visit_id}/actions", {"activity_id": greet["activity_id"]})  # 重复点击不重复发勋章
        badges = [i for i in owner.get("/collection").json() if i["kind"] == "badge"]
        self.assertEqual([b["title"] for b in badges], ["小侦探勋章"])
        self.assertTrue(badges[0]["bound_to_pet"])
        self.assertFalse(badges[0]["tradable"])
        self.clock.advance(seconds=10)
        story = next(m["text"] for m in owner.get(f"/communicator/{owner.pet_id}/messages").json()["items"] if "咖啡馆小侦探" in m["text"])
        self.assertIn("蓝色的毯子", story, "主人确认、且授权了 public_story 的物件才出现在家庭故事里")

    def test_harvest_replay_does_not_duplicate(self) -> None:
        user = self.user("replay-farmer")
        user.adopt_and_move_in("adopt-pudding")
        self.clock.advance(seconds=181)
        ripe = next(p for p in user.home()["plots"] if p["stage"] == "ripe")
        body = {"home_id": user.home_id, "plot_id": ripe["plot_id"], "cycle_id": ripe["cycle_id"], "action": "harvest"}
        user.post("/farm/actions", body)
        user.post("/farm/actions", body)  # 新幂等键再点一次：自然键去重，不重复入库
        self.assertEqual({i["item_key"]: i["qty"] for i in user.home()["pantry"]}, {"sun_pea": 4})


if __name__ == "__main__":
    unittest.main()

