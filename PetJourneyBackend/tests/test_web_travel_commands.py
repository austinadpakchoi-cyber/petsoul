"""旅行研究的显式重做命令（TRV-03；合同第 7 节 POST …/research/retry；方案 §11.2）。真实迁移建库、**假**研究端口、0 次付费调用。

钉的是：可能已发出、还没结清的旧 operation 在时**不换号重发**；对账结成「确定没发」以后才放行（正向对照）；
这一轮有已存下的应答时，重做在同一轮复用、**不发送**；研究在排或在跑时不再排一个；资料过期时主人明确重做 → 新一轮、新一版计划。
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import timedelta
from unittest import mock

from travel_wish_fakes import TravelResearchTestBase, good_result

from app.utils import iso, utcnow
from app.web_platform.uow import unit_of_work
from app.web_travel.model import FACT_STALE, READY, VersionConflict
from app.web_travel.ports import ResearchUnknown
from app.web_travel.research import ResearchInProgress, ResearchUnsettled
from app.web_travel.service import RESEARCH_KIND


class TravelRetryTests(TravelResearchTestBase):
    def revision(self) -> int:
        return self.wishes.read("pet-1").wish_revision

    def test_an_unsettled_maybe_sent_operation_blocks_a_retry_until_reconciled(self) -> None:
        self.port.raises = ResearchUnknown("timeout")
        ref = self.propose()
        self.research.run_pending()
        with self.assertRaises(ResearchUnsettled):
            self.research.retry(ref.wish_id, self.revision())
        (reservation,) = self.reservations()
        self.ledger.settle(reservation["reservation_id"], "not_sent")  # 运营对账：确定没发出

        self.port.raises = None
        self.research.retry(ref.wish_id, self.revision())
        self.research.run_pending()

        self.assertEqual(len(self.port.calls), 2, "结清之后才换号重发")
        view = self.wishes.read("pet-1")
        self.assertEqual((view.research_round, view.status, view.plan_revision), (2, READY, 1))

    def test_a_stored_answer_is_reused_by_a_retry_without_sending(self) -> None:
        count = []

        def broken(conn, task, operation_id, result, now):
            count.append(1)
            raise RuntimeError("发布写入失败（测试注入）")

        ref = self.propose()
        with mock.patch.object(self.research, "_publish_in", broken):
            for _ in range(2):  # 两次都发布失败：次数用尽，任务落定为 failed，应答还存着
                self.research.run_pending()
                with self.storage.connect() as conn:
                    conn.execute("UPDATE web_tasks SET run_after = '2000-01-01T00:00:00+00:00' WHERE kind = ? AND status = 'queued'", (RESEARCH_KIND,))
        self.assertEqual(([r["status"] for r in self.receipts()], self.task()["status"]), (["answered"], "failed"))

        self.research.retry(ref.wish_id, self.revision())
        self.research.run_pending()

        self.assertEqual(len(self.port.calls), 1, "复用已付费的应答，不再发")
        self.assertEqual((self.wishes.read("pet-1").research_round, self.receipts()[0]["status"]), (1, "published"))
        self.assertEqual(len(count), 2)

    def test_a_retry_while_research_is_queued_is_refused(self) -> None:
        ref = self.propose()
        with self.assertRaises(ResearchInProgress):
            self.research.retry(ref.wish_id, ref.wish_revision)
        self.assertEqual(len(self.query("SELECT * FROM web_tasks WHERE kind = ?", (RESEARCH_KIND,))), 1)

    def test_a_retry_while_research_is_running_is_refused(self) -> None:
        """结构不变量之一：研究**在跑**时也不能改轮次。`research._publish_in` 开头那道「心愿还开着、轮次没变」的复核
        因此走不到（另两条：取消作废在跑的任务、重查期间心愿不是 ready）。放开它，那道复核就可达——请同时给它补一条真触发用例。"""
        seen: list[str] = []

        def meanwhile(request):
            try:
                self.research.retry(request.wish_id, self.revision())
                seen.append("queued")
            except ResearchInProgress:
                seen.append("refused")

        self.port.on_call = meanwhile
        self.propose()
        self.research.run_pending()
        self.assertEqual(seen, ["refused"])
        self.assertEqual((len(self.plans()), self.wishes.read("pet-1").research_round), (1, 1))

    def test_a_wish_being_re_researched_cannot_depart_on_its_old_plan(self) -> None:
        """结构不变量之二：主人要求重查后研究挂 research_pending，心愿不是 ready——出发拿不到计划，拿旧一版硬关联
        （连当前的心愿版本号一起给）也挡下。放开它（例如让重查期间照旧按旧计划出发），研究在跑时心愿就可能被关联，
        `research._publish_in` 开头那道复核就可达——请同时给它补一条真触发用例。"""
        ref = self.propose()
        self.research.run_pending()
        with self.storage.connect() as conn:
            old = self.wishes.ready_plan_in(conn, "pet-1")
        self.research.retry(ref.wish_id, self.revision())

        with self.storage.connect() as conn:
            self.assertIsNone(self.wishes.ready_plan_in(conn, "pet-1"), "重查途中没有可出发的计划")
        with self.assertRaises(VersionConflict):
            with unit_of_work(self.storage) as conn:
                self.wishes.link_journey_in(conn, old.plan_id, old.plan_revision, old.wish_id, self.revision(), "jr-1")
        self.research.run_pending()
        with self.storage.connect() as conn:
            self.assertEqual(self.wishes.ready_plan_in(conn, "pet-1").plan_revision, 2, "查完：新一版可以出发")

    def test_stale_facts_and_an_explicit_retry_give_a_new_round_and_plan_revision(self) -> None:
        stale = tuple(replace(f, observed_at=iso(utcnow() - timedelta(days=3))) if f.key == "weather" else f for f in good_result().facts)
        self.port.result = replace(good_result(), facts=stale)
        ref = self.propose()
        self.research.run_pending()
        self.assertEqual(self.wishes.read("pet-1").waiting_reasons, (FACT_STALE,))

        self.port.result = good_result()
        self.research.retry(ref.wish_id, self.revision())
        self.research.run_pending()

        self.assertEqual(len(self.port.calls), 2)
        view = self.wishes.read("pet-1")
        self.assertEqual((view.research_round, view.plan_revision, view.waiting_reasons, view.status), (2, 2, (), READY))
        self.assertEqual([p["plan_revision"] for p in self.plans()], [1, 2], "旧版计划留着，新版 +1")


if __name__ == "__main__":
    unittest.main()
