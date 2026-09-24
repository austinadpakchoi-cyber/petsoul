"""旅行研究任务：正常路径与核对规则（TRV-03；方案 §11；合同 11.3、11.4）。真实迁移建库、**假**研究端口、0 次付费调用。

钉的是：一次研究发一次、落一版计划、回执标 published、预占按成功结算（T01 的研究一段）；
检索没真正执行时搜索事实不落库、不进计划（T13）；旧天气与假来源只拒那条事实、文字仍可用（T04）；
研究请求只带公开字段（T11）；平台额度不够不发送、挂 quota_denied（≠ 缺钱）；暂停的宠物不发送；心愿中途取消则作废响应。
恢复与并发（T06／T07）在 `test_web_travel_recovery.py`。
"""

from __future__ import annotations

import json
import unittest
from dataclasses import asdict, replace
from datetime import timedelta

from travel_wish_fakes import PRIVATE_REASON, TravelResearchTestBase, good_result

from app.utils import iso, utcnow
from app.web_platform.budget import BudgetLimit
from app.web_travel.facts import fact_id
from app.web_travel.model import FACT_STALE, FACT_UNVERIFIED, QUOTA_DENIED, READY, RESEARCH_PENDING
from app.web_travel.ports import ResearchFact


class TravelResearchPathTests(TravelResearchTestBase):
    def test_one_research_one_send_one_plan_revision(self) -> None:
        ref = self.propose()
        self.research.run_pending()

        self.assertEqual(len(self.port.calls), 1)
        (receipt,) = self.receipts()
        (plan,) = self.plans()
        self.assertEqual((receipt["status"], receipt["plan_revision"], plan["plan_revision"]), ("published", 1, 1))
        self.assertEqual(plan["operation_id"], receipt["operation_id"], "计划的那一版指回产出它的回执")
        self.assertEqual((receipt["tool_executions"], json.loads(receipt["tool_execution_ids_json"])), (1, ["srvtool-1"]))
        self.assertEqual([(r["status"], r["purpose"]) for r in self.reservations()], [("settled", "travel_research")])
        stops = json.loads(plan["stops_json"])
        self.assertEqual([(s["name"], s["role"], s["verified"]) for s in stops], [("浅水湾", "main", True), ("赤柱", "suggested", True)])
        self.assertEqual([s["visited_event_ids"] for s in stops], [[], []], "计划阶段不盖到访章")
        self.assertEqual([t["text"] for t in json.loads(plan["owner_tips_json"])], ["坐 6 路巴士去", "记得带水"])
        view = self.wishes.read("pet-1")
        self.assertEqual((view.status, view.waiting_reasons, view.plan_revision, view.research_state), (READY, (), 1, "ready"))
        self.assertEqual(self.task()["status"], "succeeded")
        self.research.run_pending()
        self.assertEqual(len(self.port.calls), 1, "做完了就不再发")
        self.assertTrue(ref.created)

    def test_a_model_that_only_says_it_searched_gets_no_facts(self) -> None:
        """T13：工具执行条数为 0（或有条数无标识）＝没检索；正文里写了来源也不算，搜索事实不落库、不进计划。"""
        for label, override in {"没有执行块": {"tool_executions": 0, "tool_execution_ids": ()},
                                "有条数无标识": {"tool_executions": 2, "tool_execution_ids": ()}}.items():
            with self.subTest(label):
                self.setUp()
                self.port.result = good_result(**override)
                self.propose()
                self.research.run_pending()
                stored = {row["category"] for row in self.query("SELECT category FROM web_travel_facts")}
                self.assertNotIn("feature", stored, "搜索来的那条不落库")
                stops = json.loads(self.plans()[0]["stops_json"])
                self.assertEqual([s["name"] for s in stops], ["浅水湾"], "顺路建议没有已核验事实支撑，不进计划")
                self.assertEqual(self.receipts()[0]["tool_executions"], override["tool_executions"], "原样记下，供对账")

    def test_old_weather_and_a_fake_source_reject_only_those_facts(self) -> None:
        """T04：旧天气 → fact_stale；假 source_id → 那条被拒、不进计划；可用文字仍在，正常路径对照在同一份证据里。"""
        now = utcnow()
        base = good_result()
        facts = tuple(replace(f, observed_at=iso(now - timedelta(days=3))) if f.key == "weather" else f for f in base.facts)
        facts += (ResearchFact("fake", "feature", "赤柱", "据说有集市", ("s-nowhere",), verification="map"),)
        self.port.result = replace(base, facts=facts)
        self.propose()
        self.research.run_pending()

        verdicts = {row["subject"] + ":" + row["category"]: row["verdict"] for row in self.query("SELECT * FROM web_travel_facts")}
        self.assertEqual(verdicts["浅水湾:weather"], "stale")
        self.assertIn("rejected", verdicts.values())
        self.assertEqual(verdicts["浅水湾:destination_identity"], "verified", "对照：正常的那几条照常核验")
        view = self.wishes.read("pet-1")
        self.assertEqual(view.waiting_reasons, (FACT_STALE,))
        plan = self.plans()[0]
        self.assertEqual((plan["title"], plan["summary"]), ("去看海", "我想去海边听一会儿浪。"), "拒的是那条事实，不是整份计划")
        self.assertNotIn("s-nowhere", plan["sources_json"])

    def test_a_missing_destination_identity_keeps_the_wish_waiting(self) -> None:
        base = good_result()
        self.port.result = replace(base, facts=tuple(f for f in base.facts if f.category != "destination_identity"))
        self.propose()
        self.research.run_pending()
        self.assertEqual(self.wishes.read("pet-1").waiting_reasons, (FACT_UNVERIFIED,))

    def test_tips_with_numbers_need_a_verified_fact(self) -> None:
        """带数字的提醒（票价、时间）必须有已核验事实支撑才进计划；不带数字的通用提醒可以留。"""
        base = good_result()
        self.port.result = replace(base, draft=replace(base.draft, owner_tips=("门票 50 元", "记得带水"), tip_fact_keys=((), ())))
        self.propose()
        self.research.run_pending()
        self.assertEqual([t["text"] for t in json.loads(self.plans()[0]["owner_tips_json"])], ["记得带水"])

    def test_a_price_without_an_iso_currency_is_dropped_whole(self) -> None:
        """I 裁定：币种只认 ISO 4217 三字母大写。认不出（「元」、小写、不知道是否估算、负数）就整条拒，**落库不带原值**——
        页面不用猜；可选项被拒不挡出行。正例对照：HKD、带是否估算的那条照常核验通过、原值落库。"""
        observed = iso(utcnow() - timedelta(days=1))
        values = {"hkd": {"amount": 12, "currency": "HKD", "estimated": False}, "yuan": {"amount": 12, "currency": "元", "estimated": False},
                  "lower": {"amount": 12, "currency": "hkd", "estimated": True}, "unsure": {"amount": 12, "currency": "HKD"},
                  "negative": {"amount": -1, "currency": "HKD", "estimated": True}}
        prices = tuple(ResearchFact(key, "ticket_price", "浅水湾", value, ("s-web",), observed_at=observed, verification="search")
                       for key, value in values.items())
        self.port.result = good_result(facts=good_result().facts + prices)
        self.propose()
        self.research.run_pending()

        (receipt,) = self.receipts()
        rows = {r["fact_id"]: r for r in self.query("SELECT * FROM web_travel_facts")}
        got = {key: (rows[fact_id(receipt["operation_id"], key)]["verdict"], json.loads(rows[fact_id(receipt["operation_id"], key)]["value_json"]))
               for key in values}
        self.assertEqual(got.pop("hkd"), ("verified", values["hkd"]))
        self.assertEqual(got, {key: ("rejected", None) for key in got})
        self.assertEqual(self.wishes.read("pet-1").status, READY, "可选项被拒不挡出行")

    def test_the_research_call_cost_is_kept_only_with_an_iso_currency(self) -> None:
        """研究调用本身的费用（平台 API 费，合同 §8 不下发玩家端，只供对账）同一口径：认不出币种就金额也不留。"""
        for currency, expected in (("USD", (0.03, "USD")), ("usd", (None, None)), ("美元", (None, None)), (None, (None, None))):
            with self.subTest(currency=currency):
                self.setUp()
                self.port.result = good_result(cost_amount=0.03, cost_currency=currency)
                self.propose()
                self.research.run_pending()
                (receipt,) = self.receipts()
                self.assertEqual((receipt["cost_amount"], receipt["cost_currency"]), expected)

    def test_the_request_carries_only_public_fields(self) -> None:
        """T11：请求体里找不到给主人的理由（带合成标记），只有目的地、城市、日期窗口、白名单标签。"""
        self.propose()
        self.research.run_pending()
        (request,) = self.port.calls
        body = json.dumps(asdict(request), ensure_ascii=False)
        self.assertNotIn("合成标记", body)
        self.assertEqual(set(asdict(request)), {"operation_id", "wish_id", "wish_revision", "destination_key", "destination_name",
                                                "city", "window_start", "window_end", "interests"})
        self.assertEqual(request.interests, ("sea",))
        self.assertIn(PRIVATE_REASON, self.query("SELECT owner_reason FROM web_travel_wishes")[0]["owner_reason"], "对照：理由确实存着")


class TravelResearchGateTests(TravelResearchTestBase):
    def test_no_platform_quota_means_no_send_and_it_is_not_missing_funds(self) -> None:
        self.research.per_pet_daily = 1
        self.ledger.reserve("other:op", provider="research", purpose="travel_research", subject_scope="pet:pet-1", units=1,
                            limits=[BudgetLimit("pet:pet-1:travel_research", 1)])  # 别的研究先占满了这只宠物今天的额度
        self.propose()
        self.research.run_pending()
        self.assertEqual(len(self.port.calls), 0)
        view = self.wishes.read("pet-1")
        self.assertEqual((view.waiting_reasons, view.research_state), ((QUOTA_DENIED,), "failed"))
        self.assertEqual(self.receipts(), [], "没拿到额度：连意图都不落")

    def test_a_paused_pet_is_not_researched_now(self) -> None:
        self.propose()  # 心愿在暂停前已形成
        self.wishes.paused_in = lambda conn, pet_id: True
        self.research.run_pending()
        self.assertEqual(len(self.port.calls), 0)
        self.assertEqual((self.task()["status"], self.wishes.read("pet-1").waiting_reasons), ("queued", (RESEARCH_PENDING,)))

    def test_a_wish_cancelled_while_researching_discards_the_answer(self) -> None:
        ref = self.propose()
        self.port.on_call = lambda request: self.wishes.cancel(ref.wish_id, self.wishes.read("pet-1").wish_revision)
        self.research.run_pending()
        self.assertEqual(len(self.port.calls), 1)
        self.assertEqual([r["status"] for r in self.receipts()], ["discarded"])
        self.assertEqual(self.plans(), [], "心愿已取消：响应作废，不落计划")
        # 结构不变量之三：取消把**在跑**的研究一并作废，发布那道围栏失效——`research._publish_in` 开头那道复核因此走不到。
        # 不作废在跑的任务，这条用例照样绿（那道复核接住）；所以单独钉任务状态。放开它，请同时给那道复核补一条真触发用例
        self.assertEqual(self.task()["status"], "superseded")


if __name__ == "__main__":
    unittest.main()
