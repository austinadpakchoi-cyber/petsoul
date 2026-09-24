"""心愿轮接到真实事实上之后的行为（包 B，TRV-01 接线）。

策略本身在 `test_web_wish_policy.py` 里按纯函数验过。**这一份验的是另一件事：两边接上之后**——
今天连着三次都栽在这层（`plan_stale` 算法错、`handled_triggers` 填不满、算了 A 的等待原因），
**共同点是两个各自正确的模块，接口理解不一致时双方的单测都绿**：它们的判断从没在同一个进程里相遇过。
所以这一份一律走**真实装配**：真的 `web.travel.wishes`、真的钱包、真的通讯器。

**冷却会把大部分轮次挡在 `cooling_down`，那是设计意图**（I 2026-09-24 提醒）。
所以判据三段都钉：第一轮有动作 → 随后若干轮没有 → 过了冷却又有。
只钉"有动作"会让每轮都动的实现绿，只钉"没动作"会让一律不动的实现绿。
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from app.web_agent.wish_policy import LIFE_SIDE, SkipReason, WaitingReason, WishAction
import app.web_agent.life as life_module
from app.web_agent.wish_wiring import WishProposal, bind_ready_plan, bind_wish_round
from app.web_platform.budget import BudgetLedger
from app.web_travel.model import LIFE_REASONS, RESEARCH_REASONS
from travel_wish_fakes import SEA, FakeResearchPort
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase

SEASIDE = [{"destination_key": "local:cafe", "name": "海边的小咖啡馆", "city": "香港"}]


class WaitingReasonOwnershipTests(unittest.TestCase):
    """两个写入方、两份清单，**必须对得上**——而"对得上"这件事没有任何东西会主动提醒。

    存储上就是两列（`m1700_travel_wish.py:9`）：`life_waiting_json` 归 B、`research_waiting_json` 归 A。
    我先前把 A 那一半也算了一遍：**写过去会被 `WishRejected` 拒收**，
    而且重算的一份迟早与 A 存的不一致，于是每一轮都判成"变了"、每一轮写一次（静默）。

    这里**直接 import 两侧来比**：测试文件同时引两边**不会**倒生产依赖方向——
    `dependency_gate` 只扫 `app/`（`scripts/dependency_gate.py:27` 的 `APP_ROOT`），我核过。
    """

    def test_the_two_writers_agree_on_who_writes_what(self) -> None:
        self.assertEqual(set(LIFE_SIDE), set(LIFE_REASONS),
                         "B 的 LIFE_SIDE 与 A 的 LIFE_REASONS 对不上：两边都要改")
        self.assertEqual(set(LIFE_SIDE) & set(RESEARCH_REASONS), set(),
                         "两个写入方的清单不能有交叠——交叠的那个码会被后写的一方冲掉")
        self.assertEqual(set(LIFE_SIDE) | set(RESEARCH_REASONS), {member.value for member in WaitingReason},
                         "两份合起来必须正好是合同 §5.2 的全集：少一个就没人写，多一个就没人认")


class WishRoundTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("wish-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.pet = self.owner.pet_id
        self.asked: list[str] = []
        self.round = self.bind(self.propose)

    def bind(self, propose):
        return bind_wish_round(wishes=self.web.travel.wishes, projector=self.web.projector, economy=self.web.economy,
                               journeys=self.web.journeys, storage=self.web.journeys.storage, propose=propose)

    def propose(self, user_id, pet_id, trigger, now) -> WishProposal:
        """替身大脑：不调模型，永远想去同一个地方。记下每次被问到的时刻。"""
        self.asked.append(now.isoformat())
        return WishProposal(candidates=list(SEASIDE), selected=0, owner_reason="想去海边听一会儿浪", funds_goal=40)

    def tick(self, **over):
        """跑一轮心愿。**不能叫 run**——那是 `TestCase.run` 的名字，覆盖掉它会让 setUp 根本不跑，
        而现象是每条用例都在 `self.round` 上 AttributeError（第一版就是这样）。"""
        return self.round(self.owner.user_id, self.pet, over.get("now", self.clock.now), activated=True)

    def wish(self):
        return self.web.travel.wishes.read(self.pet)

    def test_the_default_assembly_actually_runs_the_wish_round(self) -> None:
        """**默认装配里真的挂上了这一轮**——没有这条，下面每一条都可能只在我手搭的对象上成立。

        这正是"测回调的会静悄悄地绿、测正式入口的在接线消失时才会红"：
        下面那些用例自己 `bind_wish_round`，**组合根一行都不接它们照样全绿**。

        挂点在 I 的 `web_composition.py`（心愿轮要 `travel.wishes`，那是它装配的），
        CR 已给。**在它接上之前这一条是红的，红得对。**
        """
        names = [name for name, _ in self.web.ticker.jobs]

        self.assertIn("wishes", names, f"世界线没有心愿轮这个任务：{names}")

    def test_the_first_round_really_forms_a_wish(self) -> None:
        """对照组。这一条要是红了，下面每一条的"没动作"都毫无意义。"""
        decision = self.tick()

        self.assertEqual(decision.action, WishAction.ASK_BRAIN.value)
        self.assertEqual(len(self.asked), 1, "问了大脑一次")
        self.assertIsNotNone(self.wish(), "心愿真的落库了")

    def test_the_next_rounds_do_not_ask_again_and_the_day_after_does(self) -> None:
        """三段都钉：第一轮有动作 → 随后若干轮没有 → 过了冷却又有。

        只钉中间那段，一条"一律不推进"的实现也会绿；只钉两头，一条"每轮都问"的实现也会绿。
        """
        self.tick()
        self.assertEqual(len(self.asked), 1)

        for minutes in (15, 30, 45, 60, 6 * 60):  # 生活评估是 15 分钟一跳
            self.tick(now=self.clock.now + timedelta(minutes=minutes))
        self.assertEqual(len(self.asked), 1, "冷却期间一次都不该再问大脑")

        self.web.travel.wishes.cancel(self.wish().wish_id, self.wish().wish_revision)  # 上一个心愿收尾，才谈得上再想一个
        self.tick(now=self.clock.now + timedelta(hours=25))

        self.assertEqual(len(self.asked), 2, "过了 24 小时冷却该再想一次")

    def test_a_wage_arriving_gets_through_the_cooldown(self) -> None:
        """T03 的触发那一半：工资到账是**新事件**，不受冷却限制。

        与上一条只差一个变量：同样在冷却期内，这次多了一笔真实工钱入账。
        入账走真实账本（`web_job_income`），不直接改钱包。
        """
        self.tick()
        self.web.travel.wishes.cancel(self.wish().wish_id, self.wish().wish_revision)
        later = self.clock.now + timedelta(hours=2)

        self.web.economy.apply(self.pet, 30, "web_job_income", f"web:job:probe-{self.pet}", reason="打工的工钱",
                               source="web.journey.work", now=later)
        self.tick(now=later + timedelta(minutes=1))

        self.assertEqual(len(self.asked), 2, "工资到账之后该重新想一想，不该被冷却挡住")

    def test_a_settled_wish_does_not_block_the_next_one_forever(self) -> None:
        """取消之后 TA 还能再想一个。**这条是修出来的**，不是预防性的。

        A 的 `read_in` 在没有进行中心愿时**有意返回最近一条**（已关联／已完成／已取消）——
        那是给页面说清楚现状用的。我第一版原样交给策略，`_hard_skip` 判 `wish_closed`、
        于是**取消一次之后这只宠物再也形成不了新心愿**，而且一声不响。
        方案 §9 的"已关闭心愿不自动复活"说的是别把旧的救活，不是别再想新的。

        断言挑的是 `skip_reason` 而不是"有没有再问大脑"：冷却期内两者都不会问，
        **只有原因码能区分"这一轮还没到点"和"它被那条已取消的心愿永久挡住了"**。
        """
        self.tick()
        self.web.travel.wishes.cancel(self.wish().wish_id, self.wish().wish_revision)

        soon = self.round(self.owner.user_id, self.pet, self.clock.now + timedelta(minutes=15), activated=True)

        self.assertEqual(soon.skip_reason, SkipReason.COOLING_DOWN.value, "该是「还没到点」，不是「被关闭的心愿挡住」")
        self.assertNotEqual(soon.skip_reason, SkipReason.WISH_CLOSED.value)

    def test_without_a_proposer_nothing_happens_at_all(self) -> None:
        """没接提案器**＝不形成心愿，也不记「考虑过」**——不接就什么都不发生。

        反过来做（记一笔空的）会把冷却推后 24 小时，而那一轮其实什么也没想。
        """
        quiet = self.bind(None)

        decision = quiet(self.owner.user_id, self.pet, self.clock.now, activated=True)

        self.assertEqual(decision.action, WishAction.ASK_BRAIN.value, "策略仍然认为值得想一次")
        self.assertIsNone(self.wish(), "但没有提案器就不该有心愿")
        self.assertEqual(self.round(self.owner.user_id, self.pet, self.clock.now + timedelta(minutes=15), activated=True).action,
                         WishAction.ASK_BRAIN.value, "冷却没有被那一轮空转推后")

    def test_running_low_on_coins_writes_only_the_life_side(self) -> None:
        """钱不够时写回去的**只有生活侧那一条**。

        把整个 `waiting` 传给 `update_waiting` 会被 `WishRejected` 拒收——
        而研究侧此刻**确实非空**（没接 research port，心愿停在 `research_pending`，那是诚实的状态），
        所以这条用例里那个错误是真的会触发，不是假设。
        """
        self.tick()
        broke = self.clock.now + timedelta(hours=25)

        decision = self.round(self.owner.user_id, self.pet, broke, activated=True)

        self.assertEqual(decision.life_waiting, (WaitingReason.MISSING_FUNDS.value,), "钱不够是我写的那一条")
        self.assertIn(WaitingReason.RESEARCH_PENDING.value, decision.waiting, "前提：研究侧此刻确实非空")
        self.assertNotIn(WaitingReason.RESEARCH_PENDING.value, decision.life_waiting, "研究侧不能混进我要写回去的那一份")
        self.assertIn(WaitingReason.MISSING_FUNDS.value, self.wish().waiting_reasons, "写进去了")


class ReadyPlanDepartureTests(WebPlatformTestBase):
    """攒够了、资料也齐了之后，**那份计划真的会变成一次出发**——走真实装配、真实研究流水线。

    研究端口用 A 的共享替身（`travel_wish_fakes`）：**不联网、零付费**。
    **注意这里后置注入 `port` ＋ `ledger`，绕过了 `install_travel` 的成对检查**——
    那条检查是防生产上"接了端口没接账本就发真钱"，这里两样都给了替身。
    **别把这两行抄进生产装配。**
    """

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("plan-owner")
        self.owner.adopt_and_move_in("adopt-lan")
        self.pet = self.owner.pet_id
        original = life_module._roll
        life_module._roll = lambda *parts: 0.0  # 这一轮一定想出门：否则"没去成"可能只是没掷中
        self.addCleanup(lambda: setattr(life_module, "_roll", original))
        # **先留住组合根接的那一个**，presence 用例要验的是它，不是我下面手接的这个
        self.assembled_ready_plan_of = self.web.life.ready_plan_of
        self.web.life.ready_plan_of = bind_ready_plan(self.web.travel.wishes, self.web.journeys.storage)

    def ready_plan(self, destination_key: str):
        """真造一份就绪计划：propose → 替身研究端口 → `run_pending` 发布。名字用 A 替身里那个地方。"""
        self.web.travel.wishes.propose(pet_id=self.pet, user_id=self.owner.user_id, trigger_event_id=f"t-{destination_key}",
                                       candidates=[{**SEA, "destination_key": destination_key}], selected=0,
                                       interest_tags=(), owner_reason="想去海边听一会儿浪", funds_goal=0, now=self.clock.now)
        self.web.travel.research.port = FakeResearchPort()
        self.web.travel.research.ledger = BudgetLedger(self.web.journeys.storage)
        self.web.travel.research.run_pending()
        view = self.web.travel.wishes.read(self.pet)
        self.assertEqual(view.status, "ready", f"前提不成立：计划没就绪（waiting={view.waiting_reasons}）")
        return view

    def journey(self):
        return self.web.journeys.repo.active_for_pet(self.pet)

    def test_the_default_assembly_binds_the_ready_plan_hook(self) -> None:
        """默认装配要把这个钩子接上，否则下面两条只在我手接的对象上成立。

        不接的后果是**安静的**：`ready_plan_of` 默认返回 None，规则生活照原样掷骰选目的地，
        **一条用例都不会红**——攒了很久的那个地方只是永远轮不到。

        断言的是**行为**（真造一份就绪计划，看组合根那个钩子认不认得出来），
        不是名字或类型：钩子叫什么、是不是 lambda，都不说明它接没接对东西。
        """
        self.ready_plan("harbour_cafe")

        picked = self.assembled_ready_plan_of(self.pet)

        self.assertIsNotNone(picked, "组合根没接 ready_plan_of：就绪的计划永远不会被选中，而且一条用例都不会红")
        self.assertEqual(picked.destination_key, "harbour_cafe")

    def test_a_ready_plan_becomes_a_real_departure(self) -> None:
        """正向：计划指向一个**引擎去得了**的地方 → TA 就去那儿，而且旅程绑上了这份计划。"""
        view = self.ready_plan("harbour_cafe")

        self.web.life.run(self.clock.now)

        trip = self.journey()
        self.assertIsNotNone(trip, "该出门了")
        self.assertEqual(trip.destination_key, "harbour_cafe", "该去计划里那个地方，不是随机挑一个")
        self.assertEqual(self.web.travel.wishes.read(self.pet).status, "linked", "心愿要绑到这趟真实旅程上")
        self.assertEqual(self.web.travel.wishes.read(self.pet).journey_id, trip.journey_id)
        self.assertEqual(view.plan_revision, 1, "前提：这是第 1 版计划")

    def test_a_plan_the_engine_cannot_execute_is_not_forced(self) -> None:
        """反向：计划指向**引擎还没接的地方** → 不强推，照常过 TA 自己的日子。

        这不是缺陷，是方案 §8「未接入的目的地最多保存为心愿」生效的样子。
        与上一条只差一个变量：同样是一份就绪计划，只是那个键不在出发选项里。
        """
        self.ready_plan("hk-repulse-bay")
        self.assertNotIn("hk-repulse-bay", [o.destination_key for o in
                                            self.web.journeys.destinations(self.owner.user_id, self.pet, self.owner.home_id)],
                         "前提：这个目的地确实不在出发选项里")

        self.web.life.run(self.clock.now)

        trip = self.journey()
        self.assertTrue(trip is None or trip.destination_key != "hk-repulse-bay", "去不了的地方不该被强推")
        self.assertEqual(self.web.travel.wishes.read(self.pet).status, "ready", "心愿仍然就绪地等着，没有被作废")


if __name__ == "__main__":
    unittest.main()
