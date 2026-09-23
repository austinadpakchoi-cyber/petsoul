"""打工记录、生活时间线与可复用的攻略资料（对齐说明 §4、§9、§10）。"""

from __future__ import annotations

import json
import unittest
from datetime import timedelta

from app.web_providers import PlaceCandidate
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase
from web_provider_fakes import FakeChat, FakeGeo

GUIDE = json.dumps({"title": "港岛慢慢走", "summary": "喝杯咖啡再看海。", "owner_tips": ["带把伞"],
                    "stops": [{"name": "示例·海边咖啡馆（演示店）", "time": "上午", "why": "晒太阳", "tip": "以现场为准"},
                              {"name": "卜公码头", "time": "中午", "why": "看船", "tip": "注意防晒"},
                              {"name": "秘密花园", "time": "傍晚", "why": "听说很美", "tip": "以现场为准"}]}, ensure_ascii=False)


class LifeRecordTests(WebPlatformTestBase):
    settle_on_read = True  # 读接口已改为纯读：这组用例按“任务进程一直跟得上”验证（每次 GET 前先跑一轮后台）
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("life-records")

    def move_in(self, habitat: str | None = None) -> None:
        self.owner.post("/adoption/adopt", {"candidate_id": "adopt-lan"})
        state = self.owner.get("/onboarding").json()
        self.owner.pet_id, self.owner.home_id = state["pet_id"], state["home_id"]
        self.owner.post("/onboarding/move-in", {"public_posts": False, **({"habitat": habitat} if habitat else {})})

    def test_job_record_shows_status_and_salary_once_and_timeline_links_the_facts(self) -> None:
        self.move_in("seaside")
        self.owner.post("/journey/depart", {"destination_key": "work:fishing_port"})
        job = self.owner.get("/jobs").json()[0]
        self.assertEqual((job["status"], job["pay"], job["paid"]), ("going", 28, False))
        self.clock.advance(minutes=15)
        self.assertEqual(self.owner.get("/jobs").json()[0]["status"], "working")
        self.clock.advance(hours=4)
        self.owner.get("/journey/map")
        job = self.owner.get("/jobs").json()[0]
        self.assertEqual((job["status"], job["paid"]), ("done", True))
        self.owner.get("/journey/map")  # 重复读取不会重复发薪
        salaries = [i for i in self.owner.get("/timeline").json() if i["kind"] == "salary"]
        self.assertEqual(len(salaries), 1)
        self.assertIn("28", salaries[0]["title"])
        kinds = {i["kind"] for i in self.owner.get("/timeline").json()}
        self.assertTrue({"work", "home", "salary", "credential"} <= kinds, kinds)

    def test_guide_is_reusable_in_real_life_and_keeps_plan_apart_from_what_happened(self) -> None:
        self.move_in()
        geo = FakeGeo()
        geo.known = {"卜公码头": PlaceCandidate(provider="amap", place_id="amap:B0PIER", name="卜公码头", address="中环海滨", lat=22.285, lng=114.16,
                                                 category="景点", attribution="地点资料：高德地图")}
        self.web.guides.geo = geo
        self.web.guides.chat = FakeChat([GUIDE])
        self.owner.patch("/settings", {"model_replies": True})
        self.owner.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.run_background()  # 攻略由任务进程写（slow 通道）
        guide = self.owner.get("/guides").json()[0]
        pier = next(s for s in guide["stops"] if s["name"] == "卜公码头")
        self.assertIn("uri.amap.com/marker", pier["nav_url"])
        self.assertIn("coordinate=wgs84", pier["nav_url"])
        self.assertEqual(pier["copy_text"], "卜公码头｜中环海滨")
        secret = next(s for s in guide["stops"] if s["name"] == "秘密花园")
        self.assertIsNone(secret["nav_url"], "未核实的地点不给导航")
        self.assertEqual((guide["status"], guide["visited"], guide["coin_budget"]), ("in_progress", [], 8))
        self.assertIn("以现场为准", guide["real_budget_note"])
        self.clock.advance(minutes=10)
        self.assertEqual(self.owner.get("/guides").json()[0]["visited"], ["示例·海边咖啡馆（演示店）"], "到过的才算到过")
        self.clock.advance(hours=1)
        self.owner.get("/journey/map")
        self.assertEqual(self.owner.get("/guides").json()[0]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
