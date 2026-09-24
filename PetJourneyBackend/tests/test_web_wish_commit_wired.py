"""**组合根真的把那三根线接上了吗**——这一组自己一根线都不接（TRV-02，合同 §4.2）。

和 `test_web_wish_commit_real.py` 的分工，是两件不同的事，都要有：

    test_web_wish_commit_real.py   用例里**自己接**三个端口 → 证明「**接上之后**能用」
    本文件                          **一根都不接**，走真实组合根 → 证明「**已经接上了**」

只留前者的话，组合根哪天漏接一根、或者被谁重构掉，那一组照样全绿——
**接线消失时，测回调的用例会静悄悄地绿，测正式入口的才会红。后者才是危险的那一类。**

唯一的替身是**研究供应商**（`FakeResearchPort`）：组合根有意没接 `research_port`
（TRV-04 适配器还没做，`run_pending` 在没有 port 时 `return 0`，是诚实的 fail-closed）。
这里注入它只是为了造出一份真计划，**不联网、0 次付费调用**。
连同 `ledger` 一起注入：**注入了 port 就必须同时注入 ledger**（研究是付费调用）。

这句的理由 2026-09-24 变过一次，照实写清楚——**A 后来把它闭合成两层，不再是 fail-open**：

    install_travel:43      构造期：接了 port 没接 ledger → 当场 ValueError
    research.py:211        `_reserve_in`：`ledger is None` → 抛 ResearchMisconfigured（**不再 return None**）

**这一组绕过了第一层**（直接给 `research.ledger` 赋值，不经 `install_travel`），靠的是第二层。
实测拆掉 ledger 之后会怎样：异常**不会浮到调用方表面**——任务机制接住它，
记 `web_tasks.last_error='ResearchMisconfigured'`、状态留 `queued`，心愿停在 `research_pending`。
**所以看到的现象是"心愿卡住"，不是"配置错了"**；是本文件 `ready_plan()` 里那句前提断言
（"真实流水线没产出 ready 计划（等待原因：…）"）把它变成一条读得懂的红。
"""

from __future__ import annotations

import unittest

from app.web_journey.service import PlanChoice
from app.web_platform.budget import BudgetLedger
from test_web_wish_commit import DESTINATION, FEE, WishCommitBase
from test_web_wish_commit_real import CANDIDATE, cafe_result
from travel_wish_fakes import FakeResearchPort


class CompositionWiringTests(WishCommitBase):
    def setUp(self) -> None:
        super().setUp()
        self.travel = self.web.travel                      # 组合根装好的那一套，不重建
        self.travel.research.port = FakeResearchPort(cafe_result(self.clock.now))
        self.travel.research.ledger = BudgetLedger(self.app.state.storage)
        # **这里一根线都不接**：journeys.ready_plan_in / link_journey_in / stale_facts_in 保持组合根给的样子

    def ready_plan(self):
        self.travel.wishes.propose(pet_id=self.owner.pet_id, user_id=self.owner.user_id, trigger_event_id="evt-wired-1",
                                   candidates=[CANDIDATE], selected=0, interest_tags=["cafe"],
                                   owner_reason="主人说过想去坐坐", funds_goal=FEE)
        self.travel.research.run_pending()
        with self.app.state.storage.connect() as conn:
            view = self.travel.wishes.read_in(conn, self.owner.pet_id)
            plan = self.travel.wishes.ready_plan_in(conn, self.owner.pet_id)
        self.assertIsNotNone(plan, f"前提不成立：真实流水线没产出 ready 计划（等待原因：{view.waiting_reasons}）")
        return plan

    def wish_row(self) -> tuple:
        return self.rows("SELECT status, journey_id FROM web_travel_wishes WHERE pet_id = ?", self.owner.pet_id)[-1]

    def test_the_composition_root_wires_the_three_ports(self) -> None:
        """三个端口**都**要从组合根接上——漏接一根，这条红。

        先逐个断言"不是 None"（漏了哪一根一眼看得出），再走一趟真出发把它们真正用一遍：
        **只断言不是 None 是不够的**，接错对象、接成别人的方法，同样是 None 以外的值。
        """
        for name in ("ready_plan_in", "link_journey_in", "stale_facts_in"):
            with self.subTest(port=name):
                self.assertIsNotNone(getattr(self.web.journeys, name), f"组合根没接 {name}")

        plan = self.ready_plan()
        before = self.balance()

        journey = self.web.journeys.depart(self.owner.user_id, self.owner.pet_id, self.owner.home_id, DESTINATION,
                                           self.clock.now, plan=PlanChoice(plan.plan_id, plan.plan_revision))

        self.assertEqual(self.wish_row(), ("linked", journey.journey_id), "心愿要落到这一趟真旅程上")
        self.assertEqual(self.fares(), [f"web:travel_fee:{journey.journey_id}"])
        self.assertEqual(self.balance(), before - FEE)

    def test_a_stale_revision_is_refused_through_the_real_wiring(self) -> None:
        """反向：走同一条真实接线，版本对不上必须整笔不做。

        没有这条的话，一个"把三个端口接成永远放行的桩"也能让上面那条通过。
        """
        from app.web_journey.errors import JourneyError

        plan = self.ready_plan()

        with self.assertRaises(JourneyError) as rejected:
            self.web.journeys.depart(self.owner.user_id, self.owner.pet_id, self.owner.home_id, DESTINATION,
                                     self.clock.now, plan=PlanChoice(plan.plan_id, plan.plan_revision + 1))

        self.assertEqual(rejected.exception.reason, "plan_revision_changed")
        self.assertEqual(self.wish_row(), ("ready", None))
        self.assertEqual(self.journeys_count(), 0)


if __name__ == "__main__":
    unittest.main()
