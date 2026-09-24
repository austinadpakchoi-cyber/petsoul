"""真实体验（0.4.0）：正式环境没有演示线路；港澳一日行按已核验船期与地图接驳；地点去演示化；任务租约、并发扣款、运行状态与重启不重复结算。"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone

from app.main import create_app
from app.schemas import EconomyTransactionType
from app.web_agent.ticker import WorldTicker
from app.web_economy import InsufficientFunds
from app.web_platform.lease import WorkerLease
from app.web_providers.geo import PlaceCandidate
from web_base import PREFIX, FakeClock, WebPlatformTestBase
from web_provider_fakes import FakeGeo

HK_MORNING = datetime(2026, 9, 23, 1, 0, tzinfo=timezone.utc)  # 香港 09:00
CAFE = PlaceCandidate(provider="amap", place_id="amap:TESTCAFE", name="测试老城咖啡", address="议事亭前地附近", lat=22.1937, lng=113.5391,
                      category="咖啡厅", attribution="地点资料：高德地图", fetched_at="2026-09-23T00:59:00Z")
SQUARE = PlaceCandidate(provider="amap", place_id="amap:TESTSQUARE", name="议事亭前地", address=None, lat=22.1935, lng=113.5393,
                        category="广场", attribution="地点资料：高德地图")


class MacauGeo(FakeGeo):
    def __init__(self, minutes: int = 8, fail: bool = False) -> None:
        super().__init__(place=CAFE, minutes=minutes, fail=fail)
        self.known = {"议事亭前地": SQUARE}

    def route(self, region, mode, origin, destination, max_age=None):
        if self.fail:
            return None
        return super().route(region, mode, origin, destination)


class RealModeBase(WebPlatformTestBase):
    demo_catalog = False

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(HK_MORNING).install(self)

    def owner(self, name: str, geo=None, coins: int = 200):
        user = self.user(name)
        user.upload_pet("小海", "cat")
        user.move_in()
        if geo is not None:
            self.web.journeys.geo = geo
        self.web.economy.apply(user.pet_id, coins - 20, EconomyTransactionType.web_reward, f"test:grant:{user.pet_id}", reason="测试补给", source="test")
        return user


class RealTransportTests(RealModeBase):
    settle_on_read = True  # 读接口已改为纯读：这组用例按“任务进程一直跟得上”验证（每次 GET 前先跑一轮后台）
    def test_formal_environment_has_no_demo_lines(self) -> None:
        user = self.owner("real-a", MacauGeo())
        options = {o["destination_key"]: o for o in user.get("/journey/destinations").json()}
        self.assertNotIn("harbour_cafe", options)
        self.assertNotIn("tokyo_flight", options)
        ferry = options["macau_ferry"]
        self.assertEqual(ferry["time_basis"], "verified_timetable")
        self.assertTrue(ferry["available"])
        self.assertIn("TurboJET", ferry["reference_note"])
        self.assertIn("与星币无关", ferry["reference_note"], "现实参考票价与星币旅费分开")

    def test_day_trip_plans_backwards_from_verified_sailing(self) -> None:
        user = self.owner("real-b", MacauGeo())
        before = user.home()["wallet"]["balance"]
        response = user.post("/journey/depart", {"destination_key": "macau_ferry"})
        self.assertEqual(response.status_code, 200, response.text)
        snapshot = response.json()
        legs = snapshot["legs"]
        ferry_out = next(l for l in legs if l["mode"] == "ferry" and l["kind"] == "main")
        # 09:00 决定出发：打车 8 分钟 + 登船 30 分钟 → 最早赶上 10:00（香港时间 02:00 UTC）那一班；出门时间反推为 09:22
        self.assertEqual(ferry_out["times"]["planned_departure_utc"][:16], "2026-09-23T02:00")
        self.assertEqual(ferry_out["time_basis"], "verified_timetable")
        self.assertEqual(ferry_out["time_source"], "verified_timetable")
        self.assertEqual(ferry_out["reference"]["reference_id"], "turbojet-hk-macau-outer-2026-02-11:hk_to_macau:2026-09-23:10:00")
        self.assertIn("TurboJET", ferry_out["reference"]["source_label"])
        self.assertEqual(ferry_out["world_service"]["carrier_name"], "海獭轮渡")
        self.assertEqual(ferry_out["world_service"]["reference_id"], ferry_out["reference"]["reference_id"], "动物世界编号追溯到参考班次")
        taxi = legs[0]
        self.assertEqual(taxi["time_basis"], "routed_estimate")
        self.assertIn("高德", taxi["reference"]["source_label"])
        self.assertEqual(taxi["times"]["planned_departure_utc"][:16], "2026-09-23T01:22")
        wait = next(l for l in legs if l["kind"] == "wait" and l["origin"]["node_id"] == "hub:hk-macau-ferry-terminal")
        self.assertIn("30 分钟", wait["reference"]["source_label"])
        ferry_back = [l for l in legs if l["mode"] == "ferry" and l["kind"] == "main"][1]
        self.assertTrue(ferry_back["reference"]["reference_id"].startswith("turbojet-hk-macau-outer-2026-02-11:macau_to_hk:2026-09-23:"))
        wait_back = [l for l in legs if l["kind"] == "wait"][1]
        self.assertGreaterEqual((datetime.fromisoformat(wait_back["times"]["planned_arrival_utc"]) -
                                 datetime.fromisoformat(wait_back["times"]["planned_departure_utc"])).total_seconds(), 30 * 60)
        # 旅费按星币扣一次；出门时间没到之前 TA 在家收拾
        self.assertEqual(user.home()["wallet"]["balance"], before - 40)
        self.assertEqual(user.home()["presence"], "at_home")
        self.clock.advance(minutes=23)
        self.assertEqual(user.home()["presence"], "in_transit")
        # 同一班船的另一只宠物共用同一个动物世界编号
        other = self.owner("real-c", MacauGeo())
        other_ferry = next(l for l in other.post("/journey/depart", {"destination_key": "macau_ferry"}).json()["legs"] if l["mode"] == "ferry" and l["kind"] == "main")
        if other_ferry["reference"]["reference_id"] == ferry_out["reference"]["reference_id"]:
            self.assertEqual(other_ferry["world_service"]["world_service_id"], ferry_out["world_service"]["world_service_id"])
        with self.web.journeys.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_transport_reference_trips WHERE reference_id = ?", (ferry_out["reference"]["reference_id"],)).fetchone()
        self.assertEqual(row["source_url"], "https://www.turbojet.com.hk/en/routing-sailing-schedule/hong-kong-macau/sailing-schedule-fares")
        # 船票：从同一份行程签发
        self.clock.advance(minutes=1)
        tickets = [c for c in user.get("/credentials").json() if c["kind"] == "transport_ticket" and c.get("credential_id")]
        self.assertEqual(len(tickets), 2)
        self.assertTrue(all("海獭轮渡" in t["title"] for t in tickets))

    def test_plan_preview_shows_sources_without_charging(self) -> None:
        user = self.owner("real-preview", MacauGeo())
        before = user.home()["wallet"]["balance"]
        plan = user.get("/journey/plan?destination_key=macau_ferry")
        self.assertEqual(plan.status_code, 200, plan.text)
        body = plan.json()
        self.assertEqual(body["leave_home_at"][:16], "2026-09-23T01:22")
        ferry = next(l for l in body["legs"] if l["mode"] == "ferry" and l["kind"] == "main")
        self.assertTrue(ferry["reference_id"].endswith(":hk_to_macau:2026-09-23:10:00"))
        self.assertEqual(ferry["reference_fare"]["currency"], "HKD")
        self.assertEqual(ferry["reference_fare"]["amount"], 175, "周三日间经济位")
        self.assertIn("星币", " ".join(body["notes"]))
        self.assertEqual(body["venue"]["provider"], "amap")
        self.assertEqual(user.home()["wallet"]["balance"], before, "预览不扣钱")
        self.assertEqual(user.get("/journey/map").status_code, 404, "预览不生成行程")
        with self.web.journeys.storage.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM web_world_services").fetchone()["n"], 0, "预览不分配动物世界编号")

    def test_scheduled_trip_is_replanned_with_fresh_traffic_or_cancelled(self) -> None:
        geo = MacauGeo()
        user = self.owner("real-replan", geo)
        journey_id = user.post("/journey/depart", {"destination_key": "macau_ferry"}).json()["journey_id"]  # 09:00 决定：09:22 出门，坐 10:00 的船
        geo.minutes = 40  # 出门前路况变差：去码头要 40 分钟
        self.clock.advance(minutes=10)
        self.assertEqual(self.web.journeys.refresh_scheduled(self.clock.now, stale_after=timedelta(minutes=5)), 1, "出门前按最新路况复核")
        snapshot = user.get("/journey/map").json()
        self.assertEqual(snapshot["itinerary_version"], 2)
        ferry = next(l for l in snapshot["legs"] if l["mode"] == "ferry" and l["kind"] == "main")
        self.assertTrue(ferry["reference"]["reference_id"].endswith(":hk_to_macau:2026-09-23:10:30"), "赶不上 10:00，改坐 10:30")
        self.assertEqual(snapshot["legs"][0]["times"]["planned_departure_utc"][:16], "2026-09-23T01:20")
        notes = [m for m in user.get(f"/communicator/{user.pet_id}/messages").json()["items"] if m["channel"] == "family" and "改成" in m["text"]]
        self.assertEqual(len(notes), 1)
        self.assertEqual(self.web.journeys.refresh_scheduled(self.clock.now, stale_after=timedelta(minutes=5)), 0, "同一行程版本只复核一次")
        before = user.home()["wallet"]["balance"]
        geo.fail = True  # 完全拿不到路况：来不及了
        self.assertEqual(self.web.journeys.replan(journey_id, self.clock.now), "cancelled")
        self.assertEqual(user.home()["wallet"]["balance"], before + 40, "取消的行程退回旅费")
        self.assertEqual(user.home()["presence"], "at_home")

    def test_late_night_plans_next_morning_across_midnight(self) -> None:
        self.clock.now = datetime(2026, 9, 23, 14, 0, tzinfo=timezone.utc)  # 香港 22:00：当天已经来不及往返
        user = self.owner("real-night", MacauGeo())
        legs = user.post("/journey/depart", {"destination_key": "macau_ferry"}).json()["legs"]
        ferry_out = next(l for l in legs if l["mode"] == "ferry" and l["kind"] == "main")
        # 默认作息 07:30 起床：07:30 那班要 06:52 出门（TA 还在睡），所以排在 TA 醒着能赶上的 08:30 那班、07:52 出门
        self.assertTrue(ferry_out["reference"]["reference_id"].endswith(":hk_to_macau:2026-09-24:08:30"), ferry_out["reference"]["reference_id"])
        self.assertEqual(legs[0]["times"]["planned_departure_utc"][:16], "2026-09-23T23:52")
        self.assertEqual(user.home()["presence"], "at_home", "出门时间是第二天早上，今晚在家")

    def test_asleep_pet_is_not_sent_out_immediately(self) -> None:
        self.clock.now = datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc)  # 香港 00:00，默认作息在睡觉
        user = self.owner("real-asleep", MacauGeo())
        asleep = user.post("/journey/depart", {"destination_key": "local:stroll"})
        self.assertEqual(asleep.status_code, 409, asleep.text)
        self.assertEqual(asleep.json()["error"]["details"]["reason"], "pet_asleep")
        self.assertEqual(user.post("/journey/suggest", {"destination_key": "local:stroll"}).status_code, 200, "可以先留建议")

    def test_real_service_failure_returns_explicit_status_without_charging(self) -> None:
        user = self.owner("real-fail", MacauGeo(fail=True))
        before = user.home()["wallet"]["balance"]
        failed = user.post("/journey/depart", {"destination_key": "macau_ferry"})
        self.assertEqual(failed.status_code, 409, failed.text)
        self.assertEqual(failed.json()["error"]["details"]["reason"], "transport_unavailable")
        self.assertEqual(failed.json()["error"]["details"]["unavailable_reason"], "route_unavailable")
        self.assertEqual(user.home()["wallet"]["balance"], before, "没出发就不扣钱")
        self.assertEqual(user.get("/journey/map").status_code, 404, "没有生成任何行程")

    def test_without_map_local_life_uses_world_places_and_real_trips_are_unavailable(self) -> None:
        user = self.owner("real-nomap")
        self.web.journeys.geo = None
        options = {o["destination_key"]: o for o in user.get("/journey/destinations").json()}
        self.assertFalse(options["macau_ferry"]["available"])
        self.assertFalse(options["local:city_trip"]["available"])
        self.assertEqual(options["local:stroll"]["time_basis"], "world_rule")
        stroll = user.post("/journey/depart", {"destination_key": "local:stroll"}).json()
        self.assertEqual(stroll["legs"][0]["time_basis"], "routed_estimate", "time_basis 只有四个大类：星球内路程算“估算”")
        self.assertEqual(stroll["legs"][0]["time_source"], "world_rule")
        self.assertEqual(stroll["legs"][0]["freshness"], "unavailable", "没有现实资料")
        self.assertIn("星球", stroll["legs"][0]["reference"]["source_label"])
        visit = user.get(f"/visits/{stroll['planned_visit_id']}").json()
        self.assertEqual(visit["place"]["provider"], "world")
        self.assertNotIn("示例", visit["place"]["name"])
        self.assertIn("星球内", visit["place"]["attribution"])
        city = user.post("/journey/depart", {"destination_key": "local:city_trip"})
        self.assertEqual(city.json()["error"]["details"]["reason"], "already_traveling")

    def test_demo_food_samples_are_not_served_in_formal_environment(self) -> None:
        user = self.owner("real-food", MacauGeo())
        response = user.post("/food/recommendations", {"pet_id": user.pet_id, "mode": "owner_real_dining"})
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["error"]["details"]["capability"], "food.recommendations")
        meta = self.client.get(f"{PREFIX}/meta").json()
        food = next(c for c in meta["capabilities"] if c["key"] == "food.recommendations")
        self.assertEqual(food["status"], "not_configured")

    def test_stale_timetable_is_not_used_as_verified(self) -> None:
        import dataclasses
        from datetime import date
        from unittest import mock

        from app.web_transport.timetable import load_timetable

        stale = dataclasses.replace(load_timetable("turbojet_hk_macau_outer"), recheck_by=date(2026, 9, 22))  # 复核期限已过
        user = self.owner("real-stale", MacauGeo())
        with mock.patch("app.web_journey.planning.load_timetable", return_value=stale), mock.patch("app.web_transport.daytrip.load_timetable", return_value=stale):
            ferry = next(o for o in user.get("/journey/destinations").json() if o["destination_key"] == "macau_ferry")
            self.assertFalse(ferry["available"])
            self.assertIn("复核", ferry["unavailable_reason"])
            failed = user.post("/journey/depart", {"destination_key": "macau_ferry"})
        self.assertEqual(failed.json()["error"]["details"]["unavailable_reason"], "timetable_needs_recheck")


class RuntimeSafetyTests(RealModeBase):
    def test_only_one_process_advances_the_world(self) -> None:
        runs: list[str] = []
        first = WorldTicker([("a", lambda now: runs.append("first"))], interval_seconds=30)
        second = WorldTicker([("a", lambda now: runs.append("second"))], interval_seconds=30)
        first.lease = WorkerLease(self.web.journeys.storage, "test-world", timedelta(seconds=90), "embedded")
        second.lease = WorkerLease(self.web.journeys.storage, "test-world", timedelta(seconds=90), "worker")
        self.assertTrue(first.tick())
        self.assertFalse(second.tick(), "别的进程持有租约时跳过")
        self.clock.advance(seconds=91)
        self.assertTrue(second.tick(), "持有者挂了、租约过期后接手")
        self.assertFalse(first.tick())
        self.assertEqual(runs, ["first", "second"])

    def test_concurrent_debits_never_go_negative_or_lose_updates(self) -> None:
        user = self.owner("wallet-race", coins=100)
        errors: list[str] = []

        def spend(i: int) -> None:
            try:
                self.web.economy.apply(user.pet_id, -15, EconomyTransactionType.web_travel_fee, f"test:race:{i}", reason="并发扣款", source="test")
            except InsufficientFunds:
                errors.append("insufficient")

        threads = [threading.Thread(target=spend, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        balance = self.web.economy.wallet(user.pet_id).balance
        self.assertEqual(balance, 100 - 15 * 6)
        self.assertEqual(len(errors), 4)
        with self.web.journeys.storage.connect() as conn:
            charged = conn.execute("SELECT COUNT(*) AS n FROM economy_transactions WHERE idempotency_key LIKE 'test:race:%'").fetchone()["n"]
        self.assertEqual(charged, 6)

    def test_restart_does_not_pay_twice(self) -> None:
        user = self.owner("worker-restart", MacauGeo())
        job = user.post("/journey/depart", {"destination_key": "work:post_office"})
        self.assertEqual(job.status_code, 200, job.text)
        self.clock.advance(hours=4)
        self.web.ticker.tick(self.clock.now)
        restarted = create_app(self.settings)  # 同一份数据库再起一个进程（重启 / 独立任务进程）
        restarted.state.web.ticker.lease.holder = "restarted"
        self.clock.advance(minutes=5)
        restarted.state.web.ticker.tick(self.clock.now)
        self.web.ticker.tick(self.clock.now)
        with self.web.journeys.storage.connect() as conn:
            paid = conn.execute("SELECT after_json, before_json FROM economy_transactions WHERE type = 'web_job_income' AND pet_id = ?", (user.pet_id,)).fetchall()
            done = conn.execute("SELECT COUNT(*) AS n FROM web_messages WHERE pet_id = ? AND text LIKE '%干完啦%'", (user.pet_id,)).fetchone()["n"]
        self.assertEqual(len(paid), 1, "工钱只入账一次")
        self.assertEqual(json.loads(paid[0]["after_json"])["travel_coin"] - json.loads(paid[0]["before_json"])["travel_coin"], 24)
        self.assertEqual(done, 1, "“干完啦”只发一次")
        # 余额不直接比较：白天跑完一轮世界任务后，TA 可能自己又出门花了钱（这是自主生活，不是重复结算）

    def test_ops_status_reports_environment_and_is_local_only(self) -> None:
        status = self.client.get(f"{PREFIX}/ops/status")
        self.assertEqual(status.status_code, 200, status.text)
        body = status.json()
        self.assertEqual(body["environment"], "dev")
        self.assertFalse(body["providers_enabled"])
        self.assertTrue(all(p["state"] == "disabled" for p in body["providers"]))
        self.assertIn(body["world"]["runner"], ("embedded", "off", "worker"))
        self.assertEqual(body["frontend"]["data_mode"], "live")
        self.assertNotIn("secret", status.text.lower())
        proxied = self.client.get(f"{PREFIX}/ops/status", headers={"X-Forwarded-For": "203.0.113.9"})
        self.assertEqual(proxied.status_code, 403)
        token = self.client.get(f"{PREFIX}/ops/status", headers={"X-Forwarded-For": "203.0.113.9", "X-Admin-Token": "admin-test-token"})
        self.assertEqual(token.status_code, 200)


if __name__ == "__main__":
    import unittest

    unittest.main()
