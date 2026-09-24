"""旅行手账（TRV-03；方案 §6、§12；P 的画面简报 TRV-05）。一份计划一页手账：**准确文字由程序排版，画面由 GPT 画**。

  - 计划的一版发布时（研究发布的**同一事务**里）编译 P 的 `compile_journal_brief`：**被拒就不发**，手账照样有文字、没有图；
  - 画面版本 `visual_digest` 与这份计划已有的手账相同 → **复用那张图，不再付费**（改站名、时间、提醒不重画；回忆页也复用）；
  - 需要新图时经**现有插画链路**登记（`style="travel_journal"`），任务与手账修订同生共死；提示词是 P 编好的，站名、数字不在里面；
  - 身份参考只认主人原照／档案真照（P 的编译器把关）；没有就出无肖像版，**不补画证件照来凑**（方案 §11.2、§12）；
  - 手账图状态**以插画记录为准**（按 `image_task_id`），`unknown` 独立于 `failed`、不自动重试；显式重画走插画服务现有的四态与版本凭据；
  - **回忆页**（T10）：旅程结束（`returned_home`）时按计划出一页回忆，**只给真实发生的到访事件盖章**（事件号 `<旅程>:<事件键>`）；
    顺路建议永远不盖章，没去成就没有章；画面与计划页相同 → 复用背景。关联着这趟旅程的心愿随之 `completed`。

模板号与纸笔照 r7k 的 TRV-07（`TRV-07-layout-spec-r7k.md`）：版式 `t1`，首批默认 `cream` 米白旧纸＋`watercolor` 淡水彩；
`kraft/grid`、`pencil/ink` 是以后可选的封闭变体，首批不并行生产多套。换模板号或纸笔会让画面摘要变化、需要新图。
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from ..utils import iso, parse_dt
from ..web_photo_director.contracts import PhotoDirectorError
from ..web_photo_director.journal_brief import (
    BRIEF_STYLE_VERSION, JournalBriefInput, JournalEvent, JournalFact, JournalIdentity, JournalStation, compile_journal_brief,
)
from ..web_platform.tasks import redraw_ticket
from ..web_platform.uow import unit_of_work
from . import store, views
from .model import PHASE_MEMORY, PHASE_PLAN

STYLE = "travel_journal"
TEMPLATE_REVISION = "t1"  # TRV-07 基础版式 t1
PAPER, BRUSH, MOOD = "cream", "watercolor", "calm"  # TRV-07 首批默认纸笔
VISUAL = re.compile(r"[一-鿿，、]{2,24}\Z")  # 能画的特征：纯中文短语、不带数字（与 P 的 FEATURE 同口径）
VISUAL_CATEGORIES = ("feature", "landmark")
VERIFICATION = {"verified": "verified", "unverified": "unverified", "stale": "stale", "conflicting": "conflicting", "rejected": "unverified"}
MAIN_STATION = "st-0"  # 计划里恒有且只有一个主目的地，排在第一站
# 站点编号 `st-<下标>` **只在一版计划（一页手账）之内有效**：按 stops 的下标生成，计划改版后同一个编号可能指另一个地点。
# 盖章在出回忆页那一刻、按关联的那一版计划算，不跨版本；跨版本对应地点用站名＋role，**不要拿 st-N 当键**（I 核出）


@dataclass(frozen=True, slots=True)
class JournalImage:
    """手账图的读法（合同 11.5）：没有图用 None；processing／ready／failed／unknown 四个取值互不折叠。"""

    status: str | None
    url: str | None
    ticket: str | None  # 能重画时给出重画凭据（failed／unknown），其余为 None


class TravelJournalService:
    def __init__(self, storage, illustrations=None) -> None:
        self.storage = storage
        self.illustrations = illustrations  # web_journey.illustrations.IllustrationService；没有就只出文字手账
        # 装配注入：这只宠物现在的身份参考（物种、参考照版本与指纹、来源、外貌标签）；没有照片就 None
        self.identity_of: Callable[[sqlite3.Connection, str], JournalIdentity | None] = lambda conn, pet_id: None
        self.mood_of: Callable[[str], str] = lambda pet_id: MOOD
        # 装配注入：这趟旅程**真实**的到访（开始过的才算）；没有就 None。回忆页只按它盖章
        self.visit_of: Callable[[str], object | None] = lambda journey_id: None
        # 装配注入：旅程结束时把关联的心愿落定为 completed（service.TravelWishService.complete_in）
        self.complete_wish_in: Callable[..., object] = lambda conn, journey_id, now=None: None
        self.template_revision = TEMPLATE_REVISION

    # ---- 计划发布时（研究发布的同一事务）----
    def plan_published_in(self, conn: sqlite3.Connection, wish: sqlite3.Row, plan, now: datetime) -> dict:
        return self._page_in(conn, wish, plan, PHASE_PLAN, (), now)

    # ---- 回忆页（世界事件 sink）----
    def on_world_event(self, event) -> None:
        if event.kind != "returned_home":
            return
        journey_id = event.journey.journey_id
        visit = self.visit_of(journey_id)
        started = visit is not None and getattr(visit, "starts_at", None) is not None and visit.starts_at <= event.occurred_at
        events = (JournalEvent(f"{journey_id}:visit_started", MAIN_STATION),) if started else ()
        with unit_of_work(self.storage) as conn:
            plan = store.plan_for_journey_in(conn, journey_id)
            if plan is None:
                return  # 没有预研计划的老旅程：不出回忆页（兼容路径保留）
            self.complete_wish_in(conn, journey_id, event.occurred_at)
            if conn.execute("SELECT 1 FROM web_travel_journals WHERE plan_id = ? AND plan_revision = ? AND phase = ?",
                            (plan["plan_id"], plan["plan_revision"], PHASE_MEMORY)).fetchone() is not None:
                return  # 事件重放：同一个结果
            wish = store.wish_in(conn, plan["wish_id"])
            self._page_in(conn, wish, plan, PHASE_MEMORY, events, event.occurred_at)

    # ---- 出一页（计划页与回忆页同一条路）----
    def _page_in(self, conn: sqlite3.Connection, wish, plan, phase: str, events: tuple, now: datetime) -> dict:
        facts = store.facts_for_operation_in(conn, plan["operation_id"]) if plan["operation_id"] else []
        stops = json.loads(plan["stops_json"])
        brief, refused = self._compile(conn, wish, plan, stops, facts, now, phase, events)
        journal_id = f"tj-{plan['plan_id']}-{phase}"
        revision = int(conn.execute("SELECT COALESCE(MAX(journal_revision), 0) + 1 FROM web_travel_journals WHERE journal_id = ?",
                                    (journal_id,)).fetchone()[0])
        digest = brief.visual_digest if brief else f"none:{refused}"
        task_id = self._image_for_in(conn, wish, plan, brief) if brief else None
        stamped = {event.station_id: [event.event_id] for event in events}
        # stations[*].station_id 只在这一版计划内有效（见 MAIN_STATION 处）
        layout = {"phase": phase, "plan_id": plan["plan_id"], "plan_revision": int(plan["plan_revision"]), "title": plan["title"],
                  "summary": plan["summary"], "tips": json.loads(plan["owner_tips_json"]), "rain_alternative": plan["rain_alternative"],
                  "stations": [{**{k: s.get(k) for k in ("name", "role", "lat", "lng", "fact_ids")}, "station_id": f"st-{i}",
                                "visited_event_ids": stamped.get(f"st-{i}", [])} for i, s in enumerate(stops)],
                  "sources": json.loads(plan["sources_json"]), "text_zones": list(brief.text_zones) if brief else [],
                  "image_refused": refused}
        layout_json = json.dumps(layout, ensure_ascii=False, sort_keys=True, default=str)
        row = {"journal_id": journal_id, "journal_revision": revision, "plan_id": plan["plan_id"], "plan_revision": int(plan["plan_revision"]),
               "visual_digest": digest, "phase": phase, "event_ids_json": json.dumps([e.event_id for e in events]),
               "template_revision": self.template_revision, "brief_version": BRIEF_STYLE_VERSION,
               "identity_mode": brief.identity_mode if brief else "none", "identity_note": brief.identity_note if brief else None,
               "reference_revision": brief.references[0][1] if brief and brief.references else None, "image_task_id": task_id,
               "layout_json": layout_json, "digest": hashlib.sha256(layout_json.encode()).hexdigest(), "created_at": iso(now), "updated_at": iso(now)}
        columns = ", ".join(row)
        conn.execute(f"INSERT INTO web_travel_journals ({columns}) VALUES ({', '.join('?' for _ in row)})", tuple(row.values()))
        return row

    def _compile(self, conn, wish, plan, stops, facts, now, phase, events):
        """返回 (简报, None) 或 (None, P 的原因码)。**被拒就不发**。

        交给 P 的事实编号换成**按内容的稳定编号**：P 的画面摘要里含 fact_id，而库里的 fact_id 按研究轮次（每轮的抓取、观测时间
        各自独立）——不换的话，重新研究得到一模一样的画面特征也会变成新画面、再付一次费（方案 §12：与画面无关的变化不重画）。"""
        alias, visual = {}, {}
        for f in facts:
            value = json.loads(f["value_json"])
            if f["category"] not in VISUAL_CATEGORIES or not isinstance(value, str) or not VISUAL.fullmatch(value):
                continue
            stable = "vf-" + hashlib.sha256(json.dumps([f["category"], f["subject"], value], ensure_ascii=False).encode()).hexdigest()[:20]
            alias[f["fact_id"]] = stable
            if stable not in visual or f["verdict"] == "verified":  # 同内容去重，已核验的那条优先
                visual[stable] = JournalFact(stable, value, VERIFICATION[f["verdict"]], f["verdict"] == "verified",  # 没登记的结论当场报错
                                             tuple(json.loads(f["source_ids_json"])), _dt(f["valid_until"]), (f["subject"],))
        stations = tuple(JournalStation(f"st-{i}", s["role"], s["name"], tuple(dict.fromkeys(alias.get(x, x) for x in s.get("fact_ids") or ())))
                         for i, s in enumerate(stops))
        known = frozenset(s["source_id"] for s in json.loads(plan["sources_json"]))
        illustrator = getattr(self.illustrations, "illustrator", None)
        capabilities = frozenset({"reference_images"}) if illustrator is not None else frozenset()
        try:
            brief = compile_journal_brief(JournalBriefInput(
                phase=phase, plan_id=plan["plan_id"], plan_revision=int(plan["plan_revision"]), template_revision=self.template_revision,
                paper=PAPER, brush=BRUSH, mood=self.mood_of(wish["pet_id"]), stations=stations, facts=tuple(visual.values()),
                known_source_ids=known, now=now, identity=self.identity_of(conn, wish["pet_id"]), events=events,
                capabilities=capabilities, allow_portrait_free=True))
        except PhotoDirectorError as exc:
            return None, str(exc) or type(exc).__name__
        return brief, None

    def _image_for_in(self, conn: sqlite3.Connection, wish, plan, brief) -> str | None:
        """同一份计划、同一画面版本、同一模板已经有图（或在画）→ 复用那个任务；否则登记新图。"""
        reused = conn.execute("SELECT image_task_id FROM web_travel_journals WHERE plan_id = ? AND visual_digest = ? AND template_revision = ? "
                              "AND image_task_id IS NOT NULL ORDER BY journal_revision DESC LIMIT 1",
                              (plan["plan_id"], brief.visual_digest, self.template_revision)).fetchone()
        if reused is not None:
            return reused["image_task_id"]
        if self.illustrations is None:
            return None
        reference = brief.references[0] if brief.references else None
        return self.illustrations.request_image_in(
            conn, wish["user_id"], wish["pet_id"], f"{STYLE}:{plan['plan_id']}:{brief.visual_digest[:16]}:{self.template_revision}",
            style=STYLE, brief_prompt=brief.prompt, brief_size=brief.size, identity_mode=brief.identity_mode,
            reference_revision=reference[1] if reference else None, reference_sha256=reference[2] if reference else None)

    # ---- 纯读 ----
    def latest_in(self, conn: sqlite3.Connection, plan_id: str) -> sqlite3.Row | None:
        return conn.execute("SELECT * FROM web_travel_journals WHERE plan_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1", (plan_id,)).fetchone()

    def plan_view_in(self, conn: sqlite3.Connection, pet_id: str, plan_id: str, plan_revision: int | None = None) -> views.PlanView | None:
        """GET `/travel/plans/{plan_id}` 用的只读视图（表长什么样只有 views.py 知道）。计划不是这只宠物的、还没发布、没有那一版 → None。"""
        return views.plan_view_in(conn, pet_id, plan_id, plan_revision, image_in=self.image_in)

    def image_in(self, conn: sqlite3.Connection, task_id: str | None) -> JournalImage:
        """手账图状态以插画记录为准：processing／ready／failed，failed 再用插画服务的 `outcome_of` 分出 unknown。"""
        if not task_id:
            return JournalImage(None, None, None)
        row = conn.execute("SELECT i.illustration_id, i.status, i.task_id AS image_task_id, t.attempts FROM web_illustrations i "
                           "LEFT JOIN web_tasks t ON t.task_id = i.task_id WHERE i.task_id = ?", (task_id,)).fetchone()
        if row is None:
            return JournalImage("processing", None, None)
        if row["status"] == "ready":
            return JournalImage("ready", self.illustrations.url(row["illustration_id"]) if self.illustrations else None, None)
        if row["status"] == "failed":
            outcome = self.illustrations.outcome_of(task_id, conn) if self.illustrations else "failed"
            return JournalImage(outcome or "failed", None, redraw_ticket(row, "image_task_id"))
        return JournalImage("processing", None, None)

    # ---- 显式重画（合同第 7 节 POST …/journal/redraw；CSRF、幂等键由路由负责）----
    def redraw(self, plan_id: str) -> str:
        """重画这份计划最新一页手账的图：只对 failed／unknown 开放，走插画服务的重画凭据（挡迟到的重复请求）。返回插画服务的结论。"""
        with self.storage.connect() as conn:
            journal = self.latest_in(conn, plan_id)
            image = self.image_in(conn, journal["image_task_id"]) if journal is not None else JournalImage(None, None, None)
        if image.ticket is None or self.illustrations is None:
            return "not_retryable" if image.status != "processing" else "already_queued"
        return self.illustrations.retry(image.ticket)


def reference_for_brief(payload: dict, reference: tuple[bytes, str] | None) -> tuple[tuple[bytes, str] | None, str | None]:
    """插画执行时用：手账的身份参考只认**编译时那一张**（指纹一致）。无肖像版不给参考图、也不补画证件照。
    返回 (参考图或 None, 不发送的原因或 None)。"""
    if payload.get("identity_mode") != "photo":
        return None, None
    if reference is None or hashlib.sha256(reference[0]).hexdigest() != payload.get("reference_sha256"):
        return None, "reference_changed"
    return reference, None


def _dt(value: str | None) -> datetime | None:
    return parse_dt(value) if value else None
