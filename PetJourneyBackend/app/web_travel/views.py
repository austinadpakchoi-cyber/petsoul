"""旅行计划的只读视图（TRV-03；给 I 的 `/travel/plans` 路由，合同 §8、§23.2、§25.2）。

**只有这一处知道计划、事实、手账这几张表长什么样**：路由拿视图、不读表，表结构一变只改这里（与合同 §0.1「一份实现」同源）。
  - 按宠物取：计划不是这只宠物的，就当不存在（None）——越权读挡在这一层，不指望路由记得；
  - 不给版本号时取心愿当前那一版；给了就取那一版，没有那一版就 None；还没发布过计划的心愿也是 None；
  - **不含**平台 API 费（在回执里，合同 §8 不下发玩家端）、研究 operation 号、给主人的理由；
  - 手账图的状态走 `TravelJournalService.image_in`（以插画记录为准，processing／ready／failed／unknown 互不折叠），不是表里的列。
事实的值、手账版式按 JSON 解出：dataclass 冻结的是字段，里面的 dict 按只读约定用。纯读，不写库。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable

from . import store
from .model import PHASE_MEMORY, PHASE_PLAN


@dataclass(frozen=True, slots=True)
class SourceView:
    source_id: str
    url: str | None
    publisher: str | None
    retrieved_at: str | None
    published_at: str | None


@dataclass(frozen=True, slots=True)
class StopView:
    name: str
    role: str  # main／suggested
    why: str
    tip: str
    fact_ids: tuple[str, ...]
    verified: bool
    lat: float | None  # TRV-04 适配器落库前已换成 WGS-84，这里原样给
    lng: float | None
    visited_event_ids: tuple[str, ...]  # 计划页恒为空：真实到访只盖在回忆页


@dataclass(frozen=True, slots=True)
class TipView:
    text: str
    fact_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FactView:
    fact_id: str
    category: str
    subject: str
    value: Any  # 价格类形如 {"amount", "currency", "estimated"}；认不出的价格是 None
    source_ids: tuple[str, ...]
    retrieved_at: str | None
    published_at: str | None
    observed_at: str | None
    valid_from: str | None
    valid_until: str | None
    verification: str
    conclusion: str | None
    verdict: str  # verified／unverified／stale／conflicting／rejected
    blocks_departure: bool


@dataclass(frozen=True, slots=True)
class JournalView:
    journal_id: str
    journal_revision: int
    plan_revision: int
    phase: str  # plan／memory
    identity_mode: str  # photo／none
    event_ids: tuple[str, ...]
    layout: dict  # 版式：站点（station_id 只在这一版内有效）、提醒、来源、文字区、image_refused
    image: Any  # journal.JournalImage(status, url, ticket)
    created_at: str  # 这一页自己的时间：回忆页建得比计划页晚，不能拿计划的时间顶替
    updated_at: str
    identity_note: str | None
    template_revision: str  # TRV-07 的版式号（如 t1）


@dataclass(frozen=True, slots=True)
class PlanRevisionView:
    plan_id: str
    plan_revision: int
    wish_id: str
    wish_revision_at_build: int
    destination_key: str
    title: str
    summary: str
    stops: tuple[StopView, ...]
    tips: tuple[TipView, ...]
    rain_alternative: str | None
    preconditions: tuple[str, ...]
    sources: tuple[SourceView, ...]
    valid_from: str | None
    valid_until: str | None
    journey_id: str | None
    created_at: str
    facts: tuple[FactView, ...]
    journals: tuple[JournalView, ...]  # 这一版的计划页、回忆页（各取最新一次修订）


@dataclass(frozen=True, slots=True)
class PlanView:
    plan_id: str
    wish_id: str
    current_revision: int
    revisions: tuple[int, ...]
    revision: PlanRevisionView  # 选中的那一版（默认当前那一版）


def plan_view_in(conn: sqlite3.Connection, pet_id: str, plan_id: str, plan_revision: int | None = None, *,
                 image_in: Callable[[sqlite3.Connection, str | None], Any]) -> PlanView | None:
    wish = conn.execute("SELECT wish_id, pet_id, plan_revision FROM web_travel_wishes WHERE plan_id = ?", (plan_id,)).fetchone()
    if wish is None or wish["pet_id"] != pet_id or wish["plan_revision"] is None:
        return None
    current = int(wish["plan_revision"])
    plan = store.plan_in(conn, plan_id, current if plan_revision is None else int(plan_revision))
    if plan is None:  # 计划行的 pet_id 总是来自心愿行：上面那一道就够，不再重复（重复的那道永远走不到，还会遮住上一道的变异）
        return None
    revisions = tuple(int(r[0]) for r in conn.execute("SELECT plan_revision FROM web_travel_plans WHERE plan_id = ? ORDER BY plan_revision",
                                                     (plan_id,)))
    return PlanView(plan_id=plan_id, wish_id=wish["wish_id"], current_revision=current, revisions=revisions,
                    revision=_revision(conn, plan, image_in))


def _revision(conn: sqlite3.Connection, plan: sqlite3.Row, image_in) -> PlanRevisionView:
    facts = store.facts_for_operation_in(conn, plan["operation_id"]) if plan["operation_id"] else []
    rows = conn.execute("SELECT * FROM web_travel_journals WHERE plan_id = ? AND plan_revision = ? ORDER BY journal_revision",
                        (plan["plan_id"], plan["plan_revision"])).fetchall()
    latest = {row["phase"]: row for row in rows}  # 每个阶段取最新一次修订
    return PlanRevisionView(
        plan_id=plan["plan_id"], plan_revision=int(plan["plan_revision"]), wish_id=plan["wish_id"],
        wish_revision_at_build=int(plan["wish_revision_at_build"]), destination_key=plan["destination_key"],
        title=plan["title"], summary=plan["summary"],
        stops=tuple(StopView(name=s["name"], role=s["role"], why=s["why"], tip=s["tip"], fact_ids=tuple(s["fact_ids"]), verified=bool(s["verified"]),
                             lat=s["lat"], lng=s["lng"], visited_event_ids=tuple(s["visited_event_ids"])) for s in json.loads(plan["stops_json"])),
        tips=tuple(TipView(text=t["text"], fact_ids=tuple(t["fact_ids"])) for t in json.loads(plan["owner_tips_json"])),
        rain_alternative=plan["rain_alternative"], preconditions=tuple(json.loads(plan["preconditions_json"])),
        sources=tuple(SourceView(source_id=s["source_id"], url=s["url"], publisher=s["publisher"], retrieved_at=s["retrieved_at"],
                                 published_at=s["published_at"]) for s in json.loads(plan["sources_json"])),
        valid_from=plan["valid_from"], valid_until=plan["valid_until"], journey_id=plan["journey_id"], created_at=plan["created_at"],
        facts=tuple(_fact(row) for row in facts),
        journals=tuple(_journal(conn, latest[phase], image_in) for phase in (PHASE_PLAN, PHASE_MEMORY) if phase in latest))


def _fact(row: sqlite3.Row) -> FactView:
    return FactView(fact_id=row["fact_id"], category=row["category"], subject=row["subject"], value=json.loads(row["value_json"]),
                    source_ids=tuple(json.loads(row["source_ids_json"])), retrieved_at=row["retrieved_at"], published_at=row["published_at"],
                    observed_at=row["observed_at"], valid_from=row["valid_from"], valid_until=row["valid_until"],
                    verification=row["verification"], conclusion=row["conclusion"], verdict=row["verdict"],
                    blocks_departure=bool(row["blocks_departure"]))


def _journal(conn: sqlite3.Connection, row: sqlite3.Row, image_in) -> JournalView:
    return JournalView(journal_id=row["journal_id"], journal_revision=int(row["journal_revision"]), plan_revision=int(row["plan_revision"]),
                       phase=row["phase"], identity_mode=row["identity_mode"], event_ids=tuple(json.loads(row["event_ids_json"])),
                       layout=json.loads(row["layout_json"]), image=image_in(conn, row["image_task_id"]),
                       created_at=row["created_at"], updated_at=row["updated_at"], identity_note=row["identity_note"],
                       template_revision=row["template_revision"])
