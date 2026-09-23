"""每宠运行投影与心跳 shadow（集成侧）。

- RuntimeStore：web_entity_runtime 的读写，已拆到 runtime_store.py；这里再导出，原导入路径不变。
- RuntimeProjector：把真实库里的事实只读投影成 web_runtime 要的 RuntimeState 与 HeartbeatFacts。
  时区严格取实际所在地（家 / 驿站 / 交通段 / 店里），取不到就是 None——心跳会给出明确的不可用结果，不套用香港或上海。
- HeartbeatShadow：世界线里“只记录不执行”地跑一遍心跳策略，与现有规则生活对照，把结论写进运行记录。
  shadow 不出门、不发消息、不调模型、不花钱；接管真实调度要等对照稳定后由集成窗口按批次切换。
"""

from __future__ import annotations

import logging
from collections import Counter
from hashlib import sha256
from dataclasses import dataclass
from datetime import datetime, timedelta
from time import monotonic
from typing import Callable

from ..schemas.runtime_internal import ActivityRef, RuntimeState, Versions
from ..schemas.web.pets import PetPresence
from ..utils import iso, parse_dt, utcnow
from ..web_platform.lease import LeaseLost
from ..web_platform.runtime_epochs import EPOCHS
from ..web_runtime.clock_policy import ClockHealthStatus, ClockMonitor, ensure_utc, local_wall, resolve_zone
from ..web_runtime.heartbeat_policy import HeartbeatPolicy, evaluate
from ..web_runtime.state import (AutonomyFacts, BrainAvailability, CognitionFacts, DueItem, DueKind, HeartbeatFacts,
                                 cognition_status, commitment_deadline)
from .runtime_store import RuntimeStore  # noqa: F401 - 再导出：历史调用方仍 from .runtime_view import RuntimeStore

logger = logging.getLogger("petsoul.web.runtime")
_UNSET = object()  # facts(timezone=...) 的"没传"标记：None 是有效取值（时区取不到）
BUDGET_RECHECK = timedelta(minutes=5)  # 额度读不出来时隔多久再看一次（依赖故障的复查间隔，不是许可）
EXAM_STALE = timedelta(hours=1)  # 与 web_driving.sessions.PREPARING_TTL 一致：开了这么久还没动的考局按放弃处理


def reply_ref(pet_id: str, user_id: str) -> str:
    """回复承诺的稳定引用。**不含家人编号**——同一位家人每次算出同一个化名，去重与对账都不受影响。

    留言本身是谁写的，运行层不需要知道；需要的话在集成层按 user_id 重新算一次化名来对上。
    """
    return f"reply:{pet_id}:{sha256(user_id.encode('utf-8')).hexdigest()[:12]}"


@dataclass(frozen=True, slots=True)
class ShadowResult:
    """一轮 shadow 的汇总：每种心跳结论各多少只宠物，以及与规则生活结论不同的条数。"""

    evaluated: int
    actions: dict[str, int]
    unavailable: int
    stale: int = 0  # 算完才发现世界已经变了、结论作废的条数（旧评估不得确认它没读到的新版本）


class WorldClock:
    """项目统一时间入口的 Clock 实现：now_utc 走 app.utils.utcnow（测试里被假时钟替换），monotonic 只用于进程内超时。"""

    def now_utc(self) -> datetime:
        return utcnow()

    def monotonic(self) -> float:
        return monotonic()


class RuntimeProjector:
    """只读投影：所有依赖都是现成服务的读取方法，装配时注入。不推进世界、不写库。"""

    def __init__(self, *, storage, journeys, households, residents, homes, home_places, dna, communicator, profile_of, realm: str) -> None:
        self.storage = storage
        self.journeys = journeys
        self.households = households
        self.residents = residents
        self.homes = homes
        self.home_places = home_places
        self.dna = dna
        self.communicator = communicator
        self.profile_of = profile_of
        self.realm = realm
        self.runtime = RuntimeStore(storage)
        # 这只宠物能不能用模型做生活规划（家庭“模型回信”开关）；装配时注入
        self.model_enabled: Callable[[str], bool] = lambda pet_id: False
        self.model_available: Callable[[], bool] = lambda: False
        # (本记账窗口还剩几次, 窗口重置时刻)；装配时接到额度账本。None 表示没接，按"可用、次数未知"处理
        self.budget_facts: Callable[[str], tuple[int | None, datetime | None]] | None = None
        self.decide_window: Callable[[str], tuple] = lambda pet_id: (None, None)
        # 时钟健康（CR-B7）：**每个进程一份**，两条线共用。它测的是"墙上时钟与单调时钟对不对得上"，
        # 本来就是进程级的事实，不是某条线的。放在这里运维核对校时之后也够得着 `clock_monitor.reanchor(clock)`。
        self.clock = WorldClock()
        self.clock_monitor = ClockMonitor()

    def versions(self, pet_id: str, row: dict | None = None) -> Versions:
        row = self.runtime.row(pet_id) if row is None else row
        saved = self.dna.saved(pet_id)
        journey = self.journeys.repo.active_for_pet(pet_id)
        return Versions(runtime_epoch=int(row.get("runtime_epoch") or 0), activity_epoch=int(row.get("activity_epoch") or 0),
                        dna_version=int(getattr(saved, "version", 0) or 0), privacy_epoch=int(row.get("privacy_epoch") or 0),
                        membership_epoch=int(row.get("membership_epoch") or 0),
                        itinerary_version=journey.itinerary_version if journey else None)

    def _base_place(self, pet_id: str):
        """TA 的生活基地：家或驿站。没有就是 None（还没入住的宠物）。"""
        residence = self.residents.residence_of(pet_id) if self.residents is not None else None  # 驿站编号（还没被领养的居民）
        if residence is not None:
            return self.home_places.get(residence), f"residence:{residence}"
        home = self.homes.by_pet(pet_id)
        return (self.home_places.get(home.home_id), f"home:{home.home_id}") if home is not None else (None, None)

    def _where(self, pet_id: str, now: datetime) -> tuple[ActivityRef | None, str | None, str | None, str | None]:
        """(主活动, 时区, 片区, 场景引用)。

        时区按 TA 此刻实际所在地取：店里的地点资料 → 这段交通的起点 → 生活基地（家或驿站）。
        一个都取不到（还没入住）就给 None，由心跳给出明确的不可用结果，不套用香港或上海。
        """
        presence, journey, visit = self.journeys.peek(pet_id, now)
        scheduled = self.journeys.repo.active_for_pet(pet_id) if journey is None else None  # 已经定好、还没到出门时间的行程
        base, scene = self._base_place(pet_id)
        base_zone = base.timezone if base is not None else None
        if journey is not None and visit is not None and presence is PetPresence.visiting:
            kind = "work" if str(journey.destination_key).startswith("work:") else "visit"
            place = visit.place or {}
            return (ActivityRef(kind, f"visit:{visit.visit_id}", visit.starts_at, visit.ends_at, False), place.get("timezone") or base_zone,
                    journey.city, f"visit:{visit.visit_id}")
        if journey is not None and presence in (PetPresence.in_transit, PetPresence.returning):
            leg = next((l for l in self.journeys.repo.legs(journey.journey_id) if l.starts_at <= now < l.ends_at), None)
            origin = (leg.origin if leg else {}) or {}
            return (ActivityRef("travel", f"leg:{leg.leg_id}" if leg else f"journey:{journey.journey_id}",
                                leg.starts_at if leg else journey.departed_at, leg.ends_at if leg else journey.completes_at, False),
                    origin.get("timezone") or base_zone, journey.city, f"leg:{leg.leg_id}" if leg else f"journey:{journey.journey_id}")
        place, timezone = base, base_zone
        exam = self._open_exam(pet_id, now)
        if exam is not None:  # 正在考正式考局：不可打断（打断就等于替 TA 交白卷）
            return (ActivityRef("exam", f"exam:{exam['session_id']}", exam["started_at"], None, False),
                    timezone, getattr(place, "area_key", None) if place is not None else None, scene)
        if place is None:
            return ActivityRef("at_home", scene), None, None, scene
        if scheduled is not None and now < scheduled.departed_at:
            # 行程已定、还没到出门时间：在家收拾，不可打断（打断就赶不上已核验的班次）；下次检查落在出门时刻
            return (ActivityRef("at_home", f"journey:{scheduled.journey_id}", None, scheduled.departed_at, False), timezone,
                    getattr(place, "area_key", None), scene)
        return ActivityRef("at_home", scene), timezone, getattr(place, "area_key", None), scene

    def snapshot(self, pet_id: str, now: datetime | None = None) -> tuple[RuntimeState, HeartbeatFacts]:
        """一次把状态和事实都算出来，`_where` 只查一次。

        调度每轮每只宠物本来要算两遍（state 一遍、facts 一遍），CR-B6 点名的"被评估两次"就是这个。
        """
        now = now or utcnow()
        where = self._where(pet_id, now)
        row = self.runtime.row(pet_id)  # CR-B8 第②项：运行记录**只读这一次**，state/facts/versions 用的是同一份快照
        facts = self.facts(pet_id, now, timezone=where[1], row=row)
        return self.state(pet_id, now, facts=facts, where=where, row=row), facts

    def state(self, pet_id: str, now: datetime | None = None, *, facts: HeartbeatFacts | None = None, where=None,
              row: dict | None = None) -> RuntimeState:
        now = now or utcnow()
        home = self.homes.by_pet(pet_id)
        activated = home is not None and home.activated_at is not None and self.homes.join_step(pet_id, home).value == "moved_in"
        resident = self.residents is not None and self.residents.residence_of(pet_id) is not None  # 驿站居民照常调度
        activity, timezone, region, scene = where if where is not None else self._where(pet_id, now)
        if not activated and not resident:
            activity = ActivityRef("not_activated", None)
        profile = self.profile_of(pet_id) if self.profile_of is not None else None
        row = self.runtime.row(pet_id) if row is None else row
        # 时区传下去：出门次数要按当地自然日算；运行记录那一份也传下去，别再读第二次
        facts = facts if facts is not None else self.facts(pet_id, now, timezone=timezone, row=row)
        return RuntimeState(pet_id=pet_id, realm_id=self.realm, versions=self.versions(pet_id, row), as_of=now,
                            household_id=self.households.household_of_pet(pet_id) if self.households is not None else None,
                            timezone=timezone, region_id=region, scene_ref=scene, primary_activity=activity,
                            sleep_window=(profile.sleep_start, profile.wake) if profile is not None else None,
                            next_check_at=parse_dt(row["next_check_at"]) if row.get("next_check_at") else None,
                            silence_reason=row.get("silence_reason"),
                            # CR-B5：这两个字段是共享类型的一部分，恒为空会让 /ops/runtime 与
                            # `facts_from_state`（最小模式）看不到"有承诺待兑现 / 大脑不可用"。
                            # 用 B 自己的推导函数填，保证和心跳看到的是同一份事实。
                            pending_commitment_deadline=commitment_deadline(facts),
                            cognition_status=cognition_status(facts, now))

    def facts(self, pet_id: str, now: datetime | None = None, *, timezone: str | None = _UNSET,
              row: dict | None = None) -> HeartbeatFacts:
        """timezone：TA 此刻所在地的 IANA 时区名。不传就自己查一次（出门次数要按当地自然日算，见 _outings_today）。

        row：运行记录那一行。调用方已经读过就传进来——同一次评估里读三次可能读到三个时刻的快照（CR-B8 第②项）。
        """
        now = now or utcnow()
        timezone = self._where(pet_id, now)[1] if timezone is _UNSET else timezone
        row = self.runtime.row(pet_id) if row is None else row
        profile = self.profile_of(pet_id) if self.profile_of is not None else None
        enabled = bool(self.model_enabled(pet_id)) and bool(self.model_available())
        cognition = self._cognition(pet_id, enabled, now)
        window = self.decide_window(pet_id)
        autonomy = AutonomyFacts(**({"active_window": window} if window and all(window) else {}), outings_today=self._outings_today(pet_id, now, timezone),
                                 outings_per_day=getattr(profile, "outings_per_day", 2),
                                 next_review_at=parse_dt(row["next_review_at"]) if row.get("next_review_at") else None,
                                 last_decision_at=parse_dt(row["last_decision_at"]) if row.get("last_decision_at") else None,
                                 latest_suggestion_at=self._latest_suggestion(pet_id, now))
        return HeartbeatFacts(due_items=self._due_items(pet_id, now), cognition=cognition, autonomy=autonomy,
                              last_evaluated_at=parse_dt(row["last_evaluated_at"]) if row.get("last_evaluated_at") else None,
                              maintenance=bool(row.get("maintenance")))

    def _cognition(self, pet_id: str, enabled: bool, now: datetime) -> CognitionFacts:
        """大脑此刻可不可用。额度用完要如实说成 EXHAUSTED 并带上记账窗口的重置时刻——

        否则心跳会一直给出 REQUEST_BRAIN，每一轮都再去预占一次、被拒一次（包 B 的 BLOCK-2）。
        额度一旦被调高，下一次复查读到的 remaining_today 就变了，自然回到 REQUEST_BRAIN，不需要清任何标记。
        """
        if not enabled:
            return CognitionFacts(enabled=False, availability=BrainAvailability.DISABLED)
        if self.budget_facts is None:
            return CognitionFacts(enabled=True, availability=BrainAvailability.AVAILABLE)
        try:
            remaining, resets_at = self.budget_facts(pet_id)
        except Exception:  # noqa: BLE001 - 读不到额度不该让这只宠物整个评估失败……
            # ……但**读不到不等于有额度**。如实说成依赖不可用（安静原因是"依赖故障"而不是"正常安静"），
            # 隔一会儿再看；这只是复查，不是许可，真要调用时仍然要原子预占一次（包 B 的 BLOCK-2）。
            logger.exception("budget facts unavailable pet=%s", pet_id[:8])
            return CognitionFacts(enabled=True, availability=BrainAvailability.UNAVAILABLE, retry_after=now + BUDGET_RECHECK)
        if remaining is not None and remaining <= 0:
            return CognitionFacts(enabled=True, availability=BrainAvailability.EXHAUSTED, retry_after=resets_at,
                                  remaining_today=0, window_resets_at=resets_at)
        return CognitionFacts(enabled=True, availability=BrainAvailability.AVAILABLE, remaining_today=remaining, window_resets_at=resets_at)

    def _open_exam(self, pet_id: str, now: datetime) -> dict | None:
        """TA 正在考的那一局正式考试（`web_school_sessions`）。练习局不算——那是随时可以停的。

        心跳的 `ONGOING` 本来就认 `exam`，只是投影一直没给，于是考试期间 TA 被当成在家空闲，
        家人的建议和新的生活决定都可能把考试打断（CR-B8 第①项）。

        **只认还活着的局**：`preparing` 超过 `PREPARING_TTL` 就是被放弃的残局，
        拿它当"正在考试"会让这只宠物永远停在考试里、再也排不上调度——那比不投影更糟。
        """
        alive = iso(now - EXAM_STALE)
        with self.storage.connect() as conn:
            row = conn.execute(
                "SELECT session_id, begun_at, created_at FROM web_school_sessions "
                "WHERE pet_id = ? AND mode = 'formal' AND state IN ('preparing', 'running') AND last_active_at >= ? "
                "ORDER BY created_at DESC LIMIT 1", (pet_id, alive)).fetchone()
        if row is None:
            return None
        started = row["begun_at"] or row["created_at"]
        return {"session_id": row["session_id"], "started_at": parse_dt(started) if started else None}

    def _due_items(self, pet_id: str, now: datetime) -> tuple[DueItem, ...]:
        items: list[DueItem] = []
        due = self.journeys.due_summary(pet_id, now)
        if due is not None:
            items.append(DueItem(ref=due["ref"], kind=DueKind.JOURNEY, due_at=due["due_at"], commitment=due["commitment"],
                                 itinerary_version=due["itinerary_version"]))
        for pending in self.communicator.pending_summary(pet_id, now):
            # **引用里不放家人编号**：它会经心跳的意图（dedupe_key）与 /ops/runtime 输出出去（CR-B8 第③项）。
            # 换成按家人编号算出的稳定化名：同一位家人永远是同一个化名，能去重、能对上，但看不出是谁。
            items.append(DueItem(ref=reply_ref(pet_id, pending["user_id"]), kind=DueKind.REPLY, due_at=pending["due_at"],
                                 commitment=True, input_high_watermark=pending["inputs"]))
        return tuple(items)

    def _outings_today(self, pet_id: str, now: datetime, timezone: str | None = None) -> int:
        """今天出门过几次。**按 TA 所在地的自然日算**，和规则生活（`life.LifeEngine.consider`）是同一个口径。

        两处口径不一致会在跨午夜时打架：按最近 24 小时算的心跳说"今天够了、不再规划"，
        按当地当天 0 点算的规则生活却还允许出门（CR-B4）。
        取不到时区时退回最近 24 小时——那是偏保守的一侧（算得多、更早说够了），
        宁可少出门，也不要两处给出相反的结论。
        """
        zone = resolve_zone(timezone)
        since = (local_wall(now, zone).replace(hour=0, minute=0, second=0, microsecond=0) if zone is not None
                 else ensure_utc(now, "now") - timedelta(hours=24))
        with self.storage.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM web_journeys WHERE pet_id = ? AND departed_at >= ?",
                               (pet_id, iso(ensure_utc(since, "since")))).fetchone()
        return int(row["n"])

    def _latest_suggestion(self, pet_id: str, now: datetime) -> datetime | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT MAX(created_at) AS t FROM web_owner_suggestions WHERE pet_id = ? AND status = 'pending' AND created_at >= ?",
                               (pet_id, iso(now - timedelta(hours=24)))).fetchone()
        return parse_dt(row["t"]) if row and row["t"] else None


class HeartbeatShadow:
    """只记录不执行：每轮给每只宠物评估一次心跳，写下结论，和现有规则生活对照。"""

    def __init__(self, projector: RuntimeProjector, pets_of: Callable[[], list[str]], policy: HeartbeatPolicy | None = None,
                 due_of: Callable[[datetime, str], list[tuple[str, str]]] | None = None) -> None:
        self.projector = projector
        self.pets_of = pets_of
        self.policy = policy or HeartbeatPolicy()
        # 按到期取宠物（CR-B6）。接上之后这一轮只看"该看的"，而不是每 30 秒把所有宠物重算一遍。
        # 没接就退回全量扫描——行为与接线前完全一致。
        self.due_of = due_of
        self.after = ""  # 轮转游标：下一轮从这只之后接着排（新旧候选共用同一个上限与这条轮转）

        self.last: ShadowResult | None = None

    def _pets(self, now: datetime) -> list[str]:
        """这一轮看哪些宠物：接了按到期取就只看该看的，否则全量扫描（行为与接线前一致）。

        取完把游标停在最后一只身上，下一轮从它之后接着排——一轮看不完也不会让后面的宠物永远轮不到。
        """
        if self.due_of is None:
            return list(self.pets_of())
        picked = self.due_of(now, self.after)
        if picked:
            self.after = picked[-1][0]
        return [pet_id for pet_id, _why in picked]

    def run(self, now: datetime | None = None) -> ShadowResult:
        now = now or utcnow()
        actions: Counter = Counter()
        unavailable = stale = 0
        # 每轮采一次样，本轮所有宠物用同一个读数。只比墙上时钟与单调时钟的差，
        # 所以**回拨和大幅前跳都发现得了**——只看 last_evaluated_at 只能发现回拨。
        health = self.projector.clock_monitor.sample(self.projector.clock).health
        if health.status is not ClockHealthStatus.OK:
            logger.warning("heartbeat shadow clock unhealthy: %s skew=%ss", health.status.value, health.skew_seconds)
        for pet_id in self._pets(now):
            try:
                state, facts = self.projector.snapshot(pet_id, now)
                decision = evaluate(state, (), self.policy, now, facts=facts, clock_health=health)
            except LeaseLost:  # 租约被接手：本轮到此为止，剩下的宠物交给新任期，不再往运行记录里写
                raise
            except Exception:  # noqa: BLE001 - shadow 不能影响世界线：记下来，继续下一只
                logger.exception("heartbeat shadow failed pet=%s", pet_id[:8])
                unavailable += 1
                continue
            # 算的时候读的是 state.versions；写之前在同一个事务里再比一次。
            # 中途被别的命令改了（撤权、改 DNA、换成员、活动变化）就整个作废——
            # 否则这次用旧事实算出的 next_check_at 会把那条新变化的唤醒信号一起抹掉。
            moved = self.projector.runtime.record_evaluation(pet_id, decision, now, expected=state.versions)
            if moved:
                logger.info("heartbeat shadow discarded a stale evaluation pet=%s moved=%s", pet_id[:8], ",".join(moved))
                stale += 1
                continue
            actions[decision.action.value] += 1
        self.last = ShadowResult(evaluated=sum(actions.values()), actions=dict(actions), unavailable=unavailable, stale=stale)
        logger.info("heartbeat shadow: %s", self.last)
        return self.last
