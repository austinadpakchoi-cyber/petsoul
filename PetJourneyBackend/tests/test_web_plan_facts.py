"""逐条前置事实的有效期：出发这一刻按 `now` 再核一遍（TRV-02 T05，合同 4.2 第三个端口）。

计划整体的 `valid_window` 只是**这版计划**的边界；真正会过期的是它依据的那些事实
（几点关门、今天有没有活动、票还有没有）——它们在 A 的 `web_travel_facts` 里，各有各的有效期。
**旅程包不去读别人的表**，逐条判由 A 的端口做：

    stale_facts_in(conn, fact_ids, now) -> tuple[str, ...]   # 返回已过期的 fact_id；查不到的也算过期

`conn` 必须是出发那个写事务的连接（合同 0.1）——另开连接读的是事务开始前的旧快照，等于没核。

这一组用**同连接替身**验旅程这一侧的契约；接上 A 真实实现的那一组在
`test_web_wish_commit_real.py`。**替身通过不等于接入完成**，两组都要有。

不联网、不调用供应商、不新增付费。
"""

from __future__ import annotations

import unittest

from app.web_journey.errors import JourneyError
from app.web_journey.service import PlanChoice
from test_web_wish_commit import WishCommitBase

FACTS = ("fact-hours", "fact-ticket")


class PlanFactFreshnessTests(WishCommitBase):
    def wire_facts(self, stale: tuple[str, ...] = ()) -> dict:
        """装上逐条事实端口。形状＝A 的 `TravelWishService.stale_facts_in`（静态方法，只用调用方那个 conn）。"""
        seen: dict = {"calls": []}

        def stale_facts_in(conn, fact_ids, now):
            seen["calls"].append({"ids": tuple(fact_ids), "in_transaction": bool(conn.in_transaction)})
            return tuple(f for f in fact_ids if f in stale)

        self.journeys.stale_facts_in = stale_facts_in
        return seen

    def test_a_plan_with_an_expired_fact_does_not_depart(self) -> None:
        """攻略整体还在有效期内，但它依据的某一条事实过期了：不拿过期资料出门。"""
        plan = self.wire_plan(preconditions=FACTS)
        self.wire_facts(stale=("fact-ticket",))

        with self.assertRaises(JourneyError) as rejected:
            self.depart(plan=PlanChoice(plan["plan_id"], plan["revision"]))

        self.assertEqual(rejected.exception.reason, "fact_stale")
        self.assertIn("fact-ticket", str(rejected.exception.details.get("fact_ids", "")), "要说清是哪一条过期了")
        self.nothing_left("有一条前置事实过期")

    def test_a_plan_whose_facts_are_all_fresh_departs(self) -> None:
        """正向对照：事实都还新鲜就照常出发——**而且端口真的被问过**。

        只验拒绝那一半的话，一个「从不调用端口」的实现也会通过这一组。
        """
        plan = self.wire_plan(preconditions=FACTS)
        seen = self.wire_facts(stale=())

        journey = self.depart(plan=PlanChoice(plan["plan_id"], plan["revision"]))

        self.assertEqual(self.links(), [(plan["plan_id"], journey.journey_id)])
        self.assertEqual(len(seen["calls"]), 1, "逐条核销要在出发事务里问一次")
        self.assertEqual(seen["calls"][0]["ids"], FACTS, "要把计划的全部前置事实交过去")
        self.assertTrue(seen["calls"][0]["in_transaction"], "必须用写事务里的那个连接，另开连接读的是旧快照")

    def test_a_plan_with_preconditions_refuses_when_the_fact_port_is_missing(self) -> None:
        """要核却没有端口可用：拒绝，不能当作「都还新鲜」放行。

        与 `waiver_unavailable` / `plan_link_unavailable` / `commitment_gate_unavailable` 同一条纪律——
        **静默跳过保护比拒绝危险得多**：放行之后没有任何东西会提示这次根本没核过。
        显式制造「没装配」，不依赖默认值。
        """
        plan = self.wire_plan(preconditions=FACTS)
        self.journeys.stale_facts_in = None

        with self.assertRaises(JourneyError) as refused:
            self.depart(plan=PlanChoice(plan["plan_id"], plan["revision"]))

        self.assertEqual(refused.exception.reason, "fact_check_unavailable")
        self.nothing_left("要核事实却没有端口")

    def test_a_plan_with_no_preconditions_departs_without_the_port(self) -> None:
        """边界：没有前置事实的计划，**不该**因为端口没装配而被拒。

        没这一条的话，「缺端口就拒绝」会连没有事实要核的计划一起拦掉——
        那是把一道保护扩大成一道故障。A 的端口对空入参本来就返回 `()`，这里钉的是旅程侧不去调它。
        """
        plan = self.wire_plan(preconditions=())
        self.journeys.stale_facts_in = None

        journey = self.depart(plan=PlanChoice(plan["plan_id"], plan["revision"]))

        self.assertEqual(self.links(), [(plan["plan_id"], journey.journey_id)])


if __name__ == "__main__":
    unittest.main()
