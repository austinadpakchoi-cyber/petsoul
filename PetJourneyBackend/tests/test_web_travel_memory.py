"""旅程结束后的回忆页（T10）与出发时的逐条复核端口（合同 4.2，C 要的 `stale_facts_in`）。
真实迁移建库、真实插画服务、**假**研究端口与画师，0 次付费调用。

钉的是：只给**真实发生**的到访盖章（事件号 `<旅程>:visit_started`），顺路建议不盖；没到达就没有章；
回忆页复用计划页那张背景（画师不再被叫）；关联的心愿落定为 completed；事件重放同一个结果；
没有预研计划的老旅程不出回忆页（对照）。
`stale_facts_in` 在出发那个事务里判：有效期内返回空、过期返回那条、查不到的也返回（宁可挡下，不放行）。
"""

from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

from travel_wish_fakes import TravelJournalTestBase, TravelResearchTestBase, good_result

from app.utils import iso, utcnow
from app.web_platform.uow import unit_of_work
from app.web_travel.model import COMPLETED


class TravelMemoryTests(TravelJournalTestBase):
    def link(self, journey_id: str = "jr-1") -> None:
        with self.storage.connect() as conn:
            plan = self.wishes.ready_plan_in(conn, "pet-1")
        with unit_of_work(self.storage) as conn:
            self.wishes.link_journey_in(conn, plan.plan_id, plan.plan_revision, plan.wish_id, plan.wish_revision, journey_id)

    def returned(self, journey_id: str = "jr-1", *, visited: bool = True) -> None:
        self.journals.visit_of = lambda jid: SimpleNamespace(starts_at=utcnow() - timedelta(hours=2)) if visited else None
        self.journals.on_world_event(SimpleNamespace(kind="returned_home", journey=SimpleNamespace(journey_id=journey_id), visit=None,
                                                     occurred_at=utcnow()))

    def page(self, phase: str):
        (row,) = [r for r in self.journal_rows() if r["phase"] == phase]
        return row

    def test_only_the_real_visit_is_stamped_and_the_background_is_reused(self) -> None:
        self.publish()
        self.ills.run_pending()
        self.link()
        self.returned()
        self.returned()  # 事件重放

        plan_page, memory = self.page("plan"), self.page("memory")
        self.assertEqual(json.loads(memory["event_ids_json"]), ["jr-1:visit_started"])
        stamps = {s["name"]: s["visited_event_ids"] for s in json.loads(memory["layout_json"])["stations"]}
        self.assertEqual(stamps, {"浅水湾": ["jr-1:visit_started"], "赤柱": []}, "顺路建议没真去：不盖章")
        self.assertEqual(memory["image_task_id"], plan_page["image_task_id"], "回忆页复用计划页那张背景")
        self.assertEqual(len(self.painter.calls), 1, "没有为回忆页再画一张")
        self.assertEqual(self.wishes.read("pet-1").status, COMPLETED)
        self.assertEqual(len(self.journal_rows()), 2, "重放同一个结果")

    def test_a_trip_that_never_reached_its_destination_stamps_nothing(self) -> None:
        self.publish()
        self.link()
        self.returned(visited=False)
        memory = self.page("memory")
        self.assertEqual(json.loads(memory["event_ids_json"]), [])
        self.assertTrue(all(s["visited_event_ids"] == [] for s in json.loads(memory["layout_json"])["stations"]), "没去成：一个章都没有")

    def test_an_old_journey_without_a_plan_gets_no_memory_page(self) -> None:
        self.returned("jr-legacy")
        self.assertEqual(self.journal_rows(), [])


class TravelStaleFactsTests(TravelResearchTestBase):
    def test_expired_and_unknown_preconditions_are_found_inside_the_departure_transaction(self) -> None:
        now = utcnow()
        facts = tuple(replace(f, observed_at=None, valid_from=iso(now - timedelta(hours=1)), valid_until=iso(now + timedelta(hours=2)))
                      if f.key == "weather" else f for f in good_result().facts)
        self.port.result = replace(good_result(), facts=facts)
        self.propose()
        self.research.run_pending()
        with self.storage.connect() as conn:
            plan = self.wishes.ready_plan_in(conn, "pet-1")
        self.assertEqual(len(plan.preconditions), 1, "前提：带有效期的天气成了出发前置条件")

        with unit_of_work(self.storage) as conn:
            self.assertEqual(self.wishes.stale_facts_in(conn, plan.preconditions, now), ())
            self.assertEqual(self.wishes.stale_facts_in(conn, plan.preconditions, now + timedelta(hours=3)), plan.preconditions)
            self.assertEqual(self.wishes.stale_facts_in(conn, ("tf-missing",), now), ("tf-missing",), "查不到的也挡下")


if __name__ == "__main__":
    unittest.main()
