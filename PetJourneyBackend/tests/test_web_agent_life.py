"""宠物自主世界第二阶段：TA 在家时菜园也可能被偷（醒着多半发现，打盹时几率低），并主动告诉主人。"""

from __future__ import annotations

import math
import unittest
from datetime import datetime, timedelta, timezone

from types import SimpleNamespace

import app.web_agent.life as life_module
from app.web_agent.life import choose
from app.web_home.place import HABITATS

from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase
from web_provider_fakes import REAL_CAFE, FakeGeo

HK_2AM = datetime(2026, 9, 22, 18, 0, tzinfo=timezone.utc)


class FarmWatchTests(WebPlatformTestBase):
    start = LUNCH_UTC

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(self.start).install(self)
        self.victim = self.user("watch-victim")
        self.victim.adopt_and_move_in("adopt-lan")
        self.victim.get("/session")
        self.thief = self.user("watch-thief")
        self.thief.adopt_and_move_in("adopt-pudding")

    def ripe_body(self) -> dict:
        self.clock.advance(seconds=181)
        view = self.thief.get(f"/homes/{self.victim.home_id}").json()
        ripe = next(p["plot"] for p in view["plots"] if p["plot"]["stage"] == "ripe")
        return {"home_id": self.victim.home_id, "plot_id": ripe["plot_id"], "cycle_id": ripe["cycle_id"]}, view

    def news(self) -> list[dict]:
        items = self.victim.get(f"/communicator/{self.victim.pet_id}/messages").json()["items"]
        return [m for m in items if m.get("topic") == "news"]

    def test_awake_pet_usually_catches_the_thief_and_tells_owner(self) -> None:
        body, view = self.ripe_body()
        self.assertEqual((view["guarded"], view["watch"]), (True, "pet_awake"))
        self.web.farm.catch_roll = lambda key: 0.5  # < 0.75：被发现
        self.assert_envelope(self.thief.post("/farm/steal", body), 409, "FARM_GUARDED")
        news = self.news()
        self.assertEqual(len(news), 1)
        self.assertIn("赶跑", news[0]["text"])

    def test_awake_pet_can_still_miss_one(self) -> None:
        body, _ = self.ripe_body()
        self.web.farm.catch_roll = lambda key: 0.9  # ≥ 0.75：没发现
        stolen = self.thief.post("/farm/steal", body)
        self.assertEqual(stolen.status_code, 200, stolen.text)
        self.assertIn("一不留神", stolen.json()["message"])


class NightWatchTests(FarmWatchTests):
    start = HK_2AM - timedelta(seconds=181)

    def test_awake_pet_usually_catches_the_thief_and_tells_owner(self) -> None:  # 夜里改测打盹
        body, view = self.ripe_body()
        self.assertEqual(view["watch"], "pet_resting")
        self.web.farm.catch_roll = lambda key: 0.2  # < 0.35：被惊醒
        self.assert_envelope(self.thief.post("/farm/steal", body), 409, "FARM_GUARDED")
        self.assertIn("迷迷糊糊", self.news()[0]["text"], "半夜也会告诉主人")

    def test_awake_pet_can_still_miss_one(self) -> None:
        body, _ = self.ripe_body()
        self.web.farm.catch_roll = lambda key: 0.5  # ≥ 0.35：睡着时被摘走
        stolen = self.thief.post("/farm/steal", body)
        self.assertEqual(stolen.status_code, 200, stolen.text)
        self.assertIn("打盹", stolen.json()["message"])
        self.assertIn("睡着", self.news()[0]["text"])


class HomePlaceAndDailyLifeTests(WebPlatformTestBase):
    settle_on_read = True  # 读接口已改为纯读：这组用例按“任务进程一直跟得上”验证（每次 GET 前先跑一轮后台）
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("home-sea")

    def move_in(self, habitat: str | None):
        owner = self.owner
        owner.post("/adoption/adopt", {"candidate_id": "adopt-lan"})
        home = owner.get("/onboarding").json()
        owner.pet_id, owner.home_id = home["pet_id"], home["home_id"]
        body = {"public_posts": False, **({"habitat": habitat} if habitat else {})}
        self.assertEqual(owner.post("/onboarding/move-in", body).status_code, 200)
        return owner

    def test_home_is_a_fuzzy_area_in_a_real_city(self) -> None:
        owner = self.move_in("seaside")
        view = owner.get("/home/place").json()
        place = view["place"]
        self.assertEqual((place["habitat"], place["habitat_label"], place["chosen"]), ("seaside", "海边", True))
        self.assertIn("·", place["display"])
        self.assertEqual(len(view["options"]), 8)
        self.assertEqual(owner.home()["place"]["display"], place["display"])
        area = next(a for _, (_, areas) in HABITATS.items() for a in areas if a.city == place["city"] and a.label == place["area_label"])
        with self.app.state.storage.connect() as conn:
            row = conn.execute("SELECT lat, lng FROM web_home_places WHERE home_id = ?", (owner.home_id,)).fetchone()
        offset = math.hypot((row["lat"] - area.lat) * 111_320, (row["lng"] - area.lng) * 111_320 * math.cos(math.radians(area.lat)))
        self.assertTrue(100 < offset < 1000, f"坐标已模糊处理：{offset:.0f} 米")
        again = owner.put("/home/place", {"habitat": "seaside"}).json()["place"]
        self.assertEqual(again["display"], place["display"], "同一类型重复提交，家保持不变")

    def test_daily_options_follow_the_habitat_and_work_pays_into_the_bank_card(self) -> None:
        owner = self.move_in("seaside")
        keys = {d["destination_key"] for d in owner.get("/journey/destinations").json()}
        self.assertTrue({"local:stroll", "local:cafe", "local:city_trip", "work:fishing_port"} <= keys)
        self.assertNotIn("work:ranch", keys, "海边没有牧场的活")
        self.assertNotIn("harbour_cafe", keys, "香港演示线路只给住在中环的宠物")
        self.assert_envelope(owner.post("/journey/depart", {"destination_key": "harbour_cafe"}), 404, "NOT_FOUND")
        before = owner.home()["wallet"]["balance"]
        snapshot = owner.post("/journey/depart", {"destination_key": "work:fishing_port"})
        self.assertEqual(snapshot.status_code, 200, snapshot.text)
        self.assert_envelope(owner.put("/home/place", {"habitat": "desert"}), 409, "CONFLICT")
        self.assertEqual(owner.home()["wallet"]["balance"], before, "打工不花钱")
        self.clock.advance(hours=4)
        home = owner.home()
        self.assertEqual(home["wallet"]["balance"], before + 28, "工钱进了银行卡")
        texts = [m["text"] for m in owner.get(f"/communicator/{owner.pet_id}/messages").json()["items"]]
        self.assertTrue(any("赚了 28" in t for t in texts), texts)
        kinds = [i["kind"] for i in owner.get("/collection").json()]
        self.assertNotIn("postcard", kinds, "打工不寄明信片")

    def test_stroll_uses_a_real_nearby_place_when_maps_are_available(self) -> None:
        owner = self.move_in("city")
        self.web.journeys.geo = FakeGeo(place=REAL_CAFE, minutes=9)
        legs = owner.post("/journey/depart", {"destination_key": "local:stroll"}).json()["legs"]
        self.assertEqual(legs[0]["time_basis"], "routed_estimate")
        self.assertEqual(legs[0]["destination"]["name"], REAL_CAFE.name)
        self.clock.advance(minutes=10)
        visit = owner.get(f"/visits/{owner.get('/journey/map').json()['current_visit_id']}").json()
        self.assertEqual((visit["place"]["provider"], visit["template"]), ("amap", "park"))
        self.assertEqual({a["kind"] for a in visit["activities"]}, {"choose_seat", "take_photo", "greet_resident"})


class PetAutonomyTests(WebPlatformTestBase):
    HK = timezone(timedelta(hours=8))

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(datetime(2026, 9, 23, 9, 5, tzinfo=self.HK).astimezone(timezone.utc)).install(self)
        self.owner = self.user("free-spirit")
        self.owner.adopt_and_move_in("adopt-lan")
        self.owner.put(f"/pets/{self.owner.pet_id}/dna", {"personality": "好奇、闲不住"})

    def force(self, value: float) -> None:
        original = life_module._roll
        life_module._roll = lambda *parts: value
        self.addCleanup(lambda: setattr(life_module, "_roll", original))

    def test_pet_goes_out_on_its_own_by_day_and_decides_once_per_slot(self) -> None:
        self.force(0.1)
        key = self.web.life.consider(self.owner.user_id, self.owner.pet_id, self.clock.now)
        self.assertIsNotNone(key, "白天、有精神、有钱：TA 自己出门")
        self.assertIsNotNone(self.owner.home()["journey"])
        self.assertIsNone(self.web.life.consider(self.owner.user_id, self.owner.pet_id, self.clock.now), "同一个半小时只决定一次")
        departed = [m for m in self.owner.get(f"/communicator/{self.owner.pet_id}/messages").json()["items"] if m["composed_by"] == "event"]
        self.assertTrue(departed, "出门会告诉主人")

    def test_no_outings_at_night(self) -> None:
        self.force(0.0)
        night = datetime(2026, 9, 23, 21, 0, tzinfo=self.HK).astimezone(timezone.utc)
        self.assertIsNone(self.web.life.consider(self.owner.user_id, self.owner.pet_id, night))

    def test_owner_saying_stay_home_is_taken_seriously(self) -> None:
        self.force(0.1)
        self.owner.post(f"/communicator/{self.owner.pet_id}/messages", {"client_message_id": "stay-home-01", "text": "今天别出门了，外面下雨"})
        self.assertIsNone(self.web.life.consider(self.owner.user_id, self.owner.pet_id, self.clock.now), "主人说别出门：多半就在家")

    def test_suggestion_is_heard_and_marked_when_followed(self) -> None:
        self.assert_envelope(self.owner.post("/journey/suggest", {"destination_key": "nowhere"}), 404, "NOT_FOUND")
        made = self.owner.post("/journey/suggest", {"destination_key": "local:cafe"}).json()
        self.assertEqual(made["status"], "pending")
        notes = [m["text"] for m in self.owner.get(f"/communicator/{self.owner.pet_id}/messages").json()["items"]]
        self.assertTrue(any("想想" in t for t in notes), notes)
        self.force(0.1)
        self.assertEqual(self.web.life.consider(self.owner.user_id, self.owner.pet_id, self.clock.now), "local:cafe")
        self.assertEqual(self.owner.get("/journey/suggestions").json()[0]["status"], "accepted")


class ChooseUnitTests(unittest.TestCase):
    def options(self, *pairs):
        return [SimpleNamespace(destination_key=k, fee=f) for k, f in pairs]

    def test_broke_pet_only_strolls_or_works(self) -> None:
        opts = self.options(("local:stroll", 0), ("local:cafe", 8), ("local:city_trip", 30), ("work:cafe_helper", 0))
        picks = {choose(opts, 3, "steady", suggested=set(), worked_today=False, long_trip_ok=set(), roll=r / 20) for r in range(20)}
        self.assertEqual(picks, {"local:stroll", "work:cafe_helper"})

    def test_suggestion_weighs_more_but_pet_still_decides(self) -> None:
        opts = self.options(("local:stroll", 0), ("local:cafe", 8), ("local:city_trip", 30))
        picks = [choose(opts, 100, "steady", suggested={"local:city_trip"}, worked_today=False, long_trip_ok=set(), roll=r / 100) for r in range(100)]
        self.assertGreater(picks.count("local:city_trip"), 50)
        self.assertIn("local:stroll", picks, "建议不是命令")


if __name__ == "__main__":
    unittest.main()
