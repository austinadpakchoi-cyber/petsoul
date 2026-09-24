"""`GET /travel/plans/{plan_id}`（TRV-00 §23.4；I 的路由把 A 的只读视图组装成 `TravelPlan`）。

走真实的「提出心愿 → 研究（**假**端口，0 次付费）→ 发布计划 → 手账」，再从真接口读：
  · 每一版都给、`current_revision` 指最新那一版；站点、提醒、来源、逐条事实都在；
  · 手账页带它**自己的**时间（不是拿计划的时间顶替）；
  · 导航链接只给核实过且有坐标的站点（后端给，前端不自己拼）；
  · 关联了真实行程时，`fare` 是标价、`fare_waived` 说有没有用券（合同 §30），这一步 join 的是 C 的行程；
  · 别人家的计划、不存在的计划都回同一个 404。
"""

from __future__ import annotations

import unittest

from travel_wish_fakes import SEA, FakeResearchPort

from app.web_platform.budget import BudgetLedger
from web_base import WebPlatformTestBase


class TravelPlanRouteTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = self.user("plan-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        research = self.web.travel.research
        research.port = FakeResearchPort()
        research.ledger = BudgetLedger(self.app.state.storage)  # 研究是付费步骤：端口与额度账本必须成对（A 的 fail-closed）
        self.web.travel.wishes.propose(pet_id=self.owner.pet_id, user_id=self.owner.user_id, trigger_event_id="evt-plan-1",
                                       candidates=[SEA], selected=0, interest_tags=["sea"], owner_reason="上次聊到想看海", funds_goal=None)
        research.run_pending()
        self.plan_id = self.web.travel.wishes.read(self.owner.pet_id).plan_id
        self.assertIsNotNone(self.plan_id, "前提：计划真的发布了")

    def read(self, user=None, plan_id=None, **params):
        user = user or self.owner
        return user.get(f"/travel/plans/{plan_id or self.plan_id}", params={"pet_id": params.get("pet_id", self.owner.pet_id)})

    def test_the_published_plan_is_assembled_from_the_view(self) -> None:
        response = self.read()
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body["plan_id"], body["current_revision"], [r["plan_revision"] for r in body["revisions"]]), (self.plan_id, 1, [1]))
        revision = body["revisions"][0]
        self.assertEqual([(s["name"], s["role"]) for s in revision["stops"]], [("浅水湾", "main"), ("赤柱", "suggested")])
        self.assertEqual([t["text"] for t in revision["owner_tips"]], ["坐 6 路巴士去", "记得带水"])
        self.assertEqual(revision["pet_id"], self.owner.pet_id)
        self.assertIsNone(revision["operation_id"], "研究 operation 号不下发（A 的视图本来就不给）")
        self.assertTrue(revision["facts"] and revision["sources"])
        self.assertIsNone(revision["journey"], "还没成行")

    def test_nav_links_only_for_verified_stops_with_coordinates(self) -> None:
        for stop in self.read().json()["revisions"][0]["stops"]:
            with self.subTest(stop=stop["name"]):
                expected = bool(stop["verified"] and stop["lat"] is not None)
                self.assertEqual(stop["nav_url"] is not None, expected)
                if expected:
                    self.assertIn("uri.amap.com", stop["nav_url"])

    def test_each_journal_page_carries_its_own_time(self) -> None:
        journals = self.read().json()["revisions"][0]["journals"]
        self.assertTrue(journals, "前提：发布时建了计划页手账")
        with self.app.state.storage.connect() as conn:
            rows = {r["journal_id"]: r["created_at"] for r in conn.execute("SELECT journal_id, created_at FROM web_travel_journals")}
        for page in journals:
            with self.subTest(page=page["journal_id"]):
                self.assertEqual(page["phase"], "plan")
                self.assertTrue(page["created_at"].startswith(rows[page["journal_id"]][:19]), "手账页用它自己那一行的时间")
                self.assertTrue(page["template_revision"])

    def test_a_linked_journey_shows_its_list_price_and_whether_a_voucher_was_used(self) -> None:
        departed = self.owner.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.assertEqual(departed.status_code, 200, departed.text)
        with self.app.state.storage.connect() as conn:
            journey = conn.execute("SELECT journey_id, fee, fare_waived FROM web_journeys WHERE pet_id = ?", (self.owner.pet_id,)).fetchone()
            conn.execute("UPDATE web_travel_plans SET journey_id = ? WHERE plan_id = ?", (journey["journey_id"], self.plan_id))  # 模拟 C 的关联
        summary = self.read().json()["revisions"][0]["journey"]
        self.assertEqual(summary, {"journey_id": journey["journey_id"], "fare": journey["fee"], "fare_waived": bool(journey["fare_waived"])})

    def test_someone_elses_plan_and_a_missing_plan_are_the_same_404(self) -> None:
        stranger = self.user("plan-stranger")
        stranger.adopt_and_move_in("adopt-mochi")
        foreign = self.read(user=stranger, pet_id=stranger.pet_id)
        missing = self.read(plan_id="tp-no-such-plan")
        for response in (foreign, missing):
            with self.subTest(status=response.status_code):
                self.assertEqual(response.status_code, 404, response.text)
                self.assertEqual(response.json()["error"]["details"]["reason"], "plan_not_found")
        self.assertNotIn("浅水湾", foreign.text)


if __name__ == "__main__":
    unittest.main()
