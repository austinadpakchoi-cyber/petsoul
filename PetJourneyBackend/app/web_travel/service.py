"""心愿命令端口（TRV-03；合同 4.1 B → A、4.2 C → A、第 7 节命令）。A 是心愿与计划的**唯一写入方**。

每个命令一份实现、两个入口（合同 0.1）：`xxx_in(conn, …)` 在调用方的写事务里执行（不开连接、不 BEGIN、不提交），
`xxx(…)` 自己开短事务。读接口只读已保存的状态：**绝不**触发研究、生图或出行（方案 §13）。

  - `propose`：按 `(pet_id, trigger_event_id)` 幂等；该宠物已有进行中的心愿就原样返回、`created=False`。
    研究任务在**同一事务**里登记（B 不另发「去研究」）；被暂停的宠物不形成心愿（合同 4.5，复用 `RuntimeStore.paused`）。
  - `update_waiting`：B 只写生活侧原因（钱、承诺、维护态）；研究侧原因归 A，互不覆盖。缺钱时带目标与现有游戏金币。
  - `ready_plan_in`／`link_journey_in`：C 在出发事务里复核并关联；任何版本不符或状态不是 ready 抛 VersionConflict，C 整体回滚；
    同一旅程重复关联幂等。**不预建假旅程**。
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime
from typing import Callable

from ..utils import iso, parse_dt, utcnow
from ..web_platform.tasks import WebTaskQueue, supersede_pending_in_tx
from ..web_platform.uow import unit_of_work
from . import store
from .model import (
    CANCELLED, COMPLETED, LIFE_REASONS, LINKED, MAX_CANDIDATES, MAX_INTEREST_TAGS, MISSING_FUNDS, OPEN_STATES, QUOTA_DENIED,
    R_FAILED, R_QUEUED, R_READY, R_RUNNING, R_UNKNOWN, READY, RESEARCH_FAILED, RESEARCH_PENDING, RESEARCH_UNKNOWN,
    ACTIVE, PlanRef, VersionConflict, WishRef, WishRejected, WishView, status_for, waiting_union,
)

RESEARCH_KIND = "travel_research"
_TAG = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def research_dedupe(wish_id: str, round_: int, suffix: str = "") -> str:
    return f"{RESEARCH_KIND}:{wish_id}:{int(round_)}{suffix}"


class TravelWishService:
    def __init__(self, storage, tasks: WebTaskQueue) -> None:
        self.storage = storage
        self.tasks = tasks
        # 合同 4.5：装配注入 `lambda conn, pet_id: runtime_store.paused(pet_id, conn=conn)`；不再读一次那一列
        self.paused_in: Callable[[sqlite3.Connection, str], bool] = lambda conn, pet_id: False
        # 兴趣标签白名单（合同 §10「来自白名单」）：None 时只校验形状，白名单来源由 B／I 定后注入
        self.interest_whitelist: frozenset[str] | None = None
        self.research_attempts = 2

    # ---- B → A ----
    def propose_in(self, conn: sqlite3.Connection, *, pet_id: str, user_id: str, trigger_event_id: str, candidates: list[dict],
                   selected: int, interest_tags: list[str] | tuple[str, ...], owner_reason: str, funds_goal: int | None,
                   now: datetime | None = None, household_id: str | None = None,
                   window: tuple[str | None, str | None] = (None, None)) -> WishRef:
        stamp = iso(now or utcnow())
        chosen = self._validate(pet_id, trigger_event_id, candidates, selected, interest_tags, owner_reason, funds_goal)
        existing = store.wish_by_trigger_in(conn, pet_id, trigger_event_id) or store.open_wish_in(conn, pet_id)
        if existing is not None:
            return WishRef(existing["wish_id"], int(existing["wish_revision"]), False, existing["status"])
        if self.paused_in(conn, pet_id):
            raise WishRejected("paused")
        wish_id = f"tw-{uuid.uuid4().hex[:16]}"
        row = {"wish_id": wish_id, "pet_id": pet_id, "user_id": user_id, "household_id": household_id, "wish_revision": 1,
               "status": ACTIVE, "trigger_event_id": trigger_event_id, "interest_tags_json": store.dumps(list(interest_tags)),
               "candidates_json": store.dumps(candidates), "selected_index": int(selected),
               "destination_key": chosen["destination_key"], "destination_name": chosen["name"], "city": chosen["city"],
               "owner_reason": owner_reason.strip(), "funds_goal": funds_goal, "window_start": window[0], "window_end": window[1],
               "research_waiting_json": store.dumps([RESEARCH_PENDING]), "research_round": 1,
               "plan_id": f"tp-{uuid.uuid4().hex[:16]}", "created_at": stamp, "updated_at": stamp}
        if not store.insert_wish_in(conn, row):  # 并发下另一个事务先插了同一只宠物的心愿：读回那一条
            winner = store.wish_by_trigger_in(conn, pet_id, trigger_event_id) or store.open_wish_in(conn, pet_id)
            return WishRef(winner["wish_id"], int(winner["wish_revision"]), False, winner["status"])
        self.tasks.enqueue_in(conn, RESEARCH_KIND, research_dedupe(wish_id, 1), {"wish_id": wish_id, "round": 1},
                              max_attempts=self.research_attempts, now=now)
        return WishRef(wish_id, 1, True, ACTIVE)

    def propose(self, **kwargs) -> WishRef:
        with unit_of_work(self.storage) as conn:
            return self.propose_in(conn, **kwargs)

    def update_waiting_in(self, conn: sqlite3.Connection, wish_id: str, expected_revision: int, waiting_reasons,
                          reconsider_after: str | None, last_considered_at: str | None, *, now: datetime | None = None,
                          current_coins: int | None = None) -> WishRef:
        """合同 4.1 的唯一签名。`last_considered_at`＝那一轮 evaluate 的 now（冷却闸读它，合同 17.1）；`reconsider_after` 只给页面看。"""
        reasons = set(waiting_reasons)
        if not reasons <= LIFE_REASONS:
            raise WishRejected(f"not life-side reasons: {sorted(reasons - LIFE_REASONS)}")
        row = self._open_or_conflict(conn, wish_id)
        detail = {"target_coins": row["funds_goal"], "current_coins": current_coins} if MISSING_FUNDS in reasons else {}
        research = set(store.loads(row["research_waiting_json"], []))
        status = status_for(row["status"], waiting_union(reasons, research), row["plan_revision"] is not None)
        stamp = iso(now or utcnow())
        revision = store.update_wish_in(conn, wish_id, expected_revision, stamp, life_waiting_json=store.dumps(sorted(reasons)),
                                        life_detail_json=store.dumps(detail), reconsider_after=reconsider_after, status=status)
        if last_considered_at is not None:  # 按宠物记，一份口径（同一事务）
            store.note_considered_in(conn, row["pet_id"], last_considered_at, stamp)
        return WishRef(wish_id, revision, False, status)

    def update_waiting(self, wish_id: str, expected_revision: int, waiting_reasons, reconsider_after: str | None,
                       last_considered_at: str | None, **kwargs) -> WishRef:
        with unit_of_work(self.storage) as conn:
            return self.update_waiting_in(conn, wish_id, expected_revision, waiting_reasons, reconsider_after, last_considered_at, **kwargs)

    def considered_in(self, conn: sqlite3.Connection, pet_id: str, considered_at: str, *, now: datetime | None = None) -> None:
        """**只在 `decision.considered_at` 非空的那一轮调**（只有 ask_brain 会给值；决定留在家的那一轮也在其中，
        因为那一轮本身就是 ask_brain）。**不是每一轮 tick 都调**：那样上次考虑时刻永远被推到现在，冷却永远到不了期，
        而这张表只往后走、推错了退不回来（B 核出）。合同 17.1。"""
        store.note_considered_in(conn, pet_id, considered_at, iso(now or utcnow()))

    def last_considered_in(self, conn: sqlite3.Connection, pet_id: str) -> str | None:
        """纯读：按宠物的「上次考虑」；从没考虑过是 None。"""
        return store.last_considered_in(conn, pet_id)

    def cancel_in(self, conn: sqlite3.Connection, wish_id: str, expected_revision: int, *, now: datetime | None = None) -> WishRef:
        self._open_or_conflict(conn, wish_id)
        revision = store.update_wish_in(conn, wish_id, expected_revision, iso(now or utcnow()), status=CANCELLED)
        supersede_pending_in_tx(conn, f"{RESEARCH_KIND}:{wish_id}:", "wish cancelled", now=now)
        return WishRef(wish_id, revision, False, CANCELLED)

    def cancel(self, wish_id: str, expected_revision: int, **kwargs) -> WishRef:
        with unit_of_work(self.storage) as conn:
            return self.cancel_in(conn, wish_id, expected_revision, **kwargs)

    # ---- 纯读 ----
    def read_in(self, conn: sqlite3.Connection, pet_id: str) -> WishView | None:
        """进行中的心愿优先；没有就给最近一条（已关联／已完成／已取消），页面据此说清楚现在的状态。"""
        row = store.open_wish_in(conn, pet_id) or store.latest_wish_in(conn, pet_id)
        return None if row is None else self._view(conn, row)

    def read(self, pet_id: str) -> WishView | None:
        with self.storage.connect() as conn:
            return self.read_in(conn, pet_id)

    # ---- C → A（出发事务内）----
    def ready_plan_in(self, conn: sqlite3.Connection, pet_id: str) -> PlanRef | None:
        row = store.open_wish_in(conn, pet_id)
        if row is None or row["status"] != READY or row["plan_revision"] is None:
            return None
        plan = store.plan_in(conn, row["plan_id"], row["plan_revision"])
        return PlanRef(plan["plan_id"], int(plan["plan_revision"]), row["wish_id"], int(row["wish_revision"]), pet_id,
                       plan["destination_key"], plan["valid_from"], plan["valid_until"],
                       tuple(store.loads(plan["preconditions_json"], [])))

    def link_journey_in(self, conn: sqlite3.Connection, plan_id: str, plan_revision: int, wish_id: str, wish_revision: int,
                        journey_id: str, now: datetime | None = None) -> None:
        row = store.wish_in(conn, wish_id)
        if row is None:
            raise VersionConflict(f"wish {wish_id} not found")
        same = (row["plan_id"], row["plan_revision"], row["journey_id"]) == (plan_id, int(plan_revision), journey_id)
        if row["status"] == LINKED and same:
            return  # 同一旅程重复关联：幂等
        if row["status"] != READY or row["plan_id"] != plan_id or row["plan_revision"] != int(plan_revision):
            raise VersionConflict(f"wish {wish_id} is {row['status']} at plan {row['plan_id']}#{row['plan_revision']}")
        store.update_wish_in(conn, wish_id, wish_revision, iso(now or utcnow()), status=LINKED, journey_id=journey_id)
        if not store.link_plan_in(conn, plan_id, plan_revision, journey_id):
            raise VersionConflict(f"plan {plan_id}#{plan_revision} is linked to another journey")

    def complete_in(self, conn: sqlite3.Connection, journey_id: str, now: datetime | None = None) -> WishRef | None:
        """旅程结束：关联着这趟**真**旅程的心愿 linked → completed。没有关联的（老旅程）什么都不做；已结束的不复活。"""
        row = conn.execute("SELECT * FROM web_travel_wishes WHERE journey_id = ? AND status = ?", (journey_id, LINKED)).fetchone()
        if row is None:
            return None
        revision = store.update_wish_in(conn, row["wish_id"], int(row["wish_revision"]), iso(now or utcnow()), status=COMPLETED)
        return WishRef(row["wish_id"], revision, False, COMPLETED)

    @staticmethod
    def stale_facts_in(conn: sqlite3.Connection, fact_ids, now: datetime) -> tuple[str, ...]:
        """C 在出发事务里逐条复核计划的前置事实（`PlanRef.preconditions`）：返回已过期的 fact_id。
        有效期左闭右开 `[valid_from, valid_until)`（合同 §29.3）：**到期那一刻已算过期**。
        **库里查不到的也算进来**——数据对不上时宁可挡下出发，不放行。必须用出发那个 `conn`（合同 0.1）。"""
        wanted = tuple(dict.fromkeys(fact_ids))
        if not wanted:
            return ()
        rows = {r["fact_id"]: r["valid_until"] for r in conn.execute(
            f"SELECT fact_id, valid_until FROM web_travel_facts WHERE fact_id IN ({', '.join('?' for _ in wanted)})", wanted)}
        return tuple(fid for fid in wanted if fid not in rows or (rows[fid] and parse_dt(rows[fid]) <= now))

    # ---- 研究侧（research.py 调；研究原因只由 A 写）----
    def set_research_waiting_in(self, conn: sqlite3.Connection, row: sqlite3.Row, reasons, now: str, **fields) -> int:
        research = sorted(set(reasons))
        life = set(store.loads(row["life_waiting_json"], []))
        has_plan = fields.get("plan_revision", row["plan_revision"]) is not None
        status = status_for(row["status"], waiting_union(life, set(research)), has_plan)
        return store.update_wish_in(conn, row["wish_id"], int(row["wish_revision"]), now,
                                    research_waiting_json=store.dumps(research), status=status, **fields)

    # ---- 内部 ----
    def _validate(self, pet_id, trigger_event_id, candidates, selected, interest_tags, owner_reason, funds_goal) -> dict:
        if not pet_id or not trigger_event_id:
            raise WishRejected("pet_id and trigger_event_id are required")
        if not 1 <= len(candidates) <= MAX_CANDIDATES or not 0 <= int(selected) < len(candidates):
            raise WishRejected("need 1-3 candidates and a selected one among them")
        for candidate in candidates:
            if not all(isinstance(candidate.get(key), str) and candidate.get(key) for key in ("destination_key", "name", "city")):
                raise WishRejected("candidate needs destination_key, name and city")
        tags = list(interest_tags)
        if len(tags) > MAX_INTEREST_TAGS or any(not _TAG.match(str(tag)) for tag in tags):
            raise WishRejected("interest tags must be short snake_case codes")
        if self.interest_whitelist is not None and not set(tags) <= self.interest_whitelist:
            raise WishRejected(f"interest tags outside whitelist: {sorted(set(tags) - self.interest_whitelist)}")
        if not owner_reason or not owner_reason.strip() or len(owner_reason) > 200:
            raise WishRejected("owner_reason must be 1-200 characters")
        if funds_goal is not None and (not isinstance(funds_goal, int) or funds_goal < 0):
            raise WishRejected("funds_goal must be a non-negative integer of game coins")
        return candidates[int(selected)]

    @staticmethod
    def _open_or_conflict(conn: sqlite3.Connection, wish_id: str) -> sqlite3.Row:
        row = store.wish_in(conn, wish_id)
        if row is None or row["status"] not in OPEN_STATES:
            raise VersionConflict(f"wish {wish_id} is not open")
        return row

    def _view(self, conn: sqlite3.Connection, row: sqlite3.Row) -> WishView:
        life, research = set(store.loads(row["life_waiting_json"], [])), set(store.loads(row["research_waiting_json"], []))
        detail = store.loads(row["life_detail_json"], {})
        return WishView(
            wish_id=row["wish_id"], pet_id=row["pet_id"], wish_revision=int(row["wish_revision"]), status=row["status"],
            destination_key=row["destination_key"], destination_name=row["destination_name"], city=row["city"],
            owner_reason=row["owner_reason"], funds_goal=row["funds_goal"], waiting_reasons=waiting_union(life, research),
            research_state=self._research_state_in(conn, row, research), research_round=int(row["research_round"]),
            plan_id=row["plan_id"], plan_revision=row["plan_revision"], journey_id=row["journey_id"],
            reconsider_after=row["reconsider_after"], last_considered_at=store.last_considered_in(conn, row["pet_id"]),
            target_coins=detail.get("target_coins"), current_coins=detail.get("current_coins"),
            candidates=tuple(store.loads(row["candidates_json"], [])))

    @staticmethod
    def _research_state_in(conn: sqlite3.Connection, row: sqlite3.Row, research: set[str]) -> str | None:
        """研究任务状态与心愿主状态分开给（合同 5.1）。`unknown` 独立于 `failed`，不折叠。"""
        if RESEARCH_UNKNOWN in research:
            return R_UNKNOWN
        if RESEARCH_FAILED in research or QUOTA_DENIED in research:
            return R_FAILED
        if RESEARCH_PENDING not in research:
            return R_READY if row["plan_revision"] is not None else None
        task = conn.execute("SELECT status FROM web_tasks WHERE kind = ? AND dedupe_key LIKE ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                            (RESEARCH_KIND, research_dedupe(row["wish_id"], row["research_round"]) + "%")).fetchone()
        return R_RUNNING if task is not None and task["status"] == "running" else R_QUEUED
