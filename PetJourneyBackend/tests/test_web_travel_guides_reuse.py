"""已有预研计划的出发：旧攻略链只关联复用（TRV-03；方案 §13；T08）。真实迁移建库、真实插画服务与攻略服务、**假**模型与画师，0 次付费调用。

钉的是：出发事务里关联了计划的旅程，`departed` 到来时**不再调旧攻略的模型、也不请求新手账图**——
按计划派生一份攻略（`composed_by="plan"`），图就是计划那一页手账的图；事件重放同一个结果；
**对照**：没有预研计划的老旅程照旧走原路（调一次模型、请求一张手账图）。
"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from travel_wish_fakes import TravelJournalTestBase

from app.utils import utcnow
from app.web_journey.guides import TravelGuideService
from app.web_platform.uow import unit_of_work


class CountingChat:
    """**假的**模型：只数被叫了几次。"""

    available = True

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages, **kwargs):
        self.calls += 1
        return SimpleNamespace(text=json.dumps({"title": "一日小攻略", "summary": "去海边。", "owner_tips": ["以现场为准"],
                                                "stops": [{"name": "浅水湾", "time": "上午", "why": "看海", "tip": "带水"}]}, ensure_ascii=False))


class TravelGuideReuseTests(TravelJournalTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.guides = TravelGuideService(self.storage)
        self.chat = CountingChat()
        self.guides.chat = self.chat
        self.guides.model_enabled = lambda user_id: True
        self.legacy_images: list[dict] = []
        self.guides.image_request = lambda **kwargs: self.legacy_images.append(kwargs) or None
        self.guides.image_outcome_in = lambda conn, task_id: self.ills.outcome_of(task_id, conn)

    def depart(self, journey_id: str = "jr-1") -> None:
        journey = SimpleNamespace(journey_id=journey_id, user_id="user-1", pet_id="pet-1", city="香港", title="去浅水湾",
                                  destination_key="hk-repulse-bay", fee=30, lifecycle="active")
        visit = SimpleNamespace(place={"name": "浅水湾", "timezone": "Asia/Hong_Kong", "provider": "fixture"}, starts_at=utcnow())
        self.guides.on_world_event(SimpleNamespace(kind="departed", journey=journey, visit=visit, occurred_at=utcnow()))

    def link(self, journey_id: str = "jr-1"):
        """C 的出发事务里做的那一步（这里直接调端口）。"""
        with self.storage.connect() as conn:
            plan = self.wishes.ready_plan_in(conn, "pet-1")
        with unit_of_work(self.storage) as conn:
            self.wishes.link_journey_in(conn, plan.plan_id, plan.plan_revision, plan.wish_id, plan.wish_revision, journey_id)
        return plan

    def guide_rows(self):
        return self.query("SELECT * FROM web_travel_guides ORDER BY created_at")

    def test_a_departure_with_a_researched_plan_reuses_it_and_calls_nothing(self) -> None:
        self.publish()
        self.link()
        self.depart()
        self.depart()  # 事件重放、进程恢复

        (guide,) = self.guide_rows()
        self.assertEqual(guide["composed_by"], "plan")
        self.assertEqual((self.chat.calls, self.legacy_images), (0, []), "旧攻略的模型与手账图一次都没调")
        self.assertEqual(guide["image_task_id"], self.journal_rows()[0]["image_task_id"], "图就是计划那一页手账的")
        self.assertEqual([s["name"] for s in json.loads(guide["stops_json"])], ["浅水湾", "赤柱"])
        self.assertEqual(json.loads(guide["owner_tips_json"]), ["坐 6 路巴士去", "记得带水"])
        (listed,) = self.guides.list("user-1", "pet-1")
        self.assertEqual((listed["composed_by"], listed["title"]), ("plan", "去看海"), "老的攻略读法照常能读")

    def test_an_old_journey_without_a_plan_keeps_the_legacy_path(self) -> None:
        """对照：没有预研计划的老旅程——照旧调一次模型、请求一张手账图（兼容路径保留）。"""
        self.depart("jr-old")
        (guide,) = self.guide_rows()
        self.assertNotEqual(guide["composed_by"], "plan")
        self.assertEqual((self.chat.calls, len(self.legacy_images)), (1, 1))


if __name__ == "__main__":
    unittest.main()
