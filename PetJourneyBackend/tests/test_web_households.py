"""家庭共同照顾与多宠物（0.4.0）：一只宠物一个家庭；一个家庭多位成员、多只宠物；邀请、隔离、移除、并发、访客与待领养居民。"""

from __future__ import annotations

import threading
from datetime import timedelta

from app.web_residents import SYSTEM_USER
from web_base import LUNCH_UTC, PREFIX, FakeClock, WebPlatformTestBase, WebUser


class HouseholdTestBase(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)

    def register(self, name: str, entry: dict | None = None) -> WebUser:
        user = WebUser.__new__(WebUser)
        from fastapi.testclient import TestClient

        user.client = TestClient(self.app)
        body = {"username": name, "password": "longpassword1"}
        if entry is not None:
            body["entry"] = entry
        response = user.client.post(f"{PREFIX}/auth/register", json=body)
        self.assertEqual(response.status_code, 201, response.text)
        user.user_id = response.json()["user"]["user_id"]
        user.pet_id = None
        user.home_id = None
        return user

    def two_pet_family(self) -> tuple[WebUser, str, str, str]:
        """A 建立家庭：先接自己的猫入住，再把领养的伙伴加进同一个家并入住。返回 (A, 猫, 领养伙伴, household_id)。"""
        a = self.user("family-a")
        first = a.upload_pet("年糕", "cat").json()["pet_id"]
        a.move_in()
        household_id = a.get("/households").json()[0]["household_id"]
        second = a.post("/adoption/adopt", {"candidate_id": "adopt-lan", "household_id": household_id})
        self.assertEqual(second.status_code, 200, second.text)
        second_id = second.json()["pet_id"]
        moved = a.post("/onboarding/move-in", {"pet_id": second_id})
        self.assertEqual(moved.status_code, 200, moved.text)
        return a, first, second_id, household_id

    def invite(self, admin: WebUser, household_id: str, role: str = "caregiver", hint: str | None = "妈妈") -> str:
        response = admin.post(f"/households/{household_id}/invites", {"role": role, "relation_hint": hint, "ttl_hours": 24})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["token"]


class RegistrationEntryTests(HouseholdTestBase):
    def test_register_does_not_force_a_pet_and_keeps_selected_companion_for_confirmation(self) -> None:
        resident = next(c for c in self.client.get(f"{PREFIX}/public/residents").json() if c["candidate_id"] == "adopt-mochi")
        user = self.register("visitor-mochi", {"kind": "adopt", "pet_id": resident["pet_id"]})
        state = user.get("/onboarding").json()
        self.assertEqual(state["step"], "needs_companion", "注册不强制建立宠物")
        self.assertEqual(state["households"], [])
        self.assertEqual(state["entry"]["kind"], "adopt")
        self.assertEqual(state["entry"]["pending_adoption"]["pet_id"], resident["pet_id"])
        self.assertTrue(state["entry"]["pending_adoption"]["available"])
        # 没有自动领养：候选仍然可以领养
        self.assertEqual(next(c for c in user.get("/adoption/candidates").json() if c["candidate_id"] == "adopt-mochi")["availability"], "available")
        adopted = user.post("/adoption/adopt", {"candidate_id": "adopt-mochi"})
        self.assertEqual(adopted.status_code, 200, adopted.text)
        self.assertEqual(adopted.json()["pet_id"], resident["pet_id"], "领养保留居民原来的 pet_id")
        self.assertIsNone(user.get("/onboarding").json()["entry"], "确认领养后入口处理完毕")

    def test_browse_entry_and_invalid_invite_token_do_not_leak(self) -> None:
        user = self.register("visitor-browse", {"kind": "invite", "invite_token": "x" * 32})
        state = user.get("/onboarding").json()
        self.assertEqual(state["entry"]["kind"], "invite")
        self.assertIsNone(state["entry"]["pending_invite"], "无效令牌只记入口，不透露令牌是否存在过")


class MultiPetHouseholdTests(HouseholdTestBase):
    def test_two_pets_share_one_home_but_live_separately(self) -> None:
        a, cat, companion, household_id = self.two_pet_family()
        # 同一个家：两只宠物的 home_id 相同；欢迎旅费每个家只发一次（给第一只）
        cat_home = a.get(f"/home?pet_id={cat}").json()
        companion_home = a.get(f"/home?pet_id={companion}").json()
        self.assertEqual(cat_home["home_id"], companion_home["home_id"])
        self.assertEqual({p["pet_id"] for p in cat_home["pets"]}, {cat, companion})
        self.assertEqual(cat_home["wallet"]["balance"], 20)
        self.assertEqual(companion_home["wallet"]["balance"], 0, "后加进家的宠物不再领欢迎旅费")
        # 没有“全局当前宠物”：照顾不止一只时不指明 → 409 pet_required
        body = self.assert_envelope(a.get("/home"), 409, "CONFLICT")
        self.assertEqual(body["error"]["details"]["reason"], "pet_required")
        # 各自的证件与账户
        cards = {c["kind"]: c for c in a.get(f"/credentials?pet_id={companion}").json()}
        self.assertTrue(cards["identity_card"]["credential_id"])
        self.assertNotEqual(cards["identity_card"]["number"],
                            {c["kind"]: c for c in a.get(f"/credentials?pet_id={cat}").json()}["identity_card"]["number"])
        # 一只出门、一只在家：守护只算在家的那只
        gone = a.post(f"/journey/depart?pet_id={cat}", {"destination_key": "local:stroll"})
        self.assertEqual(gone.status_code, 200, gone.text)
        snapshot = a.get(f"/home?pet_id={companion}").json()
        self.assertEqual(snapshot["presence"], "at_home")
        self.assertEqual(snapshot["guard"]["guarding_pets"], [companion])
        self.assertIn(a.get(f"/home?pet_id={cat}").json()["presence"], ("in_transit", "visiting"))
        # 另一只照样可以自己出门（并行）
        second = a.post(f"/journey/depart?pet_id={companion}", {"destination_key": "local:stroll"})
        self.assertEqual(second.status_code, 200, second.text)
        self.assertFalse(a.get(f"/home?pet_id={cat}").json()["guard"]["guarding"])

    def test_adding_a_pet_to_someone_elses_household_is_refused(self) -> None:
        a, _, _, household_id = self.two_pet_family()
        outsider = self.user("outsider")
        refused = outsider.post("/adoption/adopt", {"candidate_id": "adopt-lizi", "household_id": household_id})
        self.assert_envelope(refused, 404, "NOT_FOUND")
        self.assertEqual(next(c for c in outsider.get("/adoption/candidates").json() if c["candidate_id"] == "adopt-lizi")["availability"], "available")


class InviteAndMembershipTests(HouseholdTestBase):
    def test_invited_member_shares_life_but_private_chats_stay_private(self) -> None:
        a, cat, companion, household_id = self.two_pet_family()
        token = self.invite(a, household_id)
        b = self.register("family-b", {"kind": "invite", "invite_token": token})
        pending = b.get("/onboarding").json()["entry"]["pending_invite"]
        self.assertEqual(sorted(pending["pet_names"]), sorted(["年糕", "小岚"]))
        self.assertFalse(pending["already_member"])
        self.assertEqual(b.get("/onboarding").json()["step"], "needs_companion", "邀请只是入口，确认前不会自动加入")
        joined = b.post("/invites/accept", {"token": token})
        self.assertEqual(joined.status_code, 200, joined.text)
        self.assertEqual(joined.json()["household"]["household_id"], household_id)
        self.assertEqual(b.post("/invites/accept", {"token": token}).status_code, 200, "同一个人重复确认返回同一结果")
        state = b.get("/onboarding").json()
        self.assertEqual(state["step"], "active")
        self.assertIsNone(state["entry"])
        # 称呼只是称呼：B 是共同照顾者，不能改家庭设置
        self.assertEqual(b.get(f"/pets/{cat}/relationship").json()["relation_label"], "妈妈")
        self.assert_envelope(b.patch(f"/households/{household_id}/settings", {"public_posts": True}), 403, "FORBIDDEN")
        # 私聊各自的；世界事件来信在家庭频道，两个人都看得到
        b.post(f"/communicator/{cat}/messages", {"client_message_id": "b-private-0001", "text": "我是 B，今天想你了"})
        a_thread = a.get(f"/communicator/{cat}/messages").json()["items"]
        self.assertFalse(any("我是 B" in m["text"] for m in a_thread), "别的家人的私聊看不到")
        a.post(f"/journey/depart?pet_id={cat}", {"destination_key": "local:stroll"})
        a_family = [m for m in a.get(f"/communicator/{cat}/messages").json()["items"] if m["channel"] == "family"]
        b_family = [m for m in b.get(f"/communicator/{cat}/messages").json()["items"] if m["channel"] == "family"]
        self.assertTrue(a_family)
        self.assertEqual([m["message_id"] for m in a_family], [m["message_id"] for m in b_family], "同一件事全家只有一条")
        # 用过的邀请不能再用
        c = self.user("family-c")
        self.assertEqual(c.post("/invites/accept", {"token": token}).json()["error"]["details"]["reason"], "invite_used")

    def test_removed_member_loses_access_immediately_and_last_admin_is_kept(self) -> None:
        a, cat, _, household_id = self.two_pet_family()
        token = self.invite(a, household_id)
        b = self.user("family-b2")
        b.post("/invites/accept", {"token": token})
        self.assertEqual(b.get(f"/home?pet_id={cat}").status_code, 200)
        self.assertEqual(a.delete(f"/households/{household_id}/members/{b.user_id}").status_code, 204)
        self.assert_envelope(b.get(f"/home?pet_id={cat}"), 404, "NOT_FOUND")
        self.assert_envelope(b.get(f"/communicator/{cat}/messages"), 404, "NOT_FOUND")
        self.assertEqual(b.get("/onboarding").json()["step"], "needs_companion")
        left = a.delete(f"/households/{household_id}/members/{a.user_id}")
        self.assertEqual(left.json()["error"]["details"]["reason"], "last_admin")
        demote = a.put(f"/households/{household_id}/members/{a.user_id}/role", {"role": "caregiver"})
        self.assertEqual(demote.json()["error"]["details"]["reason"], "last_admin")

    def test_revoked_and_expired_invites(self) -> None:
        a, _, _, household_id = self.two_pet_family()
        token = self.invite(a, household_id)
        invite_id = a.get(f"/households/{household_id}/invites").json()[0]["invite_id"]
        self.assertEqual(a.delete(f"/households/{household_id}/invites/{invite_id}").json()["status"], "revoked")
        b = self.user("family-b3")
        self.assert_envelope(b.post("/invites/accept", {"token": token}), 404, "NOT_FOUND")
        late = self.invite(a, household_id)
        self.clock.advance(hours=25)
        self.assertEqual(b.post("/invites/accept", {"token": late}).json()["error"]["details"]["reason"], "invite_expired")

    def test_caregiver_spending_follows_household_setting(self) -> None:
        a, cat, _, household_id = self.two_pet_family()
        b = self.user("family-b4")
        b.post("/invites/accept", {"token": self.invite(a, household_id)})
        a.patch(f"/households/{household_id}/settings", {"caregivers_can_spend": False})
        self.assert_envelope(b.post(f"/journey/depart?pet_id={cat}", {"destination_key": "local:cafe"}), 403, "FORBIDDEN")
        self.assertEqual(b.post(f"/journey/suggest?pet_id={cat}", {"destination_key": "local:cafe"}).status_code, 200, "建议不花钱，照顾者可以提")
        a.patch(f"/households/{household_id}/settings", {"caregivers_can_spend": True})
        self.assertEqual(b.post(f"/journey/depart?pet_id={cat}", {"destination_key": "local:cafe"}).status_code, 200)

    def test_shared_dna_rejects_stale_writes_and_keeps_personal_titles(self) -> None:
        a, cat, _, household_id = self.two_pet_family()
        b = self.user("family-b5")
        b.post("/invites/accept", {"token": self.invite(a, household_id)})
        first = a.put(f"/pets/{cat}/dna", {"personality": "爱晒太阳", "owner_title": "姐姐"}).json()
        version = first["version"]
        second = b.client.put(f"{PREFIX}/pets/{cat}/dna?expected_version={version}", json={"personality": "爱晒太阳，也爱睡觉", "owner_title": "妈妈"},
                              headers={"X-CSRF-Token": b.csrf})
        self.assertEqual(second.status_code, 200, second.text)
        stale = a.client.put(f"{PREFIX}/pets/{cat}/dna?expected_version={version}", json={"personality": "覆盖家人的修改"}, headers={"X-CSRF-Token": a.csrf})
        self.assertEqual(stale.json()["error"]["details"]["reason"], "dna_version_conflict")
        self.assertEqual(a.get(f"/pets/{cat}/dna").json()["dna"]["owner_title"], "姐姐", "称呼是每位家人各自的")
        self.assertEqual(b.get(f"/pets/{cat}/dna").json()["dna"]["owner_title"], "妈妈")
        self.assertEqual(a.get(f"/pets/{cat}/dna").json()["dna"]["personality"], "爱晒太阳，也爱睡觉")


class ExclusivityAndFarmTests(HouseholdTestBase):
    def test_simultaneous_adoption_has_one_winner(self) -> None:
        users = [self.user(f"racer-{i}") for i in range(4)]
        results: list[int] = []

        def race(user: WebUser) -> None:
            results.append(user.post("/adoption/adopt", {"candidate_id": "adopt-pudding"}).status_code)

        threads = [threading.Thread(target=race, args=(u,)) for u in users]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(results), [200, 409, 409, 409])
        with self.web.pets.storage.connect() as conn:
            households = conn.execute("SELECT COUNT(*) AS n FROM web_household_pets hp JOIN web_residents r ON r.pet_id = hp.pet_id "
                                      "WHERE r.candidate_id = 'adopt-pudding'").fetchone()["n"]
        self.assertEqual(households, 1, "同一只宠物只属于一个家庭")

    def test_each_household_can_take_from_a_crop_once(self) -> None:
        victim = self.user("farm-victim")
        victim.adopt_and_move_in("adopt-arong")
        a, cat, companion, household_id = self.two_pet_family()
        b = self.user("family-b6")
        b.post("/invites/accept", {"token": self.invite(a, household_id)})
        victim.post("/journey/depart", {"destination_key": "local:stroll"})  # 受害家里没有宠物在家
        self.clock.advance(minutes=4)
        plot = next(p for p in victim.home()["plots"] if p["stage"] == "ripe")
        body = {"home_id": victim.home_id, "plot_id": plot["plot_id"], "cycle_id": plot["cycle_id"]}
        taken = a.post(f"/farm/steal?household_id={household_id}", body)
        self.assertEqual(taken.status_code, 200, taken.text)
        again = b.post(f"/farm/steal?household_id={household_id}", body)
        self.assertEqual(again.json()["error"]["details"]["reason"], "already_taken", "每批作物每个家庭只能摘一次")
        own = a.post(f"/farm/steal?household_id={household_id}", {"home_id": a.get(f"/home?pet_id={cat}").json()["home_id"], "plot_id": "x", "cycle_id": "y"})
        self.assertEqual(own.json()["error"]["details"]["reason"], "own_home")


class VisitorAndResidentTests(HouseholdTestBase):
    def test_visitors_see_resident_life_without_private_data(self) -> None:
        world = self.client.get(f"{PREFIX}/public/world")
        self.assertEqual(world.status_code, 200, world.text)
        body = world.json()
        self.assertEqual({e["route"] for e in body["entries"]}, {"browse", "own_pet", "adopt", "invite"})
        self.assertGreaterEqual(body["living_residents"], 8)
        resident = body["residents"][0]
        self.assertTrue(resident["residence"].startswith("星球居民驿站"))
        self.assertEqual(resident["presence"], "at_home")
        page = self.client.get(f"{PREFIX}/public/pets/{resident['pet_id']}").json()
        self.assertTrue(page["adoptable"])
        # 家庭里的私密宠物对访客 404；公开内容里没有任何家庭成员或私密字段
        owner = self.user("private-owner")
        owner.upload_pet("小私", "cat")
        owner.move_in(public_posts=False)
        self.assertEqual(self.client.get(f"{PREFIX}/public/pets/{owner.pet_id}").status_code, 404)
        text = world.text
        for secret in ("user_id", "household_id", "wallet", "owner_title"):
            self.assertNotIn(secret, text)

    def test_visitor_rate_limit_counts_each_visitor_behind_the_proxy(self) -> None:
        from app.routers.web import public

        original = public.RATE_PER_MINUTE
        public.RATE_PER_MINUTE = 3
        self.addCleanup(setattr, public, "RATE_PER_MINUTE", original)
        first = [self.client.get(f"{PREFIX}/public/residents", headers={"X-Forwarded-For": "203.0.113.1"}).status_code for _ in range(4)]
        other = self.client.get(f"{PREFIX}/public/residents", headers={"X-Forwarded-For": "203.0.113.2"}).status_code
        self.assertEqual(first, [200, 200, 200, 429], "同一位访客超过额度")
        self.assertEqual(other, 200, "代理后面的另一位访客不受影响")

    def test_resident_lives_before_adoption_and_does_not_teleport(self) -> None:
        resident = next(c for c in self.client.get(f"{PREFIX}/public/residents").json() if c["candidate_id"] == "adopt-doudou")
        pet_id = resident["pet_id"]
        home = self.web.residents.home_of(pet_id)
        journey = self.web.journeys.depart(SYSTEM_USER, pet_id, home.home_id, "local:stroll", self.clock.now)
        self.assertEqual(journey.pet_id, pet_id)
        public = self.client.get(f"{PREFIX}/public/pets/{pet_id}").json()
        self.assertIn(public["resident"]["presence"], ("in_transit", "visiting"), "访客能看到居民正在外面")
        user = self.user("adopter")
        adopted = user.post("/adoption/adopt", {"candidate_id": "adopt-doudou"})
        self.assertEqual(adopted.json()["pet_id"], pet_id)
        blocked = user.post("/onboarding/move-in", {"pet_id": pet_id})
        self.assertEqual(blocked.json()["error"]["details"]["reason"], "pet_away", "还在外面的居民不会瞬移进新家")
        self.clock.advance(hours=3)
        moved = user.post("/onboarding/move-in", {"pet_id": pet_id})
        self.assertEqual(moved.status_code, 200, moved.text)
        with self.web.pets.storage.connect() as conn:
            row = conn.execute("SELECT status, moved_home_at FROM web_residents WHERE pet_id = ?", (pet_id,)).fetchone()
        self.assertEqual(row["status"], "adopted")
        self.assertIsNotNone(row["moved_home_at"])
        timeline = user.get(f"/timeline?pet_id={pet_id}").json()
        self.assertTrue(any(item["ref_id"] == journey.journey_id for item in timeline), "领养前在星球上的经历保留")
        self.assertEqual(self.client.get(f"{PREFIX}/public/pets/{pet_id}").status_code, 200, "居民本来就是公开主页")
        self.assertNotIn(pet_id, [r["pet_id"] for r in self.client.get(f"{PREFIX}/public/residents").json()])

    def test_residents_go_out_on_their_own_during_the_day(self) -> None:
        """待领养居民领养前就自己过日子：白天按作息和余额决定出门（从驿站出发、回驿站），访客页看得到；不调用模型与生图。"""
        self.clock.now = LUNCH_UTC.replace(hour=1, minute=0)  # 香港 09:00
        gone = set()
        for _ in range(16):  # 一个白天里每半小时考虑一次
            for user_id, pet_id in self.web.life.activated_pets():
                if user_id == SYSTEM_USER and self.web.life.consider(user_id, pet_id, self.clock.now):
                    gone.add(pet_id)
            self.clock.advance(minutes=30)
            self.web.journeys.advance_all(self.clock.now)
        self.assertTrue(gone, "至少有一位居民白天自己出了门")
        pet_id = sorted(gone)[0]
        journey = self.web.journeys.repo.latest_for_pet(pet_id)
        self.assertTrue(journey.home_id.startswith("res-"), "从星球居民驿站出发")
        self.assertEqual(journey.user_id, SYSTEM_USER, "建档身份是驿站，不是某位用户")
        self.assertIsNotNone(self.client.get(f"{PREFIX}/public/pets/{pet_id}").json().get("resident"))
        with self.web.journeys.storage.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM web_messages WHERE pet_id = ?", (pet_id,)).fetchone()["n"], 0, "居民没有家庭频道")
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM web_tasks").fetchone()["n"], 0, "没有排队任何生图任务")

    def test_new_homes_only_open_supported_areas(self) -> None:
        user = self.user("habitat-owner")
        user.upload_pet("沙沙", "cat")
        refused = user.post("/onboarding/move-in", {"habitat": "desert"})
        self.assertEqual(refused.json()["error"]["details"]["reason"], "habitat_not_supported")
        moved = user.post("/onboarding/move-in", {"habitat": "seaside"})
        self.assertEqual(moved.status_code, 200, moved.text)
        place = user.get("/home/place").json()
        self.assertEqual(place["place"]["city"], "香港")
        self.assertEqual({o["habitat"] for o in place["options"] if o["open"]}, {"seaside", "city"})

    def test_logout_and_login_keep_everything(self) -> None:
        a, cat, companion, household_id = self.two_pet_family()
        before = {p: a.get(f"/home?pet_id={p}").json() for p in (cat, companion)}
        a.post("/auth/logout")
        self.assertEqual(a.get("/home").status_code, 401)
        login = a.client.post(f"{PREFIX}/auth/login", json={"username": "family-a", "password": "longpassword1"})
        self.assertEqual(login.status_code, 200, login.text)
        for pet_id, snapshot in before.items():
            after = a.get(f"/home?pet_id={pet_id}").json()
            self.assertEqual(after["home_id"], snapshot["home_id"])
            self.assertEqual(after["wallet"]["balance"], snapshot["wallet"]["balance"])
            self.assertEqual(len(after["pets"]), 2)


if __name__ == "__main__":
    import unittest

    unittest.main()
