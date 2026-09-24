"""计划的只读视图 `journals.plan_view_in`（TRV-03；给 I 的 /travel/plans 路由）。真实迁移建库、真实插画服务、**假**研究端口与画师，0 次付费调用。

钉的是：页面要的都在（站点、提醒、来源、逐条事实与结论、这一版的手账页和图的状态）；**私有的不在**（给主人的理由、平台 API 费、研究 operation 号）；
不是这只宠物的计划读不到；默认取当前那一版，可以指定旧版，没有的版本读不到；还没发布计划的心愿没有视图；旅程结束后回忆页带着真实到访的章。
"""

from __future__ import annotations

import json
import unittest
from dataclasses import asdict, fields, is_dataclass
from datetime import timedelta
from types import SimpleNamespace

from travel_wish_fakes import TravelJournalTestBase, good_result

from app.utils import utcnow
from app.web_platform.uow import unit_of_work


def _field_names(value) -> set[str]:
    """视图里所有 dataclass 的字段名（递归）。"""
    names: set[str] = set()
    if is_dataclass(value):
        for item in fields(value):
            names.add(item.name)
            names |= _field_names(getattr(value, item.name))
    elif isinstance(value, (tuple, list)):
        for item in value:
            names |= _field_names(item)
    return names


class TravelPlanViewTests(TravelJournalTestBase):
    def view(self, pet_id: str = "pet-1", plan_revision=None):
        plan_id = self.query("SELECT plan_id FROM web_travel_wishes")[0]["plan_id"]
        with self.storage.connect() as conn:
            return self.journals.plan_view_in(conn, pet_id, plan_id, plan_revision)

    def test_the_view_carries_what_the_page_needs_and_nothing_private(self) -> None:
        self.port.result = good_result(cost_amount=0.03, cost_currency="USD")
        self.publish()
        self.ills.run_pending()
        view = self.view()

        self.assertEqual((view.current_revision, view.revisions, view.revision.plan_revision), (1, (1,), 1))
        page = view.revision
        self.assertEqual([(s.name, s.role, s.visited_event_ids) for s in page.stops], [("浅水湾", "main", ()), ("赤柱", "suggested", ())])
        self.assertEqual([t.text for t in page.tips], ["坐 6 路巴士去", "记得带水"])
        self.assertEqual(sorted((f.category, f.verdict) for f in page.facts),
                         [("destination_identity", "verified"), ("feature", "verified"), ("route", "verified"), ("weather", "verified")])
        self.assertEqual({s.source_id for s in page.sources}, {"s-map", "s-weather", "s-web"})
        (journal,) = page.journals
        self.assertEqual((journal.phase, journal.plan_revision, journal.image.status), ("plan", 1, "ready"))
        self.assertTrue(journal.image.url)

        body = json.dumps(asdict(view), ensure_ascii=False, default=str)
        for private in ("合成标记", "USD", "travel_research:"):
            self.assertNotIn(private, body, "给主人的理由、平台 API 费、研究 operation 号都不进视图")
        self.assertFalse({"cost_amount", "cost_currency", "operation_id", "owner_reason"} & _field_names(view))

    def test_another_pets_plan_reads_as_missing(self) -> None:
        self.publish()
        self.assertIsNone(self.view(pet_id="pet-2"), "不是这只宠物的计划：当不存在")
        self.assertIsNotNone(self.view(), "对照：自己的计划读得到")

    def test_the_current_revision_is_the_default_and_an_older_one_can_be_read(self) -> None:
        self.publish()
        self.research.retry(self.wishes.read("pet-1").wish_id, self.wishes.read("pet-1").wish_revision)
        self.research.run_pending()

        current, older = self.view(), self.view(plan_revision=1)
        self.assertEqual((current.current_revision, current.revisions, current.revision.plan_revision), (2, (1, 2), 2))
        self.assertEqual((older.current_revision, older.revision.plan_revision), (2, 1))
        self.assertEqual([j.plan_revision for j in older.revision.journals], [1], "手账页跟着那一版走")
        self.assertIsNone(self.view(plan_revision=9), "没有的版本读不到")

    def test_a_wish_without_a_published_plan_has_no_view(self) -> None:
        self.propose()
        self.assertIsNone(self.view())

    def test_after_the_trip_the_memory_page_is_listed_with_its_real_stamp(self) -> None:
        self.publish()
        with self.storage.connect() as conn:
            plan = self.wishes.ready_plan_in(conn, "pet-1")
        with unit_of_work(self.storage) as conn:
            self.wishes.link_journey_in(conn, plan.plan_id, plan.plan_revision, plan.wish_id, plan.wish_revision, "jr-1")
        self.journals.visit_of = lambda journey_id: SimpleNamespace(starts_at=utcnow() - timedelta(hours=2))
        self.journals.on_world_event(SimpleNamespace(kind="returned_home", journey=SimpleNamespace(journey_id="jr-1"), visit=None,
                                                     occurred_at=utcnow()))

        page = self.view().revision
        self.assertEqual((page.journey_id, [j.phase for j in page.journals]), ("jr-1", ["plan", "memory"]))
        self.assertEqual(page.journals[1].event_ids, ("jr-1:visit_started",))
        self.assertTrue(all(s.visited_event_ids == () for s in page.stops), "计划页的站点永远不盖章，章在回忆页")

    def test_each_page_carries_its_own_times_and_template(self) -> None:
        """I 挂 /travel/plans 用：手账页的时间、身份说明、模板号都取自己那一行。回忆页建得晚，时间不能拿计划页的顶替。"""
        self.publish()
        with self.storage.connect() as conn:
            plan = self.wishes.ready_plan_in(conn, "pet-1")
        with unit_of_work(self.storage) as conn:
            self.wishes.link_journey_in(conn, plan.plan_id, plan.plan_revision, plan.wish_id, plan.wish_revision, "jr-1")
        self.journals.visit_of = lambda journey_id: SimpleNamespace(starts_at=utcnow())
        self.journals.on_world_event(SimpleNamespace(kind="returned_home", journey=SimpleNamespace(journey_id="jr-1"), visit=None,
                                                     occurred_at=utcnow() + timedelta(hours=1)))

        rows = {r["phase"]: r for r in self.journal_rows()}
        plan_page, memory_page = self.view().revision.journals
        for journal in (plan_page, memory_page):
            row = rows[journal.phase]
            self.assertEqual((journal.created_at, journal.updated_at, journal.identity_note, journal.template_revision),
                             (row["created_at"], row["updated_at"], row["identity_note"], row["template_revision"]))
        self.assertNotEqual(memory_page.created_at, plan_page.created_at, "回忆页有自己的时间")
        self.assertEqual(plan_page.template_revision, "t1")


if __name__ == "__main__":
    unittest.main()
