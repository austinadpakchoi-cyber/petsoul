"""按 DNA 与真实机会做一次自主决定（集成侧）：规则给可行机会 → 预算预占 → 决策包提案 → 复核后变成真实计划。

模式（配置 PETJOURNEY_WEB_BRAIN_MODE）：
  - off（默认）：完全不跑，一次模型都不会调用；世界仍由现有规则生活推进。
  - shadow：调用一次决策，只记录“模型会选什么、规则会选什么”，不出门、不发消息。仍然是付费调用，所以要显式打开。
  - live：提案经复核后真的出发（或明确留在家里）。

复核（提案交出之后、执行之前，按最新数据再看一遍）：这位家人是不是还是有效成员、语义版本有没有变、机会有没有过期、
TA 是不是已经在外面、钱够不够。任何一条不成立就不执行，并如实记原因；模型不可用或预算不足时退回规则生活并标 rule_fallback。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from ..schemas.runtime_internal import AudienceScope, BudgetDenied, BudgetReservation
from ..utils import utcnow
from ..web_platform.lease import LeaseLost
from ..web_runtime.heartbeat_policy import HeartbeatPolicy, next_review_at, retry_plan
from ..web_journey.local import job_of
from .life import settle_suggestions
from .decision import Brain, CallLimits, DecisionRequest, destination_key_of, offers_from_options, reason_of

logger = logging.getLogger("petsoul.web.brain")
DEADLINE = timedelta(seconds=90)  # 一次决策从登记到交出的截止（世界运行方案 v0.2 §11 首轮建议）
# 这次没想成之后什么时候再看：用包 B 的 retry_plan，不另造一套常量。
# not_before 是"最早允许再发起可能付费的尝试"（额度账本给的硬性恢复时刻原样保留），check_at 是"下一次只读复查"。
# 不退避的后果是真金白银：任务进程 30 秒一轮，一只想不成的宠物会每 30 秒再调一次模型。
DEPENDENCY_CODES = frozenset({"provider_error", "timeout", "deadline_passed"})
# 租约失效不是“这次没想成”：本进程已经不是世界的推进者，必须立刻停手，让 ticker 结束这一轮。
# 不写退避（那会替新任期决定什么时候再想）、不清决策编号、不写生活决定；
# **已经发出的模型调用记录照常保留**——额度账本不走租约围栏，预占与结算仍然落库，
# 决策编号也留在 web_entity_runtime 里，合法执行者复用同一个编号即可恢复并对账（A 的重放保护据此生效）。
# 编号什么时候换：**只看这次操作有没有结清，不看过了多久**（见 _resolved 与 RuntimeStore.open_decision）。
RESOLVED = frozenset({"succeeded", "failed", "not_sent"})  # 有明确结局的结算结果；**unknown 不在内**：结果未明不算结清


def _resolved(permit, settled: str | None) -> bool:
    """这一次操作有没有一个**明确的结局**。只有明确了才能清掉逻辑编号，下一轮才算真正的新一次决策。

    没结清就清掉编号，等于下一轮换个新编号，把**可能已经发出、可能已经计费**的那次调用再发一遍
    （CR-Q14 / Q-C13：认知线 30 秒一轮，每两轮就会重发一次，并且每次再多占一个每宠每日额度）。
    - 同编号仍在途（`in_flight`）：这恰恰说明同一次操作还没结束，绝不能清；
    - 预占到期（`expired`）：只说明没人来结清，**不等于那次请求没发出去**，同样不算明确结局；
    - `unknown`：有一次可能已被受理，也不算。
    **有明确结局就放行**，不只是"没发出"那一种：
    - `succeeded` / `failed`（这次调用正常收场，包括模型明确报错）：这是常态——一次决策做完了，
      下一次本来就是**真正的新一次决策**，照常换新编号、照常允许再调用；
    - `not_sent` / `released`（确定没离开本机）：这一次什么都没发出，重试可以接着走。
    剩下的 `unknown` / `expired` 才是"说不清发没发出"，只有它们会把编号留住；要解开得由账本那边查实后再结算一次。
    换句话说：**时间经过、预占过期都不能单独成为换编号重发的依据**，但"正常做完一次决策"始终可以开启下一次。
    """
    if permit is None:
        return True  # 没接额度账本：没有“在途”这个概念
    if isinstance(permit, BudgetDenied):
        return permit.reason != "in_flight"  # 其余拒绝（额度满、账本不可用）都是“根本没占上”，什么都没发出
    if settled is not None:
        return settled in RESOLVED
    return permit.status in ("settled", "released")


@dataclass(frozen=True, slots=True)
class BrainOutcome:
    """一次自主决定的结果：谁决定的（model / rule_fallback）、选了什么、有没有真的执行。"""

    pet_id: str
    mode: str
    status: str  # proposed / departed / stayed / rejected / failed / skipped
    composed_by: str | None = None
    destination_key: str | None = None
    intent: str | None = None
    reason: str | None = None
    operation_id: str | None = None


class BrainLife:
    def __init__(self, *, brain: Brain, journeys, households, residents, homes, projector, mode: str = "off") -> None:
        self.brain = brain
        self.journeys = journeys
        self.households = households
        self.residents = residents
        self.homes = homes
        self.projector = projector
        self.mode = mode
        # A 的操作级额度预占（装配时注入）：返回 BudgetReservation 或 BudgetDenied；没有接入时为 None（当作不限额，但仍受供应商上限约束）
        self.reserve: Callable[[str, str, str], BudgetReservation | BudgetDenied | None] | None = None
        self.settle: Callable[[BudgetReservation, str], None] | None = None
        # 家庭是否同意把共用资料交给模型（沿用“模型回信”开关）
        self.model_consent: Callable[[str], bool] = lambda pet_id: False

    def consider(self, pet_id: str, now: datetime | None = None) -> BrainOutcome:
        now = now or utcnow()
        if self.mode == "off":
            return BrainOutcome(pet_id, self.mode, "skipped", reason="brain_off")
        actor = self._actor(pet_id)
        if actor is None:
            return BrainOutcome(pet_id, self.mode, "skipped", reason="no_actor")
        user_id, audience = actor
        if self.journeys.repo.active_for_pet(pet_id) is not None:
            return BrainOutcome(pet_id, self.mode, "skipped", reason="already_traveling")
        home = self.homes.by_pet(pet_id)
        if home is None:
            return BrainOutcome(pet_id, self.mode, "skipped", reason="no_home")
        versions = self.projector.versions(pet_id)
        offers = offers_from_options(self.journeys.destinations(user_id, pet_id, home.home_id, now), pet_id=pet_id, as_of=now, expected_versions=versions,
                                     income_of=lambda key: job_of(key).pay if job_of(key) else 0)
        if not offers:
            return self._back_off(pet_id, now, BrainOutcome(pet_id, self.mode, "skipped", reason="no_offers"))
        # 这一轮决策的逻辑编号：首次创建后存进运行记录，重试、重启、跨分钟恢复都复用同一个（验收 CR-A2）
        operation_id = self.projector.runtime.open_decision(
            pet_id, now, new_id=lambda: f"life:{pet_id}:{now:%Y%m%d%H%M%S}:{uuid.uuid4().hex[:6]}")
        permit = self.reserve(operation_id, "life_plan", pet_id) if self.reserve is not None else None
        request = DecisionRequest(operation_id=operation_id, pet_id=pet_id, purpose="life_plan", audience=audience, as_of=now,
                                  deadline_at=now + DEADLINE, offers=offers, expected_versions=versions,
                                  model_consent=bool(self.model_consent(pet_id)))
        denied_until = permit.retry_after if isinstance(permit, BudgetDenied) else None  # 额度账本给的硬性恢复时刻
        result = self.brain.propose(request, permit, CallLimits())
        settled = None
        # **只结算这一次真的占上的那笔**。`reserve` 有时会把同编号上一次的记录原样交回来
        # （已结清 / 结果未明 / 到期未结清）——那笔不是这一轮的调用，拿这一轮的“我没发出去”
        # 去结算它，会把一笔**可能已经计费**的调用退回来（账本的 not_sent ＝ 查实没发出）。
        if isinstance(permit, BudgetReservation) and permit.status == "reserved" and self.settle is not None:
            settled = result.settle_outcome()
            self.settle(permit, settled)
        resolved = _resolved(permit, settled)
        failure = result.failure
        if failure is not None:
            logger.info("brain life failed pet=%s code=%s reason=%s", pet_id[:8], failure.code.value, reason_of(failure))
            return self._back_off(pet_id, now, BrainOutcome(pet_id, self.mode, "failed", reason=failure.code.value, operation_id=operation_id),
                                  retry_after=denied_until, resolved=resolved)
        proposal = result.proposal
        assert proposal is not None
        chosen = next((offer for offer in offers if offer.offer_id == proposal.selected_offer_id), None)
        destination = destination_key_of(chosen) if chosen is not None else None
        if self.mode == "shadow":
            # 只记"这一轮想过了、什么时候再看"，**不写 last_decision_at / last_decision_by**：
            # 世界并没有按这个结论走，写成生活决定就是冒充，而且会让心跳每 30 秒再调一次模型（包 B 的 BLOCK-1）。
            logger.info("brain shadow pet=%s by=%s choice=%s", pet_id[:8], proposal.composed_by, destination or "continue")
            plan = retry_plan(now, HeartbeatPolicy())
            self.projector.runtime.record_attempt(pet_id, now, review_at=plan.check_at, reason="brain:shadow")
            if resolved:
                self._close(pet_id, now, operation_id)
            return BrainOutcome(pet_id, self.mode, "proposed", proposal.composed_by, destination, proposal.intent_summary, operation_id=operation_id)
        return self._commit(pet_id, user_id, home, proposal, chosen, destination, versions, operation_id, request.deadline_at,
                            resolved=resolved)

    def _back_off(self, pet_id: str, now: datetime, outcome: BrainOutcome, *, retry_after: datetime | None = None,
                  resolved: bool = True) -> BrainOutcome:
        """没想成就记下什么时候再看：模式是 shadow/live 时才记（off 根本没跑）。心跳据此安静等待，不会每轮重来。

        retry_after：额度账本或供应商给的**硬性恢复时刻**（例如额度要等到下一个 UTC 记账日）。
        交给 `retry_plan` 算，不再固定 15 分钟——否则"要等 20 小时"会被当成"15 分钟后可以再调一次"（包 B 的 BLOCK-2）。
        """
        if self.mode == "off":
            return outcome
        reason = (outcome.reason or "unknown").split(":")[0]
        plan = retry_plan(now, HeartbeatPolicy(), dependency=reason in DEPENDENCY_CODES, retry_after=retry_after)
        try:
            self.projector.runtime.record_backoff(pet_id, now, review_at=plan.check_at, reason=f"brain:{reason}")
            if resolved:  # 没结清就把编号留着：下一轮必须沿用同一个，不能换个新编号重发（CR-Q14）
                self._close(pet_id, now, outcome.operation_id)
        except LeaseLost:  # 写退避时才发现租约没了：这条退避不属于本进程，原样抛出，本轮结束
            raise
        except Exception:  # noqa: BLE001 - 记不下退避不该让这只宠物的这一轮整个失败
            logger.exception("brain backoff not recorded pet=%s", pet_id[:8])
        return outcome

    def _commit(self, pet_id, user_id, home, proposal, chosen, destination, versions, operation_id, deadline_at,
                *, resolved: bool = True) -> BrainOutcome:
        """执行前按**此刻**再看一遍：没超过截止期限、家庭还同意用模型、版本没变、机会没过期、TA 还在家。

        判断一律用 `utcnow()` 而不是发起决策时的那个时间——中间隔着一次真实的模型调用，
        几十秒到几分钟都可能，拿旧时间判等于没判。留在家里也是一个明确结果。
        """
        at = utcnow()
        if at > deadline_at:
            return self._back_off(pet_id, at, BrainOutcome(pet_id, self.mode, "rejected", proposal.composed_by, destination,
                                                           reason="deadline_exceeded", operation_id=operation_id), resolved=resolved)
        if proposal.composed_by == "model" and not self.model_consent(pet_id):
            # 想的时候家里同意把资料交给模型，交出提案之前撤回了：这份提案不能再用
            return self._back_off(pet_id, at, BrainOutcome(pet_id, self.mode, "rejected", proposal.composed_by, destination,
                                                           reason="consent_withdrawn", operation_id=operation_id), resolved=resolved)
        stale = versions.stale_fields(self.projector.versions(pet_id))
        if stale:
            return self._back_off(pet_id, at, BrainOutcome(pet_id, self.mode, "rejected", proposal.composed_by, destination,
                                                           reason=f"versions_changed:{','.join(stale)}", operation_id=operation_id), resolved=resolved)
        if chosen is None or proposal.continue_current:
            review_at = next_review_at(at, HeartbeatPolicy(), proposal.suggested_review_after_seconds)
            stale_now = self.projector.runtime.record_decision_checked(pet_id, at, by=proposal.composed_by, next_review_at=review_at, expected=versions)
            if stale_now:  # 写"留在家里"之前的最后一刻又变了（例如刚被撤权）：这次不算数
                return self._back_off(pet_id, at, BrainOutcome(pet_id, self.mode, "rejected", proposal.composed_by, None,
                                                               reason=f"versions_changed:{','.join(stale_now)}", operation_id=operation_id), resolved=resolved)
            if resolved:
                self._close(pet_id, at, operation_id)
            return BrainOutcome(pet_id, self.mode, "stayed", proposal.composed_by, None, proposal.intent_summary, operation_id=operation_id)
        if at >= chosen.valid_until:
            return self._back_off(pet_id, at, BrainOutcome(pet_id, self.mode, "rejected", proposal.composed_by, destination,
                                                           reason="offer_expired", operation_id=operation_id), resolved=resolved)
        try:
            journey = self.journeys.depart(user_id, pet_id, home.home_id, destination, at, operation_key=operation_id,
                                           expected_versions=versions, valid_until=chosen.valid_until)
        except LeaseLost:  # 租约在模型返回之后被接手：出发事务已整体回滚，这里不能再把它记成“这次没想成”
            raise
        except Exception as exc:  # noqa: BLE001 - 规则拒绝（钱不够、已在外面、睡着、现实资料不可用）都是明确结果，不是崩溃
            return self._back_off(pet_id, at, BrainOutcome(pet_id, self.mode, "rejected", proposal.composed_by, destination,
                                                           reason=getattr(exc, "reason", type(exc).__name__), operation_id=operation_id), resolved=resolved)
        settle_suggestions(self.journeys.storage, pet_id, destination, at)  # 建议状态按真实语义记（CR-C4）
        self.projector.runtime.record_decision(pet_id, at, by=proposal.composed_by,
                                               next_review_at=next_review_at(at, HeartbeatPolicy(), proposal.suggested_review_after_seconds))
        if resolved:
            self._close(pet_id, at, operation_id)
        logger.info("brain life departed pet=%s journey=%s by=%s", pet_id[:8], journey.journey_id, proposal.composed_by)
        return BrainOutcome(pet_id, self.mode, "departed", proposal.composed_by, destination, proposal.intent_summary, operation_id=operation_id)

    def _close(self, pet_id: str, now: datetime, operation_id: str | None) -> None:
        """这一轮**有了明确结果**才清掉逻辑编号，下一轮才是新的一次决策。

        只清自己这一轮的那个编号：对不上就不动（别的轮次开的编号不归这里管）。
        """
        if operation_id is None:
            return
        try:
            self.projector.runtime.close_decision(pet_id, now, operation_id=operation_id)
        except LeaseLost:  # 编号要留给合法执行者复用（同一编号＝同一次调用，账本据此不重复扣费）
            raise
        except Exception:  # noqa: BLE001 - 清不掉编号最多让下一轮复用它，不该让这次的结果作废
            logger.exception("brain decision not closed pet=%s", pet_id[:8])

    def _actor(self, pet_id: str) -> tuple[str, AudienceScope] | None:
        """以谁的名义决定：家庭宠物用第一位管理员（受众＝这个家），驿站居民用系统账号（受众＝公开）。"""
        household_id = self.households.household_of_pet(pet_id) if self.households is not None else None
        if household_id:
            admin = self.households.primary_admin(household_id)
            return (admin, AudienceScope("household", household_id=household_id)) if admin else None
        residence = self.residents.residence_of(pet_id) if self.residents is not None else None
        if residence is None:
            return None
        record = self.journeys.repo.latest_for_pet(pet_id)
        return (record.user_id if record else None, AudienceScope("public")) if record else None
