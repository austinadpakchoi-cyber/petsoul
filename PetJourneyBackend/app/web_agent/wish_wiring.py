"""把心愿策略接到真实事实上：一次读齐 → `evaluate` → 按结论调 A 的端口（包 B，TRV-01）。

策略本身是纯函数（`wish_policy.py`），这里负责**它碰不到的那一半**：从哪读、写回哪。
放在单独文件是因为组合根 `web_agent_wiring.py` 顶在门禁上限，只能加赋值语句。

## 谁写什么

**心愿的持久化只有 A 一个写入方**（TRV-00 §4.1）。这里一行 SQL 都不往心愿表写，只调它的端口。
而且等待原因**按写入方分两列**（`m1700_travel_wish.py:9`）：

    life_waiting_json      B 写：missing_funds / commitment_active / maintenance
    research_waiting_json  A 写：研究与资料那一半

所以写回去的是 `decision.life_waiting`（**只有生活侧三条**），不是 `decision.waiting`——
后者还含 A 那一半，`update_waiting` 收到会 `WishRejected`。这一条踩过一次。

## 触发源

方案 §3 的来源表里，本批接**两种**：工资到账、主人还在考虑中的建议。
选它们是因为**两者都有确定的发生时刻**——策略判「是不是新事件」靠的正是
`occurred_at > last_considered_at`，没有确定时刻的来源在这里没法诚实地回答。
其余来源（世界事件、天气、性格兴趣）**不是不重要，是本批没接**；接的时候照这个形状加即可。

## 远端调用在事务外，写在事务里

提案要花一次模型调用，所以**先在事务外问，再开一个写事务把"考虑过"与心愿一起落下**。
两件事同一事务：崩在中间只会丢掉这次调用，不会留下「有心愿但冷却没起算」——
那种残留会让下一轮再问一次。

**`propose` 默认不接 ＝ 不形成心愿，也不记「考虑过」。** 不接就什么都不发生，
而不是记一笔空的把冷却推后。真接上模型提案器的那一刻**还要补两样**：额度预占／结算，
以及**发前持久意图**（进程被杀时不重复外发）——A 的 TRV-03 已有这套形状，照它接，别另造。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from ..utils import iso, parse_dt
from ..web_journey.service import PlanChoice
from ..web_platform.lease import LeaseLost
from ..web_platform.uow import unit_of_work
from .wish_policy import WishAction, WishDecision, WishFacts, WishPolicy, WishState, WishStatus, WishTrigger, evaluate

# 已经收尾的两种：给页面看，但对"还能不能再想一个"来说等于没有心愿（见 `_state_of`）。
# **`linked` 不在其中**——那一个正关联着真实旅程。
SETTLED = frozenset({WishStatus.COMPLETED.value, WishStatus.CANCELLED.value})

logger = logging.getLogger("petsoul.web.wish")

# 两种触发源都取**最近一条**：更早的那些，上一次考虑时就已经看见了。
# 并列排序键加上主键，是为了同一时刻的两条也有确定顺序（同样的库每次读出来一样）。
WAGE_SQL = ("SELECT tx_id AS ref, created_at FROM economy_transactions WHERE pet_id = ? AND type = 'web_job_income' "
            "ORDER BY created_at DESC, tx_id DESC LIMIT 1")
SUGGESTION_SQL = ("SELECT suggestion_id AS ref, created_at FROM web_owner_suggestions WHERE pet_id = ? AND status = 'pending' "
                  "ORDER BY created_at DESC, suggestion_id DESC LIMIT 1")


@dataclass(frozen=True, slots=True)
class WishProposal:
    """大脑给的一次提案。**返回 None 表示 TA 决定留在家里**——那也是一次考虑，冷却照样起算。"""

    candidates: list[dict]  # 每项要有 destination_key / name / city，1–3 个（A 的 `_validate`）
    selected: int  # **候选里的下标**，不是目的地键
    owner_reason: str  # 给主人的一句理由，1–200 字
    funds_goal: int  # 游戏金币目标
    interest_tags: tuple[str, ...] = ()  # 短 snake_case 码，受 A 的白名单约束


def latest_trigger(conn, pet_id: str, now: datetime) -> WishTrigger | None:
    """这只宠物眼下最近的一次有效触发。没有就是 None——那时这一轮由冷却说了算。"""
    found: list[tuple[datetime, str, str]] = []
    for kind, sql in (("wage_settled", WAGE_SQL), ("owner_suggestion", SUGGESTION_SQL)):
        row = conn.execute(sql, (pet_id,)).fetchone()
        if row is not None:
            found.append((parse_dt(row["created_at"]), f"{kind}:{row['ref']}", kind))
    if not found:
        return None
    at, event_id, kind = max(found)
    return WishTrigger(event_id=event_id, kind=kind, occurred_at=at)


def _state_of(view) -> WishState | None:
    """A 的读视图 → 策略要的那几项。`waiting_reasons` 是**两侧的并集**，策略自己拆。

    **已收尾／已取消的要当成"没有心愿"。** A 的 `read_in` 有意在没有进行中心愿时返回**最近一条**
    （已关联／已完成／已取消）——那是给页面说清楚现状用的。原样交给策略的话，
    `_hard_skip` 会判 `wish_closed` 并永远跳过：**TA 取消一次之后就再也形成不了新心愿**。
    这不是策略错：方案 §9 的"已关闭心愿不自动复活"说的是别把旧的救活，不是别再想新的。

    `linked` **保留**：那是已经关联到真实旅程的那一个，确实不该动它（旅途中另有 `active_journey` 一道）。
    """
    if view is not None and view.status in SETTLED:
        return None
    if view is None or view.funds_goal is None:
        return None  # 没有资金目标就谈不上"够不够"，当作还没有可推进的心愿
    return WishState(wish_id=view.wish_id, revision=view.wish_revision, status=view.status,
                     destination_key=view.destination_key, title=view.destination_name,
                     funds_goal=view.funds_goal, waiting=tuple(view.waiting_reasons))


def bind_wish_round(*, wishes, projector, economy, journeys, storage,
                    policy: WishPolicy | None = None, propose: Callable[..., WishProposal | None] | None = None,
                    trigger_of: Callable[..., WishTrigger | None] = latest_trigger) -> Callable[..., WishDecision]:
    """造一次「心愿轮」。返回 `run(user_id, pet_id, now, *, activated) -> WishDecision`。

    挂在现有的生活评估节奏上（I 2026-09-24 确认，不新建调度器）。**大部分轮次会被冷却挡在
    `cooling_down`——那是设计意图，不是接错了。**

    **`activated` 是按调用传进来的事实，不是一个谓词，也没有默认值。** 两个原因：

    - 我第一版收的是 `activated_of(pet_id)`，而组合根里能给的只有
      `any(p == pet_id for _, p in agent.activated_pets())`——`activated_pets()` **每次调用查一次库**，
      于是**每轮 N 次 SQL**，比同类 job（driving tick 一次 SQL 遍历结果）多一个数量级（I 核出）。
      而 `bind_wish_tick` 本来就在遍历已入住的宠物，**它知道答案，不需要再去问**。
    - 不给默认值是因为 `True` 会 fail-open：`NOT_ACTIVATED` 那道闸对待领养居民就失效了。
      **没有默认值，调用方就必须想一下这只宠物到底入没入住。**
    """
    policy = policy or WishPolicy()

    def facts_of(conn, pet_id: str, now: datetime, activated: bool) -> WishFacts:
        view = wishes.read_in(conn, pet_id)
        state = _state_of(view)
        last = (view.last_considered_at if view is not None else None) or wishes.last_considered_in(conn, pet_id)
        blocking = journeys.active_commitment_in(conn, pet_id, now) if journeys.active_commitment_in else None
        return WishFacts(pet_id=pet_id, activated=activated, maintenance=projector.runtime.paused(pet_id, conn=conn),
                         balance=economy.wallet(pet_id).balance,
                         active_journey=journeys.repo.active_for_pet(pet_id) is not None,
                         commitments=(blocking,) if blocking else (), quota_available=_has_quota(pet_id),
                         wish=state, trigger=trigger_of(conn, pet_id, now),
                         last_considered_at=parse_dt(last) if isinstance(last, str) else last)

    def _has_quota(pet_id: str) -> bool:
        """读不到账本**不算有额度**（fail-closed，与心跳同口径）：读取失败不等于可以再花一次。"""
        try:
            left, _ = projector.budget_facts(pet_id)
        except Exception:  # noqa: BLE001 - 账本读不到时按"没有额度"处理，由心跳那条链去报依赖不可用
            return False
        return left is None or left > 0

    def _think(user_id: str, pet_id: str, decision: WishDecision, trigger: WishTrigger | None, now: datetime) -> None:
        # 远端调用在事务**外**；"考虑过"与心愿在同一个写事务里落下（见模块开头）
        proposal = propose(user_id, pet_id, trigger, now)
        key = trigger.event_id if trigger is not None else f"reconsider:{now.date().isoformat()}"
        with unit_of_work(storage) as conn:
            wishes.considered_in(conn, pet_id, iso(decision.considered_at))
            if proposal is not None:
                wishes.propose_in(conn, pet_id=pet_id, user_id=user_id, trigger_event_id=key,
                                  candidates=proposal.candidates, selected=proposal.selected,
                                  interest_tags=proposal.interest_tags, owner_reason=proposal.owner_reason,
                                  funds_goal=proposal.funds_goal, now=now)

    def run(user_id: str, pet_id: str, now: datetime, *, activated: bool) -> WishDecision:
        with storage.connect() as conn:
            facts = facts_of(conn, pet_id, now, activated)
        decision = evaluate(facts, policy, now)
        if decision.action == WishAction.UPDATE_WAITING.value:
            wishes.update_waiting(facts.wish.wish_id, decision.expected_revision, decision.life_waiting,
                                  iso(decision.reconsider_after) if decision.reconsider_after else None,
                                  # **按动作取值**：策略给了 `considered_at` 才算考虑过，不由这里自己判
                                  iso(decision.considered_at) if decision.considered_at else None,
                                  current_coins=decision.funds.current_coins if decision.funds else None, now=now)
        elif decision.action == WishAction.ASK_BRAIN.value and propose is not None:
            _think(user_id, pet_id, decision, facts.trigger, now)
        return decision

    return run


@dataclass(frozen=True, slots=True)
class PlanPick:
    """事务外读到的一份就绪计划。**只用来选目的地，不用来保证能去。**

    读到它的那一刻起，到 `depart` 拿到写锁为止，A 随时可能重查、心愿可能被取消、资料可能过期——
    所以 `choice` 原样交给 `depart`，由它在写事务里用同一个 `conn` 重核一遍（C 的口径）。
    """

    destination_key: str
    choice: PlanChoice  # 编号与版本并成一个值：**漏传版本这件事写不出来**（C 按我提的原则做的更强版）


def bind_ready_plan(wishes, storage) -> Callable[[str], PlanPick | None]:
    """`ready_plan_of(pet_id)`：此刻有没有一份就绪计划、指向哪儿。没有就是 None。

    **在事务外读**是故意的——它的用途只是"让 TA 这一轮更可能选这个目的地"。
    出发那一刻的正确性不靠这次读，靠 `depart` 在写事务里重核。
    """
    def ready_plan_of(pet_id: str) -> PlanPick | None:
        if wishes.ready_plan_in is None:
            return None
        with storage.connect() as conn:
            plan = wishes.ready_plan_in(conn, pet_id)
        return None if plan is None else PlanPick(plan.destination_key, PlanChoice(plan.plan_id, plan.plan_revision))

    return ready_plan_of


def bind_wish_tick(round_of: Callable[[str, str, datetime], WishDecision],
                   activated_pets: Callable[[], list[tuple[str, str]]]) -> Callable[[datetime], int]:
    """一轮扫一遍已入住的宠物。挂在世界线现有的节奏上，**不新建调度器**（I 2026-09-24 确认）。

    异常口径与 `LifeEngine.run` 一字不差，故意的：
    - `LeaseLost` **原样抛出去**——租约被接手时 `WorldTicker._run_jobs` 要立刻停住整轮，
      吞掉它就等于旧任期继续写；
    - 其余单只宠物出错只记日志、不拖累别的宠物。

    返回这一轮真正动作过的只数（`skip` 不算），给日志和运维看。
    """
    def tick(now: datetime) -> int:
        acted = 0
        for user_id, pet_id in activated_pets():
            try:
                if round_of(user_id, pet_id, now, activated=True).action != WishAction.SKIP.value:
                    acted += 1
            except LeaseLost:
                raise
            except Exception:  # noqa: BLE001 - 单只宠物出错不影响其他宠物
                logger.exception("wish round failed pet=%s", pet_id)
        return acted

    return tick
