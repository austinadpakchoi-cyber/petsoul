"""装配自主决策与付费调用的额度预占（集成侧）。

把决策包（C）、操作级额度预占（A）与每宠运行投影（I）接到一起，并在认知线里放一步“需要想一想的宠物才走一次决策”。
默认 PETJOURNEY_WEB_BRAIN_MODE=off：一次模型都不调用，世界照旧按规则生活。
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone

from ..schemas.runtime_internal import HeartbeatAction
from ..utils import utcnow
from ..web_platform.budget import BudgetLedger, BudgetLimit
from ..web_platform.lease import LeaseLost
from ..web_runtime.heartbeat_policy import HeartbeatPolicy, evaluate, retry_plan
from .brain_life import BrainLife
from .decision import Brain, ChatModelAdapter, ServiceContextReader
from ..web_runtime.clock_policy import ClockHealthStatus
from .runtime_view import WorldClock

logger = logging.getLogger("petsoul.web.brain")


def wire_brain(web, agent, storage, providers, settings) -> None:
    """打开后每次决策先预占额度（每宠每个 UTC 记账日上限，且不超过供应商本身的上限）；
    模型不可用或预算不足就退回规则并标 rule_fallback。生图调用同样先预占。"""
    projector = agent.projector
    # timezone_of / activity_of：决策上下文与心跳共用同一个时间与活动来源。不传的话 TA 在外地时当地钟点会偏成家里的（C 的 CR-C5、CR-C6）
    reader = ServiceContextReader(web, versions_of=projector.versions, now=utcnow,
                                  timezone_of=lambda pet_id, now: projector.state(pet_id, now).timezone,
                                  activity_of=lambda pet_id, now: projector.state(pet_id, now).primary_activity)
    brain = Brain(reader=reader, model=ChatModelAdapter(providers.chat), clock=WorldClock())
    life = BrainLife(brain=brain, journeys=web.journeys, households=web.households, residents=web.residents, homes=web.homes,
                     projector=projector, mode=getattr(settings, "web_brain_mode", "off"))
    ledger = BudgetLedger(storage)
    per_pet = int(getattr(settings, "web_brain_daily_per_pet", 12))
    provider_cap = (providers.meter.caps.get("llm") if providers.meter is not None else None) or per_pet * 20

    def reserve(operation_id: str, purpose: str, pet_id: str):
        return ledger.reserve(operation_id, provider="llm", purpose=purpose, subject_scope=f"pet:{pet_id}", units=1,
                              limits=[BudgetLimit(f"pet:{pet_id}:{purpose}", per_pet), BudgetLimit(f"provider:llm:{purpose}", provider_cap)])

    def budget_facts(pet_id: str) -> tuple[int | None, datetime | None]:
        """这只宠物本记账日还能发起几次生活规划，以及窗口什么时候重置。心跳据此把"额度用完"如实说成 EXHAUSTED。

        **两层都要看**：宠物自己的日额度，和这个供应商的全局日上限。供应商那层满了，宠物额度再多也发不出去——
        只看宠物层的话，心跳会一直说"可以想"，每一轮都去预占一次、被拒一次（包 B 的 BLOCK-2）。
        两层都按"已用 ＋ 在途"算：在途是已经预占、还没结算的调用，钱可能已经花出去了。取更紧的那一层。
        读不到账本时**照原样抛出去**，由投影层如实说成"依赖不可用"；读取失败不等于有额度。
        """
        now = utcnow()
        resets_at = datetime.combine(now.date() + timedelta(days=1), time(0, 0), tzinfo=timezone.utc)

        def left(scope_key: str, cap: int) -> int:
            used = ledger.usage(scope_key)
            return max(0, cap - int(used.get("used", 0)) - int(used.get("inflight", 0)))

        return min(left(f"pet:{pet_id}:life_plan", per_pet), left("provider:llm:life_plan", provider_cap)), resets_at

    projector.budget_facts = budget_facts
    life.reserve = reserve
    life.settle = lambda reservation, outcome: ledger.settle(reservation, outcome)
    life.model_consent = projector.model_enabled
    web.brain_life = life
    agent.cognition.jobs.append(("brain_life", _round(agent, projector, life)))

    # 生图也在发出调用前预占（方案 §11：所有远端付费调用先原子预占）。
    # **两层都要占**，和生活规划那边一个道理：
    #   - `provider:image:daily` 是**全局**上限，沿用生图供应商本身的每日上限，不新增限制；
    #   - `pet:<id>:illustration` 是**每宠**上限。只有全局一层时，一只宠物（或一位主人反复点"重画"）
    #     就能把当天全局额度吃光，别人一张都画不成——默认 20 个单位、没有参考照时一次占 2 个，
    #     整个部署一天也就约 10 张。按宠物分开之后，谁画多了先停谁。
    # 任一层不够就整体不占（账本的多作用域预占本来就是原子的，跨进程有效，不需要新机制）。
    # 配置为 0 表示该层不限；两层都为 0 时 `limits` 为空，那是"没配上限"的显式选择，不是默认。
    # 全局上限取**配置**，不依赖计量表是否接上：没接计量表时 caps 是空的，
    # 那会让全局这层整个消失（改之前就是这样，配了 web_image_daily_cap 也不生效）。
    # 计量表接上了就以它为准（供应商自己的上限更硬），没接就用配置值。
    image_cap = ((providers.meter.caps.get("image") if providers.meter is not None else None)
                 or int(getattr(settings, "web_image_daily_cap", 0) or 0))
    per_pet_image_cap = int(getattr(settings, "web_image_per_pet_daily_cap", 0) or 0)

    def reserve_image(operation_id: str, pet_id: str, units: int):
        limits = [BudgetLimit("provider:image:daily", image_cap)] if image_cap else []
        if per_pet_image_cap:
            limits.append(BudgetLimit(f"pet:{pet_id}:illustration", per_pet_image_cap))
        return ledger.reserve(operation_id, provider="image", purpose="illustration", subject_scope=f"pet:{pet_id}", units=units, limits=limits)

    web.illustrations.reserve = reserve_image
    web.illustrations.settle = lambda reservation, outcome, actual_units=None: ledger.settle(reservation, outcome, actual_units=actual_units)


def _round(agent, projector, life):
    """认知线的一步：只对心跳说“需要想一想”的宠物走一次有限决策；mode=off 时整步跳过。

    **按游标轮转**：一轮最多想 limit 只，下一轮从上次停下的那只之后接着排。
    固定顺序（sorted）在宠物数超过上限时会让排在后面的永远轮不到——和世界线的到期扫描是同一个道理。
    """

    cursor = {"after": ""}  # 上一轮停在谁之后（进程内即可：换进程重新从头排也不会饿死谁）


    def brain_round(now: datetime, limit: int = 5) -> int:
        if life.mode == "off":
            return 0
        done = 0
        # 时钟健康（CR-B7）：每轮采一次样，与世界线共用投影上那一份监视器（进程级事实）。
        # 认知线是会花钱的那条线，时钟不对（尤其大幅前跳）会让"该不该现在想"整个判错。
        health = projector.clock_monitor.sample(projector.clock).health
        if health.status is not ClockHealthStatus.OK:
            logger.warning("brain round clock unhealthy: %s skew=%ss", health.status.value, health.skew_seconds)
        pets = sorted({pet for _, pet in agent.activated_pets()} | {pet for _, pet in agent.living_pets()})
        start = next((i for i, pet in enumerate(pets) if pet > cursor["after"]), 0) if pets else 0
        for pet_id in pets[start:] + pets[:start]:
            if done >= limit:
                break
            cursor["after"] = pet_id
            try:
                state, facts = projector.snapshot(pet_id, now)  # 一次算完：别把同一只宠物评估两遍（CR-B6）
                decision = evaluate(state, (), HeartbeatPolicy(), now, facts=facts, clock_health=health)
                if decision.action is not HeartbeatAction.REQUEST_BRAIN:
                    continue
            except LeaseLost:  # 租约已被接手：整轮停住，交给新任期，不写退避也不动后面的宠物
                raise
            except Exception:  # noqa: BLE001 - 评估这只宠物就出错：还没可能调模型，不占名额，但要退避免得每轮重来
                logger.exception("brain evaluate failed pet=%s", pet_id[:8])
                _stall(projector, life, pet_id, now, "evaluate_failed")
                continue
            done += 1  # **先占名额再可能调模型**：否则"模型返回后提交出错"这条路径会让一轮的真实调用次数不受 limit 约束
            try:
                outcome = life.consider(pet_id, now)
            except LeaseLost:
                # 模型可能已经答完了：调用记录留在账本与决策编号里，本进程到此为止，绝不再写退避或关闭编号。
                # 往下排的宠物也不再处理——世界现在归新任期推进。
                logger.warning("brain round stopped: lease lost at pet=%s", pet_id[:8])
                raise
            except Exception:  # noqa: BLE001 - 一只宠物想不成不影响别的宠物，也不影响世界线
                logger.exception("brain round failed pet=%s", pet_id[:8])
                _stall(projector, life, pet_id, now, "round_failed")
                continue
            logger.info("brain round pet=%s status=%s by=%s choice=%s", pet_id[:8], outcome.status, outcome.composed_by, outcome.destination_key)
        return done

    return brain_round


def _stall(projector, life, pet_id: str, now: datetime, reason: str) -> None:
    """这一轮对这只宠物出了异常：也要写一次退避，免得每轮抛同样的错、每轮再调一次模型（包 B 的 BLOCK-3）。

    **只处理普通失败**。租约失效走不到这里（调用方先 raise），万一写退避时才发现，也原样抛出。
    只写退避，不碰这一轮的决策编号——出了异常并不代表那次调用没发出去。
    """
    if life.mode == "off":
        return
    try:
        plan = retry_plan(now, HeartbeatPolicy(), dependency=True)
        projector.runtime.record_backoff(pet_id, now, review_at=plan.check_at, reason=f"brain:{reason}")
        # **不清决策编号**：这里只知道“出了异常”，不知道那一次调用发出去没有。
        # 清掉就等于下一轮换个新编号把可能已经计费的调用再发一遍（CR-Q14）。
        # 编号要等这次操作结清了才清（BrainLife._resolved），不按时间轮换。
    except LeaseLost:  # 退避本身也是写世界：租约没了就不写，交给新任期
        raise
    except Exception:  # noqa: BLE001 - 连退避都写不下就只记日志，别让整轮塌掉
        logger.exception("brain stall not recorded pet=%s", pet_id[:8])
