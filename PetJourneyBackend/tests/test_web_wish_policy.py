"""心愿策略：什么时候值得重新想、还差什么、够不够交接（包 B，TRV-01；验收 T02/T03/T05）。

**每一条"没动作"都先有一个"同样的事实真的会动作"的对照。**
没有那个对照，"没形成心愿"可能只是因为这组事实本来就不会形成心愿——那样的断言永远绿，等于没写。
这一批开头刚吃过这个亏（`test_web_life_maintenance.py` 的第一条对照就是为它加的）。

写法上有意如此：`FACTS` 是一只**万事俱备**的宠物，每条用例用 `replace` **只改自己要验的那一个变量**。
两组事实之间只差一个字段，"它被拦住了"才真的说明是那个字段拦的。

被测的是纯函数：不连库、不起线程、不碰租约、不调模型，所以这个文件里没有推时钟与 worker 的那些坑。
"""

from __future__ import annotations

import unittest
from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone

from app.web_agent.wish_policy import (LIFE_SIDE, FundsGap, SkipReason, WaitingReason, WishAction, WishCandidate,
                                       WishFacts, WishPolicy, WishState, WishStatus, evaluate)
from app.web_runtime.heartbeat_policy import HeartbeatPolicy

NOW = datetime(2026, 9, 24, 4, 0, tzinfo=timezone.utc)
POLICY = WishPolicy()

WISH = WishState(wish_id="W-1", revision=3, status=WishStatus.ACTIVE.value, destination_key="local:cafe",
                 title="想去海边坐一会儿", funds_goal=40, waiting=())
# 万事俱备：有心愿、A 那边研究侧一条等待原因都没留、钱够、没承诺、没在路上、没被暂停。
# 默认结论应当是 HAND_OFF——这一点由 test_reaching_the_goal_hands_off 当场证明，其余用例才能拿它当基线。
FACTS = WishFacts(pet_id="PJ-WISH", balance=100, wish=WISH)


class ContractEnumTests(unittest.TestCase):
    """契约枚举与实现取值的**双向**不变量（TRV-00 §0.2 要求每个新契约枚举都有一条）。

    下面两份清单是从 TRV-00 §5.1／§5.2 **逐字抄来的**，故意重复写一遍：
    实现多一个码 → 红；合同多一个码 → 也红。无论从哪边动手都会在这里当场停下。

    **为什么不 import 合同的 DTO 来消除这份重复**：那会让领域层依赖对外 schema，
    依赖方向倒过来、撞 `dependency_gate`（样板见 `tests/test_web_moderation_contract.py`）。
    何况 TRV-00 §10 第 2 条写明 DTO 的文件名与类名尚未登记，现在也没有可 import 的东西。
    I 的 DTO 落地后，把下面的字面清单换成 import 即可，两边仍然双向。
    """

    def test_waiting_reasons_match_the_contract_both_ways(self) -> None:
        contract = {"missing_funds", "quota_denied", "research_pending", "research_unknown", "research_failed",
                    "fact_stale", "plan_stale", "fact_unverified", "fact_conflicting", "weather_unsuitable",
                    "commitment_active", "maintenance"}

        self.assertEqual({member.value for member in WaitingReason}, contract,
                         "等待原因两边对不上：实现在 app/web_agent/wish_policy.py 的 WaitingReason，"
                         "合同在 TRV-00-contract-v1.md §5.2。**两边都要改。**")

    def test_statuses_match_the_contract_both_ways(self) -> None:
        contract = {"active", "ready", "linked", "completed", "cancelled"}

        self.assertEqual({member.value for member in WishStatus}, contract,
                         "业务主状态两边对不上：实现在 WishStatus，合同在 TRV-00 §5.1。"
                         "研究任务与手账图各有自己的状态，不要往这里加。")


class CooldownIsItsOwnKnobTests(unittest.TestCase):
    """冷却必须是心愿自己的常量。接到心跳那两个旋钮上，心愿会每 15 分钟被重新考虑一次。"""

    def test_the_cooldown_is_a_day_not_a_heartbeat_interval(self) -> None:
        """这条直接钉住数量级。心跳的两个旋钮是 15 分钟与 6 小时，差两个数量级（TRV-00 §5.5）。"""
        heartbeat = HeartbeatPolicy()

        self.assertEqual(POLICY.reconsider_interval, timedelta(hours=24), "方案 §9 要的是至少 24 小时")
        self.assertNotIn(POLICY.reconsider_interval, (heartbeat.idle_review_interval, heartbeat.max_review_interval),
                         "心愿冷却接到了心跳的复查间隔上——那会让心愿每 15 分钟被重新考虑一次")

    def test_a_heartbeat_sized_cooldown_is_refused(self) -> None:
        """不是只靠默认值对：手滑接上心跳那两个旋钮，构造当场就要拦住。"""
        heartbeat = HeartbeatPolicy()

        for wrong in (heartbeat.idle_review_interval, heartbeat.max_review_interval, timedelta(0)):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                WishPolicy(reconsider_interval=wrong)

    def test_the_gate_reads_the_past_not_a_deadline_handed_to_it(self) -> None:
        """闸算截止时刻用的是**本策略的常量**，不是谁传进来的值（TRV-00 §17，起因是 Q 的实测）。

        两半各自都不够：
        · 只断言"没有 `reconsider_after` 这个字段"——将来有人加回来、闸又读它，字段在、断言绿；
        · 只断言"24 小时内不放行"——传一个 15 分钟的截止时刻也能让它成立，那验的是闸在响，不是冷却有多长。

        所以这里**同一组事实、只换策略的间隔**：默认 24 小时下已经过了冷却，48 小时下还没过。
        答案跟着策略常量走，就说明闸确实在用它算，而不是在读一个存取过一轮的值。
        """
        self.assertNotIn("reconsider_after", {f.name for f in fields(WishFacts)},
                         "`reconsider_after` 不该是输入：闸一旦能读到别人算好的截止时刻，下限就守不住了")
        long_ago = replace(FACTS, wish=None, last_considered_at=NOW - timedelta(hours=30))

        self.assertEqual(evaluate(long_ago, POLICY, NOW).action, WishAction.ASK_BRAIN.value, "默认 24 小时：30 小时前考虑过，该再想了")
        patient = evaluate(long_ago, WishPolicy(reconsider_interval=timedelta(hours=48)), NOW)
        self.assertEqual(patient.action, WishAction.SKIP.value)
        self.assertEqual(patient.skip_reason, SkipReason.COOLING_DOWN.value, "48 小时的策略下，30 小时前那次还在冷却里")

    def test_only_asking_the_brain_counts_as_having_considered(self) -> None:
        """`considered_at` 非空才算"这一次考虑过"。刷新一次等待原因**不算**，否则冷却会被白白推后。

        这条由策略给、不由集成层自己判：否则"哪些动作算考虑过"会在两边各写一份，迟早分叉。
        """
        asked = evaluate(replace(FACTS, wish=None, last_considered_at=None), POLICY, NOW)
        refreshed = evaluate(replace(FACTS, balance=10, wish=replace(WISH, waiting=(WaitingReason.PLAN_STALE.value,))), POLICY, NOW)

        self.assertEqual((asked.action, asked.considered_at), (WishAction.ASK_BRAIN.value, NOW))
        self.assertEqual(refreshed.action, WishAction.UPDATE_WAITING.value, "前提：这一组确实走的是刷新等待原因那条路")
        self.assertIsNone(refreshed.considered_at, "只是刷新等待原因，不该把冷却往后推")

    def test_the_very_first_time_is_not_blocked(self) -> None:
        """对照组：从没想过的宠物必须能想第一次，否则一只没有任何事件的宠物永远不会有心愿。"""
        fresh = replace(FACTS, wish=None, last_considered_at=None)

        self.assertEqual(evaluate(fresh, POLICY, NOW).action, WishAction.ASK_BRAIN.value)

    def test_a_plain_tick_inside_the_cooldown_thinks_about_nothing(self) -> None:
        waiting = replace(FACTS, wish=None, last_considered_at=NOW - timedelta(hours=5))

        decision = evaluate(waiting, POLICY, NOW)

        self.assertEqual(decision.action, WishAction.SKIP.value)
        self.assertEqual(decision.skip_reason, SkipReason.COOLING_DOWN.value)

    def test_a_new_valid_event_gets_through_inside_the_cooldown(self) -> None:
        """正向对照：工资到账这种新的有效事件**不受冷却限制**，该让 TA 立刻重新想一想。

        没有这一条，上面那条"冷却挡住了"也可能只是因为它把什么都挡住了。
        """
        waiting = replace(FACTS, wish=None, last_considered_at=NOW - timedelta(hours=5))
        woken = replace(waiting, trigger=_trigger("ev-wage-1"))

        self.assertEqual(evaluate(woken, POLICY, NOW).action, WishAction.ASK_BRAIN.value)


class ReplayTests(unittest.TestCase):
    """T02：同一有效事件重复投递、重复 tick、多次 GET —— 不新增心愿、不请求大脑、零外发。"""

    def test_a_fresh_event_forms_a_wish(self) -> None:
        """对照组。这一条要是红了，下面三条的"什么都没发生"就毫无意义。"""
        first = replace(FACTS, wish=None, trigger=_trigger("ev-1"))

        self.assertEqual(evaluate(first, POLICY, NOW).action, WishAction.ASK_BRAIN.value)

    def test_the_same_event_delivered_again_does_nothing(self) -> None:
        """注意这一条**没有心愿**（`wish=None`）——那正是它要守的场景。

        大脑上一轮说了「留在家、不形成心愿」，所以库里没有任何以这个事件为键的心愿行。
        **任何「已处理过的 id 集合」都查不到它**，于是重放会被当成新事件、每个 tick 再问一次大脑。
        改成按 `occurred_at` 与 `last_considered_at` 比之后，这种情况自然落在重放那一侧。
        """
        # 事件发生在 5 小时前、我们 4 小时前才考虑过——那一次已经看见它了，再投一次不是新消息
        again = replace(FACTS, wish=None, trigger=_trigger("ev-1", hours_ago=5), last_considered_at=NOW - timedelta(hours=4))

        decision = evaluate(again, POLICY, NOW)

        self.assertEqual(decision.action, WishAction.SKIP.value)
        self.assertEqual(decision.skip_reason, SkipReason.TRIGGER_REPLAYED.value)
        self.assertIsNone(decision.candidate, "没有心愿就不该凭空造一个候选出来")

    def test_another_new_event_still_gets_through(self) -> None:
        """正向对照：重放之后再来一个**新的** trigger_event_id，必须仍然能推进。

        只验"重复不新增"的话，一条"一律不推进"的实现也会全绿。
        """
        # 这个事件发生在上次考虑（4 小时前）**之后**，所以是真的新消息
        after_replay = replace(FACTS, wish=None, trigger=_trigger("ev-2"), last_considered_at=NOW - timedelta(hours=4))

        self.assertEqual(evaluate(after_replay, POLICY, NOW).action, WishAction.ASK_BRAIN.value)

    def test_a_replay_never_starves_a_wish_that_is_already_ready(self) -> None:
        """重放挡的是"再花一次模型调用去想"，**不是**"已经想好、也不缺东西的那个"。

        反过来做就会把本该醒来的那次机会吞掉，TA 明明钱够了却要再等一整轮——
        这正是本批刚修过的那一类缺陷，"少做一次"在这里不是安全的默认值。
        """
        replayed = replace(FACTS, trigger=_trigger("ev-1", hours_ago=5), last_considered_at=NOW - timedelta(hours=4))

        self.assertEqual(evaluate(replayed, POLICY, NOW).action, WishAction.HAND_OFF.value)


class FundsAndRevalidationTests(unittest.TestCase):
    """T03（钱不够先存着，到账后能走）与 T05（等钱期间钱包/承诺/版本/资料变化要重新复核）。"""

    def test_reaching_the_goal_hands_off(self) -> None:
        """基线兼正向对照：万事俱备时结论就是交接。其余用例都以这条为参照。

        注意交接**不等于**已经出发——能不能走仍由 C 现有的 offers 规则决定。
        """
        decision = evaluate(FACTS, POLICY, NOW)

        self.assertEqual(decision.action, WishAction.HAND_OFF.value)
        self.assertEqual(decision.waiting, ())
        self.assertIsNone(decision.funds)

    def test_short_of_the_goal_keeps_the_wish_and_does_not_hand_off(self) -> None:
        """钱不够只是"先存着"：心愿保留，等待原因写明缺钱，**不交接**。"""
        broke = replace(FACTS, balance=10)

        decision = evaluate(broke, POLICY, NOW)

        self.assertNotEqual(decision.action, WishAction.HAND_OFF.value)
        self.assertEqual(decision.waiting, (WaitingReason.MISSING_FUNDS.value,))
        self.assertEqual(decision.expected_revision, WISH.revision, "写回时要带这次读到的版本，旧评估不许确认它没读到的新版本")

    def test_the_gap_says_how_much_is_missing(self) -> None:
        """缺什么页面就说什么：只写一个 `missing_funds` 码，玩家不知道还差多少。"""
        decision = evaluate(replace(FACTS, balance=10), POLICY, NOW)

        self.assertEqual(decision.funds, FundsGap(target_coins=40, current_coins=10))
        self.assertEqual(decision.funds.short_by, 30)

    def test_funds_are_mine_to_write_but_quota_is_not(self) -> None:
        """游戏金币不够与平台额度不够是两件事（方案 §10 点名），而且**落在两个不同的轴上**。

        缺钱是**等待原因**、由 B 写进心愿；额度不够只影响"要不要再花一次模型调用"，
        是 `SkipReason` 那一轴，**`quota_denied` 那个等待码归 A 写**（`LIFE_REASONS` 只有三条）。
        我原先两个都往 `waiting` 里塞——那样传给 `update_waiting` 会被 `WishRejected` 拒收。
        """
        broke = evaluate(replace(FACTS, balance=10), POLICY, NOW)
        throttled = evaluate(replace(FACTS, wish=None, quota_available=False, last_considered_at=None), POLICY, NOW)

        self.assertEqual(broke.life_waiting, (WaitingReason.MISSING_FUNDS.value,), "缺钱是我写的")
        self.assertEqual(throttled.skip_reason, SkipReason.QUOTA_DENIED.value, "额度不够只挡住「再想一次」")
        self.assertEqual(throttled.waiting, (), "额度不够不由我写成等待原因——那个码归 A")

    def test_a_plan_built_against_an_older_wish_revision_is_not_handed_off(self) -> None:
        """T05 的版本那一路：A 判出这版计划按的是旧版心愿，就不能拿它去出发。

        **算是不是过时归 A，守住"过时就不交接"归我**——这里验的是后者。
        我原先自己按 `wish_revision` 算，那是错的：那是乐观并发号，`update_waiting` 每动一次就 +1，
        判出来会永远过时、心愿永远到不了 ready（A 4bef 指出，我核过合同 §2 确认）。

        **披露一处可证范围**：本批没有任何命令能改心愿内容（换方向＝取消后新建），
        所以 A 目前**产生不出** `plan_stale`。这条用例验的是"A 给了这个结论之后我不交接"，
        **不是**"这个结论会被正确产生"——后者等 A 那边有了改内容的路才谈得上。

        顺带钉住两侧的分工：研究侧的码**原样出现在 `waiting` 里**（页面要显示），
        但**不出现在 `life_waiting` 里**（那是我能写的那三条）。
        把整个 `waiting` 传给 `update_waiting` 会被 `WishRejected` 拒收。
        """
        moved_on = replace(FACTS, wish=replace(WISH, waiting=(WaitingReason.PLAN_STALE.value,)))

        decision = evaluate(moved_on, POLICY, NOW)

        self.assertNotEqual(decision.action, WishAction.HAND_OFF.value)
        self.assertEqual(decision.waiting, (WaitingReason.PLAN_STALE.value,), "A 的研究侧原因要原样透传给页面")
        self.assertEqual(decision.life_waiting, (), "研究侧不是我写的，不能混进我要写回去的那一份")
        self.assertEqual(decision.skip_reason, SkipReason.UNCHANGED.value, "生活侧没变就不写：研究侧变了不该由我触发一次写")
        self.assertEqual(decision.expected_revision, WISH.revision, "写回时仍要带这次读到的心愿版本")

    def test_a_new_commitment_stops_a_wish_that_would_otherwise_hand_off(self) -> None:
        """T05 的承诺那一路：答应过的事还没兑现，先别惦记新地方。

        对照就在同一条用例里：同一组事实、只多一条承诺——上面那条基线已经证明它本来会交接。
        """
        promised = replace(FACTS, commitments=("reply:M-3",))

        decision = evaluate(promised, POLICY, NOW)

        self.assertEqual(decision.action, WishAction.SKIP.value)
        self.assertEqual(decision.skip_reason, SkipReason.COMMITMENT_ACTIVE.value)
        self.assertIn(WaitingReason.COMMITMENT_ACTIVE.value, decision.waiting, "跳过归跳过，页面仍要知道它在等什么")


class GateAndCandidateTests(unittest.TestCase):
    def test_the_hard_gates_change_nothing_while_the_same_facts_otherwise_act(self) -> None:
        """维护态、在路上、已收尾：一律什么都不做。每一条都与同一组会交接的基线只差一个字段。"""
        cases = ((replace(FACTS, maintenance=True), SkipReason.MAINTENANCE.value),
                 (replace(FACTS, active_journey=True), SkipReason.ACTIVE_JOURNEY.value),
                 (replace(FACTS, activated=False), SkipReason.NOT_ACTIVATED.value),
                 (replace(FACTS, wish=replace(WISH, status=WishStatus.COMPLETED.value)), SkipReason.WISH_CLOSED.value))

        self.assertEqual(evaluate(FACTS, POLICY, NOW).action, WishAction.HAND_OFF.value, "前提：这组事实本来会动作")
        for facts, expected in cases:
            with self.subTest(expected=expected):
                decision = evaluate(facts, POLICY, NOW)
                self.assertEqual(decision.action, WishAction.SKIP.value)
                self.assertEqual(decision.skip_reason, expected)

    def test_a_candidate_can_never_be_executable_and_has_no_departure_field(self) -> None:
        """有心愿不等于可以出发。靠文档约定"别拿它去出发"迟早有人拿它去出发，所以类型上就不给。"""
        candidate = evaluate(replace(FACTS, balance=10), POLICY, NOW).candidate

        self.assertFalse(candidate.executable)
        self.assertEqual(candidate.blocked_by, (WaitingReason.MISSING_FUNDS.value,))
        # 断言的是**设计本身**：executable 是只读属性、不是字段，所以没有任何赋值路径能把它改成真。
        # 不去断言"赋值会抛哪一种异常"——frozen + slots 下 CPython 抛的是 TypeError 而不是
        # AttributeError（生成的 __setattr__ 里 super(cls, self) 拿到的是加 slots 之前那个类）。
        # 那是解释器的实现细节，钉住它只会让这条用例在换版本时无缘无故变红。
        self.assertNotIn("executable", {f.name for f in fields(WishCandidate)}, "executable 一旦成了字段就能被赋值")
        self.assertIsNone(type(candidate).__dict__["executable"].fset, "executable 不能有 setter")
        for forbidden in ("offer_id", "valid_until", "fee", "destination"):
            self.assertFalse(hasattr(candidate, forbidden), f"候选上出现了能喂给 depart 的字段：{forbidden}")
        self.assertEqual(set(WishCandidate.__slots__), {"wish_id", "wish_revision", "destination_key", "title", "blocked_by"})

    def test_an_unchanged_waiting_set_is_not_written_again(self) -> None:
        """等待原因跟上次一模一样就不写：否则每一轮都往心愿上写一次，版本白白涨、页面白白抖。

        变了才写——由下半条当场对照。
        """
        same = replace(FACTS, balance=10, wish=replace(WISH, waiting=(WaitingReason.MISSING_FUNDS.value,)))
        changed = replace(FACTS, balance=10, wish=replace(WISH, waiting=(WaitingReason.RESEARCH_PENDING.value,)))

        self.assertEqual(evaluate(same, POLICY, NOW).skip_reason, SkipReason.UNCHANGED.value)
        self.assertEqual(evaluate(changed, POLICY, NOW).action, WishAction.UPDATE_WAITING.value)


def _trigger(event_id: str, *, hours_ago: float = 1 / 60):
    """`hours_ago` 决定它算不算「新事件」：比 `last_considered_at` 更晚发生才算新。"""
    from app.web_agent.wish_policy import WishTrigger

    return WishTrigger(event_id=event_id, kind="wage_settled", occurred_at=NOW - timedelta(hours=hours_ago))


if __name__ == "__main__":
    unittest.main()
