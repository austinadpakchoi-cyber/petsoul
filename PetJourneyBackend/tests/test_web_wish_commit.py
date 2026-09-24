"""带预研计划的出发：计划绑定、计划版本、承诺闸，都要和行程／旅费同生共死（TRV-02，T05／T07）。

合同 4.2 定的 C→A 端口（全部 `*_in(conn, …)`，理由见合同 0.1）：

    ready_plan_in(conn, pet_id)  -> (plan_id, plan_revision, wish_id, wish_revision, …)   纯读
    link_journey_in(conn, plan_id, plan_revision, wish_id, wish_revision, journey_id, now)
                                 # 条件更新：版本不符或状态非 ready → 抛，C 整体回滚
    active_commitment_in(conn, pet_id, now) -> Commitment | None                          纯读

A 还没落地这三个，所以这里用**同连接替身**验旅程这一侧的契约：替身只用调用方给的那个 `conn` 读写，
形状就是要请 A 实现的那个。A 落地后由装配接上，这组用例不用改。

两条语义是这批争出来的，用例把它们钉住：
- **承诺闸只对自主路径生效**（`honor_commitments=True`）：主人自己点出发**不该**被"家人说今天待在家"拦住；
- **端口没装配时不静默跳过**：调用方明确要闸却没有闸可用 → 明确拒绝，而不是当作"没有承诺"放行。

不联网、不调用供应商、不新增付费。
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from app.schemas.base import EconomyTransactionType
from app.web_travel.model import PlanRef
from app.web_journey.errors import JourneyError
from app.web_journey.service import PlanChoice
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase

DESTINATION, FEE = "local:cafe", 8


class WishCommitBase(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("wish-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.journeys = self.web.journeys
        self.web.economy.apply(self.owner.pet_id, 100, EconomyTransactionType.web_reward, "test:topup",
                               reason="测试用旅费", source="test.wish_commit", now=self.clock.now)
        with self.app.state.storage.connect() as conn:  # 替身的绑定表：没装替身时也要查得到（应当是空的）
            conn.execute("CREATE TABLE IF NOT EXISTS plan_link (plan_id TEXT PRIMARY KEY, journey_id TEXT NOT NULL, linked_at TEXT NOT NULL)")

    # ---- 同连接替身（形状＝要请 A 实现的那个） ----
    def wire_plan(self, *, revision: int = 3, fail_link: bool = False, valid_window=None, preconditions: tuple = ()) -> dict:
        """装上计划端口。`fail_link=True` 模拟"绑定那一步抛了"；`valid_window` ＝ A 的 `(valid_from, valid_until)`；
        `preconditions` ＝ A 的 `PlanRef.preconditions`（`web_travel_facts` 的 fact_id，逐条有效期由 A 的端口判）。"""
        seen: dict = {"plan_id": "pl-test-1", "revision": revision, "link_calls": []}

        def ready_plan_in(conn, pet_id: str):
            """返回 A 的**真实** `PlanRef`（不是自造的形状）：按字段名取，位置将来变了也不会错。"""
            row = conn.execute("SELECT plan_id FROM plan_link WHERE plan_id = ?", (seen["plan_id"],)).fetchone()
            if row:
                return None
            valid_from, valid_until = valid_window or (None, None)
            return PlanRef(plan_id=seen["plan_id"], plan_revision=seen["revision"], wish_id="wi-test-1", wish_revision=2,
                           pet_id=pet_id, destination_key=DESTINATION, valid_from=valid_from, valid_until=valid_until,
                           preconditions=preconditions)

        def link_journey_in(conn, plan_id, plan_revision, wish_id, wish_revision, journey_id, now):
            seen["link_calls"].append({"plan_id": plan_id, "revision": plan_revision, "journey_id": journey_id,
                                       "in_transaction": bool(conn.in_transaction)})
            if fail_link:
                raise RuntimeError("绑定计划这一步炸了")
            conn.execute("INSERT INTO plan_link (plan_id, journey_id, linked_at) VALUES (?, ?, ?)",
                         (plan_id, journey_id, now.isoformat()))

        self.journeys.ready_plan_in = ready_plan_in
        self.journeys.link_journey_in = link_journey_in
        return seen

    def wire_commitment(self, blocking: bool) -> dict:
        """装上承诺谓词。真实数据源是 `communicator.owner_asked_stay_home`（归 A，需要 `*_in` 版本）。"""
        seen: dict = {"calls": []}

        def active_commitment_in(conn, pet_id: str, now):
            seen["calls"].append(bool(conn.in_transaction))
            return {"kind": "owner_asked_stay_home", "text": "今天在家陪我吧"} if blocking else None

        self.journeys.active_commitment_in = active_commitment_in
        return seen

    # ---- 查库 ----
    def rows(self, sql: str, *params) -> list:
        with self.app.state.storage.connect() as conn:
            return [tuple(r) for r in conn.execute(sql, params)]

    def journeys_count(self) -> int:
        return self.rows("SELECT COUNT(*) FROM web_journeys WHERE pet_id = ?", self.owner.pet_id)[0][0]

    def fares(self) -> list[str]:
        return [key for (key,) in self.rows(
            "SELECT idempotency_key FROM economy_transactions WHERE pet_id = ? AND idempotency_key LIKE 'web:travel_fee:%'", self.owner.pet_id)]

    def links(self) -> list:
        return self.rows("SELECT plan_id, journey_id FROM plan_link")

    def balance(self) -> int:
        return self.web.economy.wallet(self.owner.pet_id).balance

    def depart(self, **kwargs):
        return self.journeys.depart(self.owner.user_id, self.owner.pet_id, self.owner.home_id, DESTINATION, self.clock.now, **kwargs)

    def nothing_left(self, why: str) -> None:
        self.assertEqual(self.journeys_count(), 0, f"{why}：行程不该留下（取消掉的也算）")
        self.assertEqual(self.fares(), [], f"{why}：旅费不该留下")
        self.assertEqual(self.links(), [], f"{why}：计划绑定不该留下")


class PlanBindingTests(WishCommitBase):
    """T07：计划绑定与行程、旅费在同一个提交边界，一起成功或一起回滚。"""

    def test_the_normal_path_departs_links_and_charges_together(self) -> None:
        plan = self.wire_plan()
        before = self.balance()

        journey = self.depart(plan=PlanChoice(plan["plan_id"], plan["revision"]))

        self.assertEqual(self.journeys_count(), 1)
        self.assertEqual(self.links(), [(plan["plan_id"], journey.journey_id)], "计划绑到了这一趟")
        self.assertEqual(self.fares(), [f"web:travel_fee:{journey.journey_id}"])
        self.assertEqual(self.balance(), before - FEE)
        self.assertTrue(plan["link_calls"][0]["in_transaction"], "绑定必须用写事务里的那个连接")

    def test_a_stale_plan_revision_does_not_depart(self) -> None:
        """等钱期间计划又改过：出发时版本对不上，整笔不做（T05）。"""
        plan = self.wire_plan(revision=5)

        with self.assertRaises(JourneyError) as rejected:
            self.depart(plan=PlanChoice(plan["plan_id"], 4))

        self.assertEqual(rejected.exception.reason, "plan_revision_changed")
        self.nothing_left("计划版本变了")

    def test_a_failure_while_linking_rolls_everything_back(self) -> None:
        plan = self.wire_plan(fail_link=True)
        before = self.balance()

        with self.assertRaises(RuntimeError):
            self.depart(plan=PlanChoice(plan["plan_id"], plan["revision"]))

        self.nothing_left("绑定那一步炸了")
        self.assertEqual(self.balance(), before, "钱也要退回去")

    def test_a_plan_whose_facts_expired_while_saving_up_does_not_depart(self) -> None:
        """等钱那段时间里资料过期了：出发这一刻按 now 再判一次，不拿过期攻略出门（T05）。"""
        plan = self.wire_plan(valid_window=(None, (self.clock.now - timedelta(minutes=1)).isoformat()))

        with self.assertRaises(JourneyError) as rejected:
            self.depart(plan=PlanChoice(plan["plan_id"], plan["revision"]))

        self.assertEqual(rejected.exception.reason, "fact_stale")
        self.nothing_left("资料过期")

    def test_a_plan_still_inside_its_window_departs(self) -> None:
        """正向对照：有有效期、而且还在期内 → 照常出发。只验拒绝那一半的话，永久拒绝也会判成通过。"""
        plan = self.wire_plan(valid_window=((self.clock.now - timedelta(hours=1)).isoformat(), (self.clock.now + timedelta(hours=6)).isoformat()))

        journey = self.depart(plan=PlanChoice(plan["plan_id"], plan["revision"]))

        self.assertEqual(self.links(), [(plan["plan_id"], journey.journey_id)])

    def test_a_plan_without_the_link_port_refuses_rather_than_departing_unlinked(self) -> None:
        """端口没装配：宁可不出发，也不能建出一趟没有计划归属的行程。

        **显式制造"没装配"，不依赖默认值**——这是同一条规矩第三次应验（借车券、承诺闸，这次是计划绑定）：
        组合根接上 `link_journey_in` 的那一刻，靠默认值的用例就会红，
        而**红的位置在用例、成因在组合根**，看到的人第一反应是"用例坏了"。
        这条安全属性本身仍要守住：它是装配出错时的最后一道。
        """
        self.journeys.link_journey_in = None
        with self.assertRaises(JourneyError) as refused:
            self.depart(plan=PlanChoice("pl-test-1", 3))

        self.assertEqual(refused.exception.reason, "plan_link_unavailable")
        self.nothing_left("端口没装配")


class CommitmentGateTests(WishCommitBase):
    """这批争出来的两条语义：闸只对自主路径生效；没装配不静默跳过。"""

    def test_a_blocking_commitment_stops_an_autonomous_departure(self) -> None:
        seen = self.wire_commitment(blocking=True)

        with self.assertRaises(JourneyError) as rejected:
            self.depart(honor_commitments=True)

        self.assertEqual(rejected.exception.reason, "commitment_active")
        self.assertEqual(seen["calls"], [True], "谓词要在写事务里被问，且只问一次")
        self.nothing_left("主人说了今天待在家")

    def test_the_owners_own_click_is_not_blocked_by_a_commitment(self) -> None:
        """主人自己说了待在家、转头自己点出发：那是改主意，不该拦（合同 15 节定稿）。"""
        seen = self.wire_commitment(blocking=True)
        before = self.balance()

        journey = self.depart()  # 路由那条路不传 honor_commitments

        self.assertEqual(self.journeys_count(), 1)
        self.assertEqual(self.fares(), [f"web:travel_fee:{journey.journey_id}"])
        self.assertEqual(self.balance(), before - FEE)
        self.assertEqual(seen["calls"], [], "默认不问承诺，别顺手把主人也拦了")

    def test_an_autonomous_departure_with_no_commitment_still_goes(self) -> None:
        """正向对照：闸开着但没有拦住出行的承诺时，照常出发。"""
        seen = self.wire_commitment(blocking=False)

        journey = self.depart(honor_commitments=True)

        self.assertEqual(self.journeys_count(), 1)
        self.assertEqual(self.fares(), [f"web:travel_fee:{journey.journey_id}"])
        self.assertEqual(seen["calls"], [True], "问过了，只是没有拦住的承诺")

    def test_honoring_commitments_without_the_port_refuses_rather_than_skipping(self) -> None:
        """明确要闸却没有闸可用：拒绝，而不是当成"没有承诺"放行——静默跳过保护是这批最不能出的错。

        **显式制造"没装配"，不依赖默认值**：组合根现在已经把谓词接上了（`web_agent_wiring.py`），
        但"调用方要闸而闸缺席时必须拒绝"这条安全属性仍要守住——那是装配出错时的最后一道。
        """
        self.journeys.active_commitment_in = None
        with self.assertRaises(JourneyError) as refused:
            self.depart(honor_commitments=True)

        self.assertEqual(refused.exception.reason, "commitment_gate_unavailable")
        self.nothing_left("要闸却没有闸")


if __name__ == "__main__":
    unittest.main()
