"""旅行心愿的持久层与命令端口（TRV-03；合同 4.1、4.2、5.2、11.1、11.6）。真实迁移建库、不联网、0 次付费调用。

钉的是：表名与键照合同（Q 按表查痕迹）；同一有效事件重复投递不新增心愿与研究（T02）；每宠同时只有一个进行中的心愿；
研究任务与心愿同生共死；暂停的宠物不形成心愿；生活侧与研究侧的等待原因互不覆盖；版本条件；C 的关联幂等且带条件；
取消作废在排的研究；读接口不写库。
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from task_budget_helpers import open_storage

from app.web_platform.tasks import WebTaskQueue
from app.web_platform.uow import unit_of_work
from app.web_travel import store
from app.web_travel.model import (
    ACTIVE, CANCELLED, LINKED, MISSING_FUNDS, READY, RESEARCH_PENDING, VersionConflict, WishRejected,
)
from app.web_travel.service import RESEARCH_KIND, TravelWishService

SEA = {"destination_key": "hk-repulse-bay", "name": "浅水湾", "city": "香港"}
PARK = {"destination_key": "hk-victoria-park", "name": "维多利亚公园", "city": "香港"}


class TravelStoreTestBase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.storage = open_storage(str(Path(tmp.name) / "travel.sqlite3"))
        self.tasks = WebTaskQueue(self.storage)
        self.wishes = TravelWishService(self.storage, self.tasks)

    def propose(self, trigger: str = "evt-1", pet_id: str = "pet-1", **overrides):
        kwargs = {"pet_id": pet_id, "user_id": "user-1", "trigger_event_id": trigger, "candidates": [SEA, PARK], "selected": 0,
                  "interest_tags": ["sea", "quiet"], "owner_reason": "我想去海边听一会儿浪。", "funds_goal": 120}
        kwargs.update(overrides)
        return self.wishes.propose(**kwargs)

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self.storage.connect() as conn:
            return conn.execute(sql, params).fetchall()

    def research_tasks(self) -> list[sqlite3.Row]:
        return self.query("SELECT * FROM web_tasks WHERE kind = ? ORDER BY created_at", (RESEARCH_KIND,))

    def publish_plan(self, ref, revision: int = 1) -> int:
        """替研究链落一版计划（本文件只测端口；研究本身在 test_web_travel_research.py）。"""
        with unit_of_work(self.storage) as conn:
            row = store.wish_in(conn, ref.wish_id)
            store.insert_plan_in(conn, {"plan_id": row["plan_id"], "plan_revision": revision, "wish_id": ref.wish_id, "wish_revision_at_build": row["wish_revision"],
                                        "pet_id": row["pet_id"], "destination_key": row["destination_key"], "title": "看海", "summary": "去看海。",
                                        "stops_json": "[]", "owner_tips_json": "[]", "preconditions_json": "[]", "sources_json": "[]",
                                        "created_at": "2026-09-24T00:00:00+00:00"})
            return self.wishes.set_research_waiting_in(conn, row, [], "2026-09-24T00:00:00+00:00", plan_revision=revision)


class TravelSchemaTests(TravelStoreTestBase):
    def test_the_migration_creates_the_five_tables_with_the_contract_names(self) -> None:
        """合同 11.6：Q 按表名查痕迹，改名得先回报 I。键与版本列按 11.1。"""
        tables = {row["name"] for row in self.query("SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'web_travel_%'")}
        self.assertTrue({"web_travel_wishes", "web_travel_plans", "web_travel_facts", "web_travel_research_receipts", "web_travel_journals"} <= tables)
        columns = {table: {row["name"] for row in self.query(f"PRAGMA table_info({table})")} for table in tables}
        self.assertTrue({"wish_id", "wish_revision", "pet_id", "status", "reconsider_after"} <= columns["web_travel_wishes"])
        self.assertEqual({row["name"] for row in self.query("PRAGMA table_info(web_travel_considerations)")},
                         {"pet_id", "last_considered_at", "updated_at"}, "上次考虑按宠物存：没有心愿也要挡冷却")
        self.assertNotIn("last_considered_at", columns["web_travel_wishes"], "一份口径：不挂在心愿行上")
        self.assertNotIn("next_review_at", columns["web_travel_wishes"], "合同 5.4：那是心跳的列")
        self.assertTrue({"plan_id", "plan_revision", "wish_id", "wish_revision_at_build", "journey_id"} <= columns["web_travel_plans"])
        self.assertTrue({"receipt_id", "operation_id", "plan_id", "plan_revision", "status", "attempt_no", "tool_executions",
                         "tool_execution_ids_json"} <= columns["web_travel_research_receipts"])
        self.assertTrue({"journal_id", "journal_revision", "plan_id", "plan_revision", "phase", "image_task_id", "visual_digest"}
                        <= columns["web_travel_journals"])
        self.assertNotIn("image_status", columns["web_travel_journals"], "手账图状态以插画记录为准，不另存一份")


class TravelWishPortTests(TravelStoreTestBase):
    def test_the_same_event_delivered_twice_makes_one_wish_and_one_research(self) -> None:
        """T02：同一有效事件重复投递（重复 tick、进程恢复重放）不新增心愿、不多排研究。"""
        first, again = self.propose(), self.propose()
        self.assertTrue(first.created)
        self.assertEqual((again.created, again.wish_id, again.wish_revision), (False, first.wish_id, 1))
        self.assertEqual(len(self.query("SELECT * FROM web_travel_wishes")), 1)
        self.assertEqual([row["dedupe_key"] for row in self.research_tasks()], [f"{RESEARCH_KIND}:{first.wish_id}:1"])

    def test_a_pet_has_one_open_wish_until_it_is_closed(self) -> None:
        first = self.propose("evt-1")
        other = self.propose("evt-2", candidates=[PARK], selected=0)
        self.assertEqual((other.created, other.wish_id), (False, first.wish_id), "已有进行中的心愿：原样返回，不新建")
        self.wishes.cancel(first.wish_id, first.wish_revision)
        fresh = self.propose("evt-3", candidates=[PARK], selected=0)
        self.assertTrue(fresh.created)
        self.assertEqual(len(self.research_tasks()), 2)

    def test_the_research_task_lives_and_dies_with_the_wish(self) -> None:
        """研究在 propose 的同一事务里登记：调用方回滚，两样都不留下。"""
        with self.assertRaises(RuntimeError):
            with unit_of_work(self.storage) as conn:
                self.wishes.propose_in(conn, pet_id="pet-1", user_id="user-1", trigger_event_id="evt-1", candidates=[SEA], selected=0,
                                       interest_tags=[], owner_reason="想去。", funds_goal=None)
                raise RuntimeError("B 的决策事务在后面失败了")
        self.assertEqual((len(self.query("SELECT * FROM web_travel_wishes")), len(self.research_tasks())), (0, 0))

    def test_a_paused_pet_forms_no_wish(self) -> None:
        """合同 4.5：复用运行时的暂停谓词，不再读一次那一列。"""
        self.wishes.paused_in = lambda conn, pet_id: pet_id == "pet-1"
        with self.assertRaises(WishRejected):
            self.propose()
        self.assertEqual((len(self.query("SELECT * FROM web_travel_wishes")), len(self.research_tasks())), (0, 0))

    def test_bad_commands_are_refused_before_anything_is_written(self) -> None:
        cases = {"四个候选": {"candidates": [SEA, PARK, SEA, PARK]}, "选中越界": {"selected": 2}, "标签不是代码": {"interest_tags": ["我想去"]},
                 "负数金币": {"funds_goal": -1}, "空理由": {"owner_reason": "  "}}
        for label, override in cases.items():
            with self.subTest(label):
                with self.assertRaises(WishRejected):
                    self.propose(**override)
        self.wishes.interest_whitelist = frozenset({"sea"})
        with self.assertRaises(WishRejected):
            self.propose(interest_tags=["quiet"])
        self.assertEqual(len(self.query("SELECT * FROM web_travel_wishes")), 0)


class TravelWaitingTests(TravelStoreTestBase):
    def test_life_side_reasons_never_erase_research_side_ones(self) -> None:
        """B 写钱，A 写研究：两份并存，页面拿到并集；缺钱时说清目标与现有游戏金币（合同 5.2）。"""
        ref = self.propose()
        updated = self.wishes.update_waiting(ref.wish_id, ref.wish_revision, [MISSING_FUNDS], "2026-09-25T00:00:00+00:00", "2026-09-24T00:00:00+00:00",
                                           current_coins=30)
        view = self.wishes.read("pet-1")
        self.assertEqual(view.waiting_reasons, (MISSING_FUNDS, RESEARCH_PENDING))
        self.assertEqual((view.target_coins, view.current_coins, view.reconsider_after, view.last_considered_at),
                         (120, 30, "2026-09-25T00:00:00+00:00", "2026-09-24T00:00:00+00:00"))
        self.assertEqual((updated.wish_revision, view.status), (2, ACTIVE))

    def test_b_cannot_write_research_reasons_and_stale_revisions_conflict(self) -> None:
        ref = self.propose()
        with self.assertRaises(WishRejected):
            self.wishes.update_waiting(ref.wish_id, ref.wish_revision, [RESEARCH_PENDING], None, None)
        self.wishes.update_waiting(ref.wish_id, ref.wish_revision, [], None, None)
        with self.assertRaises(VersionConflict):
            self.wishes.update_waiting(ref.wish_id, ref.wish_revision, [MISSING_FUNDS], None, None)

    def test_ready_needs_a_plan_and_no_reason_left_on_either_side(self) -> None:
        ref = self.propose()
        self.wishes.update_waiting(ref.wish_id, ref.wish_revision, [MISSING_FUNDS], None, None, current_coins=0)
        self.publish_plan(ref)
        self.assertEqual(self.wishes.read("pet-1").status, ACTIVE, "研究好了，但还在等钱")
        with self.storage.connect() as conn:
            self.assertIsNone(self.wishes.ready_plan_in(conn, "pet-1"), "不是 ready 就不给 C 可出发的计划")
        view = self.wishes.read("pet-1")
        self.wishes.update_waiting(ref.wish_id, view.wish_revision, [], None, None)
        self.assertEqual(self.wishes.read("pet-1").status, READY)


    def test_consideration_is_kept_per_pet_even_without_a_wish(self) -> None:
        """合同 17.1：DS 决定留在家、没形成心愿的那一轮也要记——否则这只宠物每一轮都会再问一次大脑，而且没人发现。"""
        with unit_of_work(self.storage) as conn:
            self.wishes.considered_in(conn, "pet-9", "2026-09-24T08:00:00+00:00")
            self.wishes.considered_in(conn, "pet-9", "2026-09-24T07:00:00+00:00")  # 迟到的旧时刻：不拨回去
        with self.storage.connect() as conn:
            self.assertEqual(self.wishes.last_considered_in(conn, "pet-9"), "2026-09-24T08:00:00+00:00")
            self.assertIsNone(self.wishes.last_considered_in(conn, "pet-never"), "从没考虑过就是 None")
        self.assertEqual(self.query("SELECT COUNT(*) AS n FROM web_travel_wishes")[0]["n"], 0, "前提：真的没有心愿行")


class TravelDepartureLinkTests(TravelStoreTestBase):
    def ready_wish(self):
        ref = self.propose()
        self.publish_plan(ref)
        with self.storage.connect() as conn:
            return self.wishes.ready_plan_in(conn, "pet-1")

    def test_linking_is_conditional_and_idempotent(self) -> None:
        plan = self.ready_wish()
        with self.assertRaises(VersionConflict):
            with unit_of_work(self.storage) as conn:
                self.wishes.link_journey_in(conn, plan.plan_id, plan.plan_revision + 1, plan.wish_id, plan.wish_revision, "jr-1")
        with unit_of_work(self.storage) as conn:
            self.wishes.link_journey_in(conn, plan.plan_id, plan.plan_revision, plan.wish_id, plan.wish_revision, "jr-1")
        with unit_of_work(self.storage) as conn:  # C 的重复命令（同一旅程）：幂等
            self.wishes.link_journey_in(conn, plan.plan_id, plan.plan_revision, plan.wish_id, plan.wish_revision, "jr-1")
        with self.assertRaises(VersionConflict):  # 另一趟旅程想抢这份计划
            with unit_of_work(self.storage) as conn:
                self.wishes.link_journey_in(conn, plan.plan_id, plan.plan_revision, plan.wish_id, plan.wish_revision, "jr-2")
        view = self.wishes.read("pet-1")
        self.assertEqual((view.status, view.journey_id), (LINKED, "jr-1"))
        self.assertEqual([row["journey_id"] for row in self.query("SELECT journey_id FROM web_travel_plans")], ["jr-1"])

    def test_a_wish_that_is_not_ready_cannot_be_linked(self) -> None:
        ref = self.propose()
        with self.assertRaises(VersionConflict):
            with unit_of_work(self.storage) as conn:
                row = store.wish_in(conn, ref.wish_id)
                self.wishes.link_journey_in(conn, row["plan_id"], 1, ref.wish_id, ref.wish_revision, "jr-1")
        self.assertIsNone(self.wishes.read("pet-1").journey_id, "没有真旅程就不写 journey_id，也不预建")

    def test_matching_versions_are_not_enough_the_wish_must_be_ready_on_that_plan(self) -> None:
        """与「心愿版本条件」「计划行没被别的旅程占」各自独立的一层：两个版本号都是当前的，
        关联旧一版计划（那一行还在、没被关联过）、或关联还在等（缺钱）的心愿，照样挡下。上面两条用例被另两层先拦住，分不出这一层。"""
        ref = self.propose()
        self.publish_plan(ref)
        self.publish_plan(ref, revision=2)  # 重新研究出了第 2 版
        row = self.query("SELECT * FROM web_travel_wishes")[0]
        with self.assertRaises(VersionConflict):
            with unit_of_work(self.storage) as conn:
                self.wishes.link_journey_in(conn, row["plan_id"], 1, ref.wish_id, row["wish_revision"], "jr-1")

        self.wishes.update_waiting(ref.wish_id, row["wish_revision"], [MISSING_FUNDS], None, None)
        row = self.query("SELECT * FROM web_travel_wishes")[0]
        self.assertEqual((row["status"], row["plan_revision"]), (ACTIVE, 2), "前提：缺钱，心愿回到等待")
        with self.assertRaises(VersionConflict):
            with unit_of_work(self.storage) as conn:
                self.wishes.link_journey_in(conn, row["plan_id"], 2, ref.wish_id, row["wish_revision"], "jr-1")

        self.assertEqual([r["journey_id"] for r in self.query("SELECT journey_id FROM web_travel_plans ORDER BY plan_revision")], [None, None])
        self.assertIsNone(self.wishes.read("pet-1").journey_id)

    def test_cancel_supersedes_the_queued_research_and_reading_writes_nothing(self) -> None:
        ref = self.propose()
        before = self.query("SELECT wish_revision, updated_at FROM web_travel_wishes")
        for _ in range(3):
            self.wishes.read("pet-1")
        self.assertEqual([tuple(r) for r in self.query("SELECT wish_revision, updated_at FROM web_travel_wishes")], [tuple(r) for r in before])
        self.wishes.cancel(ref.wish_id, ref.wish_revision)
        self.assertEqual(self.wishes.read("pet-1").status, CANCELLED)
        self.assertEqual([row["status"] for row in self.research_tasks()], ["superseded"])


class TravelInstallTests(TravelStoreTestBase):
    def test_install_wires_every_seam_it_promises(self) -> None:
        """装配入口：手账接到研究发布上、旅程结束能落定心愿、暂停谓词与身份／到访都接进去——漏接一根，这条红。"""
        from app.web_travel import install_travel
        paused, identity, visit = (lambda conn, pet_id: False), (lambda conn, pet_id: None), (lambda journey_id: None)
        travel = install_travel(self.storage, self.tasks, paused_in=paused, identity_of=identity, visit_of=visit,
                                settings=SimpleNamespace(web_travel_research_per_pet_daily=3, web_travel_research_daily_cap=50))
        self.assertIs(travel.research.journals, travel.journals)
        self.assertEqual(travel.journals.complete_wish_in, travel.wishes.complete_in)
        self.assertIs(travel.wishes.paused_in, paused)
        self.assertIs(travel.journals.identity_of, identity)
        self.assertIs(travel.journals.visit_of, visit)
        self.assertEqual((travel.research.per_pet_daily, travel.research.global_daily), (3, 50))
        self.assertIsNone(travel.research.port, "没接研究端口：什么都不发")


if __name__ == "__main__":
    unittest.main()
