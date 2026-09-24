"""接 A 的**真实**实现出发：`ready_plan_in` / `link_journey_in` / `stale_facts_in`（合同 4.2）。

`test_web_wish_commit.py` 与 `test_web_plan_facts.py` 用的是同连接替身——**替身通过不等于接入完成**：
替身是我按合同"应该长什么样"写的，它和 A 真写出来的东西之间，没有任何东西会自动报警。
这一组把替身换掉，用 A 的 `TravelWishService`、A 的表、真实的一个写事务。

心愿与计划由 A 的**真实**研究流水线产出（`propose` → `research.run_pending()`），
研究端口是假的（`FakeResearchPort`）：不联网、0 次付费调用。
**不手写 `ready` 行**——手写的话可能造出真实流水线根本产生不出来的状态，
那时这组用例验的是一个虚构的世界。

装配（组合根把这三个端口接到 journeys 上）**还没做，归 I**：`web_composition.py` 尚未调 `install_travel`。
所以这里在用例里自己接一次——**这一组证明的是"接上之后能用"，不是"已经接上了"**。
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from app.utils import iso
from app.web_journey.errors import JourneyError
from app.web_journey.service import PlanChoice
from app.web_platform.budget import BudgetLedger
from app.web_platform.tasks import WebTaskQueue
from app.web_travel.ports import DraftStop, ResearchDraft, ResearchFact, ResearchSource
from app.web_travel.research import TravelResearchService
from app.web_travel.service import TravelWishService
from travel_wish_fakes import FakeResearchPort, good_result
from test_web_wish_commit import DESTINATION, FEE, WishCommitBase

PLACE = "附近的咖啡馆"
CANDIDATE = {"destination_key": DESTINATION, "name": PLACE, "city": "香港"}


def cafe_result(now):
    """一份**会通过核验**的研究结果：事实的 subject 要落在主目的地上（`facts.review(primary=…)`）。

    直接用 `travel_wish_fakes.good_result()` 会停在 `fact_unverified`——它那几条事实说的是浅水湾，
    而本组的主目的地是附近的咖啡馆，身份与路径这两条 `REQUIRED` 对不上。
    这里只换 subject 与文案，核验口径（来源、verification、观测时间）照搬 A 的那一份。
    """
    sources = (ResearchSource("s-map", url=None, publisher="高德地图", retrieved_at=iso(now)),
               ResearchSource("s-weather", url=None, publisher="香港天文台", retrieved_at=iso(now)))
    facts = (ResearchFact("identity", "destination_identity", PLACE, {"lat": 22.2830, "lng": 114.1600}, ("s-map",), verification="map"),
             ResearchFact("route", "route", PLACE, "从家走过去十分钟", ("s-map",), verification="map"),
             ResearchFact("weather", "weather", PLACE, {"suitable": True, "summary": "多云"}, ("s-weather",),
                          observed_at=iso(now - timedelta(hours=1)), verification="weather_api"))
    draft = ResearchDraft(title="去坐一会儿", summary="想去附近的咖啡馆坐一会儿。",
                          stops=(DraftStop(PLACE, "main", "喝一杯", "带上零钱", ("identity", "route")),),
                          owner_tips=("走过去就行",), tip_fact_keys=(("route",),), rain_alternative="下雨就改天去")
    return good_result(sources=sources, facts=facts, draft=draft)


class RealPlanCommitTests(WishCommitBase):
    def setUp(self) -> None:
        super().setUp()
        storage = self.app.state.storage
        tasks = WebTaskQueue(storage)
        self.wishes = TravelWishService(storage, tasks)
        self.research = TravelResearchService(storage, tasks, self.wishes, ledger=BudgetLedger(storage))
        self.research.port = FakeResearchPort(cafe_result(self.clock.now))
        # 组合根该接的那三根线，这里自己接一次（真实实现，不是替身）
        self.journeys.ready_plan_in = self.wishes.ready_plan_in
        self.journeys.link_journey_in = self.wishes.link_journey_in
        self.journeys.stale_facts_in = self.wishes.stale_facts_in

    # ---- 造一份真的 ready 计划 ----
    def publish_plan(self):
        """走 A 的真实流水线：提心愿 → 跑研究 → 发布计划。返回它自己读出来的 `PlanRef`。"""
        self.wishes.propose(pet_id=self.owner.pet_id, user_id=self.owner.user_id, trigger_event_id="evt-real-1",
                            candidates=[CANDIDATE], selected=0, interest_tags=["cafe"], owner_reason="主人说过想去坐坐", funds_goal=FEE)
        self.research.run_pending()
        with self.app.state.storage.connect() as conn:
            view = self.wishes.read_in(conn, self.owner.pet_id)
            plan = self.wishes.ready_plan_in(conn, self.owner.pet_id)
        self.assertIsNotNone(plan, f"前提不成立：真实流水线没有产出 ready 计划，下面的断言都不作数（等待原因：{view.waiting_reasons}）")
        return plan

    def wish_row(self) -> tuple:
        return self.rows("SELECT status, journey_id FROM web_travel_wishes WHERE pet_id = ?", self.owner.pet_id)[-1]

    # ---- 出发 ----
    def test_a_real_ready_plan_departs_links_and_charges_in_one_transaction(self) -> None:
        plan = self.publish_plan()
        before = self.balance()
        self.assertEqual(self.wish_row(), ("ready", None), "出发前心愿是 ready、还没有旅程")

        journey = self.depart(plan=PlanChoice(plan.plan_id, plan.plan_revision))

        self.assertEqual(self.journeys_count(), 1)
        self.assertEqual(self.wish_row(), ("linked", journey.journey_id), "心愿落到了这一趟真旅程上")
        self.assertEqual(self.fares(), [f"web:travel_fee:{journey.journey_id}"])
        self.assertEqual(self.balance(), before - FEE)

    def test_a_stale_plan_revision_does_not_depart_against_the_real_service(self) -> None:
        plan = self.publish_plan()

        with self.assertRaises(JourneyError) as rejected:
            self.depart(plan=PlanChoice(plan.plan_id, plan.plan_revision + 1))

        self.assertEqual(rejected.exception.reason, "plan_revision_changed")
        self.assertEqual(self.wish_row(), ("ready", None), "心愿一动没动")
        self.assertEqual(self.journeys_count(), 0)

    def test_an_expired_precondition_in_the_real_facts_table_stops_the_departure(self) -> None:
        """把 A 表里某一条真事实的有效期改到过去：出发这一刻逐条复核必须挡下（T05）。

        这条是替身验不到的那一半——替身里"过期"是我自己 return 的，
        这里过期是 A 的 `stale_facts_in` 从 `web_travel_facts` 真读出来判的。
        """
        plan = self.publish_plan()
        self.assertTrue(plan.preconditions, "前提不成立：这份计划没有前置事实，下面挡不挡都说明不了问题")
        expired = plan.preconditions[0]
        with self.app.state.storage.connect() as conn:
            changed = conn.execute("UPDATE web_travel_facts SET valid_until = ? WHERE fact_id = ?",
                                   (iso(self.clock.now - timedelta(hours=1)), expired)).rowcount
        self.assertEqual(changed, 1, "前提不成立：那条事实没被改到，过期是假的")

        with self.assertRaises(JourneyError) as rejected:
            self.depart(plan=PlanChoice(plan.plan_id, plan.plan_revision))

        self.assertEqual(rejected.exception.reason, "fact_stale")
        self.assertIn(expired, rejected.exception.details.get("fact_ids", ""))
        self.assertEqual(self.wish_row(), ("ready", None), "挡下之后心愿不能变成 linked")
        self.assertEqual(self.journeys_count(), 0)
        self.assertEqual(self.fares(), [], "钱也不能扣")

    def test_a_plan_for_somewhere_else_cannot_be_linked_to_this_trip(self) -> None:
        """这份计划是去**别处**的：不能把它绑到这一趟上。

        不加这道的话，一份「去浅水湾」的计划会被绑到一趟去咖啡馆的旅程上，
        旅程结束时那个心愿落定为 completed——**手账上会出现一次根本没去过的旅行**，
        而且没有任何东西会报错：两个 id 都是真的、版本也都对得上。

        目前还没有生产调用方传 `plan_id`（三个 `depart` 调用点都没传），所以这是**趁还没有调用者时先把闸装上**，
        不是在修一个正在发生的缺陷。提交边界的职责就是在写之前把该核的都核一遍，
        而"目的地对不对得上"是其中唯一一条还没核的。
        """
        plan = self.publish_plan()

        with self.assertRaises(JourneyError) as rejected:
            self.journeys.depart(self.owner.user_id, self.owner.pet_id, self.owner.home_id, "local:stroll", self.clock.now,
                                 plan=PlanChoice(plan.plan_id, plan.plan_revision))

        self.assertEqual(rejected.exception.reason, "plan_destination_mismatch")
        self.assertEqual(self.wish_row(), ("ready", None), "心愿不能被绑到别处去")
        self.assertEqual(self.journeys_count(), 0)

    def test_the_same_plan_cannot_be_taken_by_a_second_journey(self) -> None:
        """同一份计划不能被第二趟旅程再用一次。

        **挡住它的是哪一道，要说准**：第一趟之后心愿变成 `linked`，A 的 `ready_plan_in` 就不再返回它，
        于是拒绝发生在**我这一侧**的 `plan_not_ready`。
        A 那条「这版计划已被别的旅程关联 → VersionConflict」**在这条路上走不到**——
        它是更里面的一道兜底，不是此处干活的那一道。
        原先这条我写的是 `assertRaises(Exception)` 并声称在验 A 的守卫：**那个标签是假的**，
        而且 `Exception` 连 `TypeError` 都会放过——普通异常不能冒充保护。
        """
        plan = self.publish_plan()
        first = self.depart(plan=PlanChoice(plan.plan_id, plan.plan_revision))
        self.web.journeys.repo.complete(first.journey_id, self.clock.now)  # 让 TA 不再"在路上"，把闸让给计划那一层

        with self.assertRaises(JourneyError) as blocked:
            self.depart(plan=PlanChoice(plan.plan_id, plan.plan_revision))

        self.assertEqual(blocked.exception.reason, "plan_not_ready")
        self.assertEqual(self.journeys_count(), 1, "第二趟必须整笔回滚，不能留下行程")
        self.assertEqual(self.wish_row(), ("linked", first.journey_id), "心愿还绑在第一趟上，没被改走")


if __name__ == "__main__":
    unittest.main()
