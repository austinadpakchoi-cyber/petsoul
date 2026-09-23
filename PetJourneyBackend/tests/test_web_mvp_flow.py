"""网页 MVP 主循环（两个真实账号，全部经 /api/v1/web）：
注册 → 领养/上传 → 接待确认 → 入住 → 菜园 → 出发（扣旅费）→ 同行影音 → 寻味改选 → 到店活动与明信片
→ 星球圈互动 → 回家 → 收藏与通讯。服务器时钟由测试推进，旅程按真实经过时间补齐事件，不压缩。
"""

from __future__ import annotations

import unittest
from datetime import datetime

from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase, tiny_png


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


class TwoHouseholdLoopTests(WebPlatformTestBase):
    settle_on_read = True  # 读接口已改为纯读：这组用例按“任务进程一直跟得上”验证（每次 GET 前先跑一轮后台）
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)

    # ---- 建立两户 ----
    def _alice_adopts_and_skips_reception(self):
        alice = self.user("alice")
        ids = [c["candidate_id"] for c in alice.get("/adoption/candidates").json()]
        self.assertIn("adopt-lan", ids)
        adopted = alice.post("/adoption/adopt", {"candidate_id": "adopt-lan"})
        self.assertEqual(adopted.status_code, 200, adopted.text)
        alice.pet_id = adopted.json()["pet_id"]
        self.assertEqual(alice.get("/onboarding").json()["step"], "reception_optional")
        session = alice.post("/reception/sessions", {"pet_id": alice.pet_id, "branch": "adopted"}).json()
        self.assertEqual(session["mode"], "guided_notes")
        self.assertTrue(session["host"]["is_ai"])
        skipped = alice.post(f"/reception/sessions/{session['session_id']}/skip").json()
        self.assertEqual(skipped["status"], "skipped")
        self.assertEqual(alice.get("/onboarding").json()["step"], "ready_to_move_in")
        alice.move_in(public_posts=True)
        return alice

    def _bob_uploads_and_confirms(self):
        bob = self.user("bob")
        taken = bob.post("/adoption/adopt", {"candidate_id": "adopt-lan"})
        self.assert_envelope(taken, 409, "ADOPTION_TAKEN")
        created = bob.upload_pet("团子", "cat", tiny_png())
        self.assertEqual(created.status_code, 201, created.text)
        bob.pet_id = created.json()["pet_id"]
        self.assertEqual(created.json()["origin"], "own_pet")
        photo = bob.get(f"/media/pets/{bob.pet_id}/photo")
        self.assertEqual(photo.status_code, 200)
        self.assertNotIn(b"tEXt", photo.content, "上传时剥离元数据块")
        self.assertIn("private", photo.headers["cache-control"])

        session = bob.post("/reception/sessions", {"pet_id": bob.pet_id, "branch": "own_pet"}).json()
        text = "叫我妈妈就好。它最喜欢那条蓝色的毯子。它不喜欢被抱。以后想带它去看海。它小时候走丢过一次，别告诉它。"
        session = bob.post(f"/reception/sessions/{session['session_id']}/turns", {"text": text, "expected_revision": session["draft_revision"]}).json()
        candidates = {c["suggested_slot"] or c["kind"]: c for c in session["candidates"]}
        for c in session["candidates"]:
            self.assertIn(c["source_excerpt"], text, "候选必须是原话依据，不补编")
        self.assertEqual(candidates["owner_title"]["suggested_slot_value"], "妈妈")
        self.assertIn("owner_private", candidates)
        stale = bob.post(f"/reception/sessions/{session['session_id']}/turns", {"text": "再补一句", "expected_revision": 0})
        self.assert_envelope(stale, 409, "VERSION_CONFLICT")

        decisions = []
        for c in session["candidates"]:
            if c["kind"] == "owner_private":
                decisions.append({"candidate_id": c["candidate_id"], "text": c["text"], "target": "keep_here", "purposes": []})
            elif c["suggested_slot"] == "wish_place":
                decisions.append({"candidate_id": c["candidate_id"], "text": c["text"], "target": "give_to_pet", "purposes": ["travel_preference"],
                                  "slot": "wish_place", "slot_value": c["suggested_slot_value"]})
            else:
                decisions.append({"candidate_id": c["candidate_id"], "text": c["text"], "target": "give_to_pet",
                                  "purposes": ["home_interaction", "private_chat"], "slot": c["suggested_slot"], "slot_value": c["suggested_slot_value"]})
        body = {"session_id": session["session_id"], "draft_revision": session["draft_revision"], "decisions": decisions}
        confirmed = bob.post("/reception/confirmations", body, key="confirm-bob-1")
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        replay = bob.post("/reception/confirmations", body, key="confirm-bob-1")
        self.assertEqual(replay.json()["confirmation_id"], confirmed.json()["confirmation_id"], "同一幂等键重放返回同一确认")
        self.assertEqual(confirmed.json()["onboarding"]["step"], "ready_to_move_in")
        after = bob.get(f"/reception/sessions/{session['session_id']}").json()
        self.assertEqual(after["candidates"], [], "确认后清除草稿")
        self.assertEqual(after["turns"], [])

        welcome = bob.get(f"/pets/{bob.pet_id}/home-welcome").json()
        kinds = {d["kind"]: d["text"] for d in welcome["details"]}
        self.assertIn("妈妈", kinds.get("owner_title", "") + welcome["greeting"])
        self.assertIn("毯子", kinds.get("favorite_object", ""))
        self.assertNotIn("走丢", str(welcome), "只留在这里的私密内容不进入欢迎")
        bob.move_in(public_posts=True)
        return bob

    def test_two_households_full_loop(self) -> None:
        alice = self._alice_adopts_and_skips_reception()
        bob = self._bob_uploads_and_confirms()

        # ---- 入住后的家 ----
        home = alice.home()
        self.assertEqual(home["presence"], "at_home")
        self.assertEqual(home["wallet"]["balance"], 20)
        plot = next(p for p in home["plots"] if p["crop_key"] == "sun_pea")
        self.assertEqual(plot["stage"], "growing")
        self.assertEqual(bob.home()["welcome"]["details"][0]["kind"] in ("owner_title", "favorite_object", "interaction_boundary"), True)

        # 旧 /api/v1/create_pet 会自动出发；网页入住不会。
        self.assertIsNone(home["journey"])

        # ---- 菜园：成熟、宠物在家守护 ----
        self.clock.advance(seconds=181)
        visit_home = bob.get(f"/homes/{alice.home_id}").json()
        self.assertTrue(visit_home["guarded"])
        ripe = next(p["plot"] for p in visit_home["plots"] if p["plot"]["stage"] == "ripe")
        steal_body = {"home_id": alice.home_id, "plot_id": ripe["plot_id"], "cycle_id": ripe["cycle_id"]}
        self.web.farm.catch_roll = lambda key: 0.0  # 宠物在家醒着时多半会发现小偷；这里固定为“被发现”
        self.assert_envelope(bob.post("/farm/steal", steal_body), 409, "FARM_GUARDED")

        # ---- 出发：扣旅费、唯一位置 ----
        destinations = {d["destination_key"]: d for d in alice.get("/journey/destinations").json()}
        self.assertTrue(destinations["harbour_cafe"]["affordable"])
        self.assertFalse(destinations["macau_ferry"]["affordable"])
        self.assertEqual(destinations["harbour_cafe"]["time_basis"], "demo_fixture")
        departed = alice.post("/journey/depart", {"destination_key": "harbour_cafe"}, key="depart-alice-1")
        self.assertEqual(departed.status_code, 200, departed.text)
        replay = alice.post("/journey/depart", {"destination_key": "harbour_cafe"}, key="depart-alice-1")
        self.assertEqual(replay.json()["journey_id"], departed.json()["journey_id"])
        self.assert_envelope(alice.post("/journey/depart", {"destination_key": "harbour_cafe"}), 409, "ALREADY_TRAVELING")
        home = alice.home()
        self.assertEqual(home["wallet"]["balance"], 12, "旅费只扣一次")
        self.assertEqual(home["presence"], "in_transit")
        self.assertIsNotNone(home["journey"])
        snapshot = departed.json()
        self.assertEqual(snapshot["lifecycle"], "active")
        self.assertNotIn("cabin", str(snapshot).lower())

        # ---- 宠物外出后才能偷；全体访客共享可偷上限 ----
        self.assertFalse(alice.home()["guard"]["guarding"], "宠物外出且主人没巡院：如实显示无人守护")
        stolen = bob.post("/farm/steal", steal_body, key="steal-bob-1")
        self.assertEqual(stolen.status_code, 200, stolen.text)
        self.assertEqual((stolen.json()["gained_item_key"], stolen.json()["gained_units"]), ("sun_pea", 1))
        again = bob.post("/farm/steal", steal_body, key="steal-bob-1")
        self.assertEqual(again.json(), stolen.json(), "幂等重放不重复入库")
        self.assertEqual(bob.home()["wallet"]["balance"], 20, "偷到的是物资，不是直接的游戏币")
        self.assertEqual({i["item_key"]: i["qty"] for i in bob.home()["pantry"]}, {"sun_pea": 1})
        sold = bob.post("/market/sell", {"item_key": "sun_pea", "qty": 1}, key="sell-bob-1")
        self.assertEqual(sold.status_code, 200, sold.text)
        self.assertEqual(bob.post("/market/sell", {"item_key": "sun_pea", "qty": 1}, key="sell-bob-1").json(), sold.json())
        self.assertEqual(bob.home()["wallet"]["balance"], 22)
        self.assertEqual(bob.home()["pantry"], [])
        self.assert_envelope(bob.post("/farm/steal", steal_body), 409, "CONFLICT")
        carol = self.user("carol")
        carol.adopt_and_move_in("adopt-lizi")
        nothing = carol.post("/farm/steal", steal_body)
        self.assertEqual(nothing.json()["error"]["details"]["reason"], "nothing_left")

        # ---- 同行影音：地图上的音符入口 → 会话 → 共同控制 → 心跳累计 ----
        entry = next(e for e in snapshot["activity_entries"] if e["media_session_id"])
        self.assertEqual(entry["badge"], "music", "步行段只放音乐")
        sid = entry["media_session_id"]
        session = alice.get(f"/media/sessions/{sid}").json()
        self.assertFalse(session["video_allowed"] and session["media"]["kind"] == "video")
        alice.post(f"/media/sessions/{sid}/join", {"device_id": "dev-a1"})

        def beat(device: str, mode: str = "synced") -> dict:
            current = alice.get(f"/media/sessions/{sid}").json()
            anchor = current["anchor"]
            position = anchor["position_ms"]
            if current["state"] == "playing":
                started = datetime.fromisoformat(anchor["server_time"].replace("Z", "+00:00"))
                position += int((self.clock.now - started).total_seconds() * 1000)
            body = {"device_id": device, "player_state": mode, "position_ms": position, "media_edition": current["media"]["edition"], "client_time": iso(self.clock.now)}
            response = alice.post(f"/media/sessions/{sid}/heartbeat", body)
            self.assertEqual(response.status_code, 200, response.text)
            return response.json()

        beat("dev-a1")
        for _ in range(3):
            self.clock.advance(seconds=15)
            participation = beat("dev-a1")
        self.assertGreaterEqual(participation["counted_ms"], 45_000)
        solo = beat("dev-a1", "solo")
        self.assertEqual(solo["counted_ms"], participation["counted_ms"], "单独收听不算同步陪伴")

        current = alice.get(f"/media/sessions/{sid}").json()
        paused = alice.post(f"/media/sessions/{sid}/commands", {"device_id": "dev-a1", "command": "pause", "session_revision": current["revision"]}, key="cmd-pause-1")
        self.assertEqual(paused.status_code, 200, paused.text)
        self.assertEqual(paused.json()["state"], "paused")
        self.assertEqual(paused.json()["revision"], current["revision"] + 1)
        stale = alice.post(f"/media/sessions/{sid}/commands", {"device_id": "dev-a1", "command": "resume", "session_revision": current["revision"]})
        self.assert_envelope(stale, 409, "VERSION_CONFLICT")
        leased = alice.post(f"/media/sessions/{sid}/commands", {"device_id": "dev-a2", "command": "resume", "session_revision": paused.json()["revision"]})
        self.assert_envelope(leased, 409, "CONTROL_LEASE_HELD")
        self.assert_envelope(bob.get(f"/media/sessions/{sid}"), 404, "NOT_FOUND")
        resumed = alice.post(f"/media/sessions/{sid}/commands", {"device_id": "dev-a1", "command": "resume", "session_revision": paused.json()["revision"]})
        self.assertEqual(resumed.json()["state"], "playing")

        # ---- 寻味（宠物模式）+ 到店前改选：行程版本 +1，旧推荐待复核 ----
        recs = alice.post("/food/recommendations", {"mode": "pet_virtual_explore", "pet_id": alice.pet_id, "max_results": 3})
        self.assertEqual(recs.status_code, 200, recs.text)
        items = recs.json()["items"]
        self.assertTrue(items)
        first = items[0]
        self.assertEqual(first["itinerary_version"], 1)
        self.assertIsNone(first["scores"]["quality"], "演示资料不产出真实品质分")
        journey_map = alice.get("/journey/map").json()
        self.assertIsNone(journey_map["current_visit_id"], "还在路上")
        visit_id = journey_map["planned_visit_id"]
        chosen = alice.post(f"/visits/{visit_id}/choice", {"recommendation_id": first["recommendation_id"], "expected_itinerary_version": 1})
        self.assertEqual(chosen.status_code, 200, chosen.text)
        self.assertEqual(chosen.json()["itinerary_version"], 2)
        self.assertEqual(alice.get(f"/food/recommendations/{first['recommendation_id']}").json()["freshness"], "needs_recheck")
        self.assert_envelope(alice.post(f"/visits/{visit_id}/choice", {"recommendation_id": first["recommendation_id"], "expected_itinerary_version": 1}),
                             409, "VERSION_CONFLICT")
        self.assert_envelope(alice.post("/food/feedback", {"recommendation_id": first["recommendation_id"], "verdict": "liked", "dined_on": "2026-09-22"}),
                             422, "VALIDATION_FAILED")
        self.assertEqual(alice.get(f"/visits/{visit_id}").json()["place"]["name"], first["branch"]["name"])
        legs = chosen.json()["legs"]
        self.assertEqual(legs[0]["destination"]["name"], first["branch"]["name"], "去程终点改成新店")
        self.assertEqual(legs[-1]["origin"]["name"], first["branch"]["name"], "回程起点改成新店")
        self.assertEqual([l["times"] for l in legs], [l["times"] for l in snapshot["legs"]], "交通时间不为餐厅缩短")

        # ---- 寻味（主人模式）：用主人的时间与城市，反馈只修正偏好 ----
        owner = alice.post("/food/recommendations", {"mode": "owner_real_dining", "pet_id": alice.pet_id,
                                                     "owner_context": {"plan_date": "2026-09-22", "meal_time_local": "19:00", "timezone": "Asia/Hong_Kong", "city": "香港"}})
        self.assertEqual(owner.status_code, 200, owner.text)
        owner_first = owner.json()["items"][0]
        self.assertIsNone(owner_first["itinerary_version"])
        feedback = alice.post("/food/feedback", {"recommendation_id": owner_first["recommendation_id"], "verdict": "liked", "reasons": ["too_salty"], "dined_on": "2026-09-22"})
        self.assertEqual(feedback.status_code, 201, feedback.text)
        self.assertEqual(feedback.json()["verification"], "self_reported")

        # ---- 到店：活动、原创明信片（私有），宠物在店里 ----
        self.clock.advance(minutes=6)
        self.assertEqual(alice.home()["presence"], "visiting")
        visit = alice.get(f"/visits/{visit_id}").json()
        self.assertEqual(visit["state"], "active")
        drink = next(a for a in visit["activities"] if a["kind"] == "order_drink")
        photo_act = next(a for a in visit["activities"] if a["kind"] == "take_photo")
        self.assertEqual(alice.post(f"/visits/{visit_id}/actions", {"activity_id": drink["activity_id"]}).status_code, 200)
        after_photo = alice.post(f"/visits/{visit_id}/actions", {"activity_id": photo_act["activity_id"]}).json()
        self.assertIn("没有照片", next(a for a in after_photo["activities"] if a["kind"] == "take_photo")["result_text"], "未开启生成照片：纸质卡片，不冒充照片")
        thread = alice.get(f"/communicator/{alice.pet_id}/messages").json()
        postcard_url = next(m["photo_url"] for m in thread["items"] if m.get("photo_url"))
        photo_id = postcard_url.rsplit("/", 1)[-1]
        self.assertEqual(alice.get(f"/media/postcards/{photo_id}").status_code, 200)
        self.assertEqual(bob.get(f"/media/postcards/{photo_id}").status_code, 404, "公开发布前明信片只属于主人")

        # ---- 离店：真实世界事件生成动态（主人入住时同意公开） ----
        self.clock.advance(minutes=20)
        feed = bob.get("/circle/feed").json()["items"]  # 主人还没打开页面，别家也能看到到访结束后的动态
        self.assertTrue(any(p["author"]["actor_id"] == alice.pet_id for p in feed))
        self.assertEqual(alice.home()["presence"], "returning")
        post = next(p for p in feed if p["author"]["actor_id"] == alice.pet_id)
        self.assertEqual(post["visit_id"], visit_id)
        self.assertTrue(post["media"] and post["media"][0]["generated"])
        self.assertEqual(bob.get(f"/media/postcards/{photo_id}").status_code, 200, "随动态公开后可见")
        npc = bob.get(f"/posts/{post['post_id']}/comments").json()["items"]
        self.assertTrue(any(c["actor"]["actor_kind"] == "npc" for c in npc))
        reacted = bob.post(f"/posts/{post['post_id']}/reactions", {"as_actor": "pet"}).json()
        self.assertEqual(reacted["reaction_count"], 1)
        self.assertEqual(bob.post(f"/posts/{post['post_id']}/reactions", {"as_actor": "pet"}).json()["reaction_count"], 1, "换键重发也不重复点赞")
        self.assertTrue(reacted["viewer_reacted"])
        comment = bob.post(f"/posts/{post['post_id']}/comments", {"as_actor": "owner", "text": "好可爱"})
        self.assertEqual(comment.status_code, 201, comment.text)
        self.assertEqual(comment.json()["actor"]["actor_kind"], "owner")
        seen = alice.get(f"/posts/{post['post_id']}/comments").json()["items"]
        self.assertIn("好可爱", [c["text"] for c in seen])
        self.assertEqual(bob.post(f"/pets/{alice.pet_id}/follow", {"follow": True}).status_code, 204)
        profile = bob.get(f"/pets/{alice.pet_id}/profile")
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertEqual(profile.json()["follower_count"], 1)

        # ---- 回家：收藏（明信片 + 共同听看回忆），通讯有真实事件消息 ----
        self.clock.advance(minutes=7)
        home = alice.home()
        self.assertEqual(home["presence"], "at_home")
        self.assertIsNone(home["journey"])
        items = alice.get("/collection").json()
        kinds = sorted(i["kind"] for i in items)
        self.assertIn("postcard", kinds)
        self.assertIn("shared_memory", kinds)
        self.assertTrue(all(not i["tradable"] for i in items if i["kind"] != "seed"))
        self.assertEqual(alice.get("/journey/map").json()["lifecycle"], "completed")
        texts = [m["text"] for m in alice.get(f"/communicator/{alice.pet_id}/messages").json()["items"]]
        self.assertGreaterEqual(len(texts), 3)

        # ---- 屏蔽与举报 ----
        self.assertEqual(bob.post("/reports", {"target_kind": "post", "target_id": post["post_id"], "reason": "other"}).status_code, 204)
        self.assertEqual(bob.post("/blocks", {"post_id": post["post_id"]}).status_code, 204)
        self.assertFalse(any(p["author"]["actor_id"] == alice.pet_id for p in bob.get("/circle/feed").json()["items"]))


if __name__ == "__main__":
    unittest.main()
