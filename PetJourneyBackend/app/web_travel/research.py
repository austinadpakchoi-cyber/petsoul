"""旅行研究任务（TRV-03；方案 §11.2；合同 4.3、11.3、11.7）。

一个心愿一轮研究（`research_round`），一轮里**每次发送尝试一行回执、一个 operation**：
`travel_research:<wish_id>:<轮次>:<领取代数>`，与额度预占同号。

  1. 领取后在**领取围栏**里：复核心愿仍进行中、轮次没变 → 看这一轮已有的回执决定怎么做 → 预占 → 落 `intent`，提交。
     - 已有 `published`：已经做完；
     - 已有 `answered`（响应存下了、发布没成）：**复用，不发送**（T07）；
     - 已有 `intent`／`unknown`：可能已经发出 → **不重发**，挂 `research_unknown`（T06）。TTL 到期、租约被接管都**不算证明没发**；
       只有账本上这笔预占确定 `released`（not_sent）才当没发，开新的一代；
     - 预占被拒：挂 `quota_denied`（平台额度，**不是**宠物的钱），不发送；
     - 宠物被暂停：这一轮先不发，稍后再试（合同 4.5）。
  2. **事务外**调 ResearchPort（不重试、不换模型）。
  3. 响应**先落盘**：独立事务，**不受领取围栏约束**——丢了租约，已经发生的费用事实也不回滚；再结算预占。
     结算抛错单独记 `settle_state='pending_reconcile'`，**不盖掉主流程**，也不盖掉之后的租约丢失。
  4. 在领取围栏里复核心愿与轮次 → 程序核对事实（`facts.review`）→ 发布计划修订 → 回执标 `published`。
     围栏失效（租约被接管）照常抛出，`answered` 留给合法执行者复用。

研究请求**只从心愿行取公开字段**（目的地、城市、日期窗口、白名单兴趣标签）；不经组合根的 `wishes_of`（那里是主人叮嘱原文），
也不带给主人的理由、候选说明（T11）。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime

from ..utils import iso, utcnow
from ..web_platform.budget import BudgetLimit
from ..web_platform.tasks import WebTask, WebTaskQueue, run_once
from ..web_platform.uow import unit_of_work
from . import facts, store
from .model import (
    ANSWERED, DISCARDED, INTENT, MAYBE_SENT, NOT_SENT, OPEN_STATES, PUBLISHED, QUOTA_DENIED, RESEARCH_FAILED, RESEARCH_PENDING,
    RESEARCH_UNKNOWN, UNKNOWN, VersionConflict, WishRef,
)
from .ports import (
    DraftStop, ResearchDraft, ResearchFact, ResearchNotSent, ResearchPort, ResearchRequest, ResearchResult, ResearchSource,
)
from .service import RESEARCH_KIND, TravelWishService, research_dedupe

logger = logging.getLogger("petsoul.web.travel")
PURPOSE = "travel_research"
PROVIDER = "research"


class ResearchUnsettled(Exception):
    """这一轮有可能已经发出、还没结清的 operation：不换号重发（方案 §11.2）。路由回 409，reason=research_unsettled。"""


class ResearchInProgress(Exception):
    """这个心愿已有研究在排或在跑：不再排一个（否则后来者会把前者的意图误判成未确认）。路由回 409，reason=already_queued。"""


class ResearchMisconfigured(RuntimeError):
    """接了研究端口却没接额度账本：不预占就不发（fail-closed）。`install_travel` 构造时已拦；这里拦绕开它、直接构造服务的路径。"""


@dataclass(frozen=True, slots=True)
class Step:
    action: str  # done／reuse／send／unknown／denied／paused
    operation_id: str | None = None
    request: ResearchRequest | None = None
    result: ResearchResult | None = None
    permit: object | None = None
    wish_id: str | None = None
    round: int | None = None


class TravelResearchService:
    kind = RESEARCH_KIND

    def __init__(self, storage, tasks: WebTaskQueue, wishes: TravelWishService, ledger=None) -> None:
        self.storage = storage
        self.tasks = tasks
        self.wishes = wishes
        self.ledger = ledger
        self.port: ResearchPort | None = None  # I 的 TRV-04 适配器；装配注入
        self.journals = None  # journal.TravelJournalService：计划发布的同一事务里登记手账（没接就只有文字计划）
        self.per_pet_daily = 2  # 每宠每天研究请求上限（兜底；一次选中心愿本就只研究一次）
        self.global_daily = 0  # 0＝该层不限
        self.paused_retry_seconds = 900

    def available(self) -> bool:
        return self.port is not None

    # ---- 任务执行 ----
    def precheck(self, task: WebTask) -> bool:
        with self.storage.connect() as conn:
            row = store.wish_in(conn, task.payload["wish_id"])
        return row is not None and row["status"] in OPEN_STATES and int(row["research_round"]) == int(task.payload["round"])

    def run_pending(self, worker_id: str = "web-travel-research", limit: int = 5) -> int:
        if not self.available():
            return 0  # 没接端口：任务留在队里，接上以后再做；不造一个"没查到"
        handled = 0
        for _ in range(limit):
            task = run_once(self.tasks, {RESEARCH_KIND: self}, worker_id)
            if task is None:
                break
            handled += 1
            if task.status == "failed":
                self._mark_failed(task)
        return handled

    def run_claimed(self, task: WebTask, claim, queue: WebTaskQueue) -> None:
        now = utcnow()
        with queue.fenced(claim, complete=False) as conn:
            step = self._prepare_in(conn, task, claim, now)
        if step.action == "done":
            with queue.fenced(claim):
                return
        if step.action == "paused":
            queue.fail_claim(claim, "travel_research paused", retryable=True, retry_delay_seconds=self.paused_retry_seconds)
            return
        if step.action in ("unknown", "denied"):
            self._stop(task, claim, queue, RESEARCH_UNKNOWN if step.action == "unknown" else QUOTA_DENIED, now)
            return
        result = step.result
        if step.action == "send":
            try:
                result = self.port.research(step.request)
            except ResearchNotSent as exc:
                self._record_outcome(step, NOT_SENT, "not_sent", exc)
                queue.fail_claim(claim, "travel_research not_sent", retryable=True)
                return
            except Exception as exc:  # noqa: BLE001 - ResearchUnknown 及其他一切：可能已经发出，保守按未确认处理
                self._record_outcome(step, UNKNOWN, "unknown", exc)
                self._stop(task, claim, queue, RESEARCH_UNKNOWN, now)
                return
            self._record_answer(step, result)
        with queue.fenced(claim) as conn:
            self._publish_in(conn, task, step.operation_id, result, utcnow())

    # ---- 显式重做（合同第 7 节 POST …/research/retry；带 CSRF、幂等键、expected_revision 由路由负责）----
    def retry_in(self, conn: sqlite3.Connection, wish_id: str, expected_revision: int, *, now: datetime | None = None) -> WishRef:
        """这一轮有已存下、没发布的应答 → 同一轮再排一次（执行时复用，不发送）；否则开新的一轮（主人明确要的新一次付费尝试）。"""
        now = now or utcnow()
        row = store.wish_in(conn, wish_id)
        if row is None or row["status"] not in OPEN_STATES or int(row["wish_revision"]) != int(expected_revision):
            raise VersionConflict(f"wish {wish_id} is not open at revision {expected_revision}")
        busy = conn.execute("SELECT 1 FROM web_tasks WHERE kind = ? AND dedupe_key LIKE ? AND status IN ('queued', 'running') LIMIT 1",
                            (RESEARCH_KIND, f"{RESEARCH_KIND}:{wish_id}:%")).fetchone()
        if busy is not None:
            raise ResearchInProgress(wish_id)
        round_ = int(row["research_round"])
        receipts = store.receipts_for_round_in(conn, wish_id, round_)
        unsettled = [r for r in receipts if r["status"] in MAYBE_SENT
                     and self._reservation_status_in(conn, r["operation_id"]) not in ("released", "settled")]
        if unsettled:
            raise ResearchUnsettled(unsettled[0]["operation_id"])
        target = round_ if any(r["status"] == ANSWERED for r in receipts) else round_ + 1
        self.tasks.enqueue_in(conn, RESEARCH_KIND, research_dedupe(wish_id, target, f":retry-{uuid.uuid4().hex[:8]}"),
                              {"wish_id": wish_id, "round": target}, max_attempts=self.wishes.research_attempts, now=now)
        revision = self.wishes.set_research_waiting_in(conn, row, {RESEARCH_PENDING}, iso(now), research_round=target)
        return WishRef(wish_id, revision, False, store.wish_in(conn, wish_id)["status"])

    def retry(self, wish_id: str, expected_revision: int, **kwargs) -> WishRef:
        with unit_of_work(self.storage) as conn:
            return self.retry_in(conn, wish_id, expected_revision, **kwargs)

    @staticmethod
    def _reservation_status_in(conn: sqlite3.Connection, operation_id: str) -> str | None:
        try:
            row = conn.execute("SELECT status FROM web_budget_reservations WHERE operation_id = ?", (operation_id,)).fetchone()
        except sqlite3.OperationalError:
            return None
        return None if row is None else row["status"]

    # ---- 1. 领取围栏里：复核、决定、预占、落意图 ----
    def _prepare_in(self, conn: sqlite3.Connection, task: WebTask, claim, now: datetime) -> Step:
        wish_id, round_ = task.payload["wish_id"], int(task.payload["round"])
        row = store.wish_in(conn, wish_id)
        if row is None or row["status"] not in OPEN_STATES or int(row["research_round"]) != round_:
            return Step("done")
        receipts = store.receipts_for_round_in(conn, wish_id, round_)
        if any(r["status"] == PUBLISHED for r in receipts):
            return Step("done")
        answered = [r for r in receipts if r["status"] == ANSWERED]
        if answered:
            return Step("reuse", answered[-1]["operation_id"], result=result_from_json(answered[-1]["result_json"]))
        for receipt in receipts:
            if receipt["status"] not in MAYBE_SENT:
                continue
            if not self._released_in(conn, receipt["operation_id"]):
                return Step("unknown", receipt["operation_id"])
            store.update_receipt_in(conn, receipt["operation_id"], iso(now), only_from=MAYBE_SENT, status=NOT_SENT)
        if self.wishes.paused_in(conn, row["pet_id"]):
            return Step("paused")
        operation_id = f"{RESEARCH_KIND}:{wish_id}:{round_}:{int(claim.claim_generation)}"
        if store.receipt_in(conn, operation_id) is not None:
            return Step("unknown", operation_id)  # 同一代已经有过意图：绝不再发一次
        permit = self._reserve_in(conn, operation_id, row["pet_id"], now)
        if getattr(permit, "status", None) != "reserved":  # 没拿到预占（含空）一律不发：不留「空就放行」的口子
            logger.info("travel research budget denied wish=%s reason=%s", wish_id, getattr(permit, "reason", "unknown"))
            return Step("denied")
        request = ResearchRequest(operation_id, wish_id, int(row["wish_revision"]), row["destination_key"], row["destination_name"],
                                  row["city"], row["window_start"], row["window_end"], tuple(store.loads(row["interest_tags_json"], [])))
        stamp = iso(now)
        store.insert_receipt_in(conn, {"receipt_id": f"rr-{uuid.uuid4().hex[:16]}", "operation_id": operation_id, "wish_id": wish_id,
                                       "pet_id": row["pet_id"], "plan_id": row["plan_id"], "round": round_,
                                       "attempt_no": int(claim.claim_generation), "task_id": task.task_id, "status": INTENT,
                                       "query_json": store.dumps(asdict(request)), "created_at": stamp, "updated_at": stamp})
        return Step("send", operation_id, request=request, permit=permit, wish_id=wish_id, round=round_)

    def _reserve_in(self, conn: sqlite3.Connection, operation_id: str, pet_id: str, now: datetime):
        if self.ledger is None:  # 只拦要花钱的这一步：复用已存应答不预占，照常发布
            raise ResearchMisconfigured(f"travel research {operation_id}: no budget ledger, refusing to send without a reservation")
        limits = [BudgetLimit("provider:research:daily", self.global_daily)] if self.global_daily else []
        if self.per_pet_daily:
            limits.append(BudgetLimit(f"pet:{pet_id}:travel_research", self.per_pet_daily))
        return self.ledger.reserve(operation_id, provider=PROVIDER, purpose=PURPOSE, subject_scope=f"pet:{pet_id}", units=1,
                                   limits=limits, now=now, conn=conn)

    def _released_in(self, conn: sqlite3.Connection, operation_id: str) -> bool:
        """只有账本上这笔预占确定释放（not_sent）才算没发出。读不到账本、没有预占、reserved／expired／unknown 都不算。"""
        return self._reservation_status_in(conn, operation_id) == "released"

    # ---- 3. 围栏外：费用事实先落盘 ----
    def _record_answer(self, step: Step, result: ResearchResult) -> None:
        cost_amount, cost_currency = facts.money(result.cost_amount, result.cost_currency)  # 认不出币种就整条不带（原样在 result_json）
        with unit_of_work(self.storage) as conn:
            store.update_receipt_in(
                conn, step.operation_id, iso(utcnow()), only_from=(INTENT, UNKNOWN), status=ANSWERED,
                requested_model=result.requested_model, effective_model=result.effective_model,
                provider_request_id=result.provider_request_id, usage_json=store.dumps(result.usage), search_uses=result.search_uses,
                tool_executions=int(result.tool_executions), tool_execution_ids_json=store.dumps(list(result.tool_execution_ids)),
                cost_amount=cost_amount, cost_currency=cost_currency, result_json=result_to_json(result))
            row = store.wish_in(conn, step.wish_id)
            if row is None or row["status"] not in OPEN_STATES or int(row["research_round"]) != step.round:
                # 响应在路上时心愿被取消／换了轮次：永远不会有人发布它。标 discarded（响应照样留着），
                # 不让结果取决于发布与取消谁先抢到领取
                store.update_receipt_in(conn, step.operation_id, iso(utcnow()), only_from=(ANSWERED,), status=DISCARDED)
        self._settle(step, "succeeded", 1, result.provider_request_id)

    def _record_outcome(self, step: Step, status: str, outcome: str, exc: BaseException) -> None:
        with unit_of_work(self.storage) as conn:
            store.update_receipt_in(conn, step.operation_id, iso(utcnow()), only_from=(INTENT,), status=status, error=type(exc).__name__)
        self._settle(step, outcome, 0 if outcome == "not_sent" else 1, None)

    def _settle(self, step: Step, outcome: str, units: int, provider_request_id: str | None) -> None:
        if self.ledger is None or step.permit is None:
            return
        try:
            self.ledger.settle(step.permit, outcome, actual_units=units, provider_request_id=provider_request_id)
            state = "settled"
        except Exception:  # noqa: BLE001 - 结算失败单列待对账，不盖掉主流程
            logger.exception("travel research settle failed operation=%s", step.operation_id)
            state = "pending_reconcile"
        try:
            with unit_of_work(self.storage) as conn:
                store.update_receipt_in(conn, step.operation_id, iso(utcnow()), settle_state=state)
        except Exception:  # noqa: BLE001 - 记不下结算状态也不影响回执本身
            logger.exception("travel research settle state not recorded operation=%s", step.operation_id)

    # ---- 4. 领取围栏里：复核、核对、发布 ----
    def _publish_in(self, conn: sqlite3.Connection, task: WebTask, operation_id: str, result: ResearchResult, now: datetime) -> None:
        wish_id, round_ = task.payload["wish_id"], int(task.payload["round"])
        row = store.wish_in(conn, wish_id)
        if row is None or row["status"] not in OPEN_STATES or int(row["research_round"]) != round_:
            store.update_receipt_in(conn, operation_id, iso(now), only_from=(ANSWERED,), status=DISCARDED)
            return
        outcome = facts.review(result, now=now, primary=(row["destination_key"], row["destination_name"]),
                               window=(row["window_start"], row["window_end"]))
        revision = store.next_plan_revision_in(conn, row["plan_id"])
        plan, fact_rows = facts.build_plan(wish=row, result=result, outcome=outcome, operation_id=operation_id,
                                           plan_revision=revision, now=now)
        store.insert_facts_in(conn, fact_rows)
        store.insert_plan_in(conn, plan)
        self.wishes.set_research_waiting_in(conn, row, outcome.waiting, iso(now), plan_revision=revision)
        if self.journals is not None:  # 同一事务：计划与它那一页手账（及手账图的任务）同生共死
            self.journals.plan_published_in(conn, row, plan, now)
        store.update_receipt_in(conn, operation_id, iso(now), only_from=(ANSWERED,), status=PUBLISHED, plan_revision=revision)

    def _stop(self, task: WebTask, claim, queue: WebTaskQueue, reason: str, now: datetime) -> None:
        """不发送（可能已发出／额度不够）：挂等待原因、任务落定为不可自动重试。"""
        with queue.fenced(claim, complete=False) as conn:
            self._set_reason_in(conn, task, reason, now)
        queue.fail_claim(claim, f"travel_research {reason}", retryable=False)

    def _set_reason_in(self, conn: sqlite3.Connection, task: WebTask, reason: str, now: datetime) -> None:
        row = store.wish_in(conn, task.payload["wish_id"])
        if row is not None and row["status"] in OPEN_STATES and int(row["research_round"]) == int(task.payload["round"]):
            kept = set(store.loads(row["research_waiting_json"], [])) - {RESEARCH_PENDING, RESEARCH_UNKNOWN, QUOTA_DENIED, RESEARCH_FAILED}
            self.wishes.set_research_waiting_in(conn, row, kept | {reason}, iso(now))

    def _mark_failed(self, task: WebTask) -> None:
        """次数用尽（例如两次都确定没发出）：还在等研究的心愿改挂 research_failed；已挂 unknown 的不改。"""
        with unit_of_work(self.storage) as conn:
            row = store.wish_in(conn, task.payload["wish_id"])
            if row is None or row["status"] not in OPEN_STATES or int(row["research_round"]) != int(task.payload["round"]):
                return
            research = set(store.loads(row["research_waiting_json"], []))
            if RESEARCH_PENDING in research and RESEARCH_UNKNOWN not in research:
                self._set_reason_in(conn, task, RESEARCH_FAILED, utcnow())


# ---- 回执里的结果：原样存、原样取（复用时发布出同一份计划）----
def result_to_json(result: ResearchResult) -> str:
    return json.dumps(asdict(result), ensure_ascii=False, sort_keys=True, default=str)


def result_from_json(text: str) -> ResearchResult:
    data = json.loads(text)
    draft = data.get("draft")
    return ResearchResult(
        requested_model=data["requested_model"], effective_model=data.get("effective_model"),
        provider_request_id=data.get("provider_request_id"), usage=data.get("usage") or {}, search_uses=data.get("search_uses"),
        tool_executions=int(data.get("tool_executions") or 0), tool_execution_ids=tuple(data.get("tool_execution_ids") or ()),
        cost_amount=data.get("cost_amount"), cost_currency=data.get("cost_currency"),
        sources=tuple(ResearchSource(**s) for s in data.get("sources") or ()),
        facts=tuple(ResearchFact(**{**f, "source_ids": tuple(f.get("source_ids") or ())}) for f in data.get("facts") or ()),
        draft=None if draft is None else ResearchDraft(
            title=draft["title"], summary=draft["summary"],
            stops=tuple(DraftStop(**{**s, "fact_keys": tuple(s.get("fact_keys") or ())}) for s in draft.get("stops") or ()),
            owner_tips=tuple(draft.get("owner_tips") or ()),
            tip_fact_keys=tuple(tuple(keys) for keys in draft.get("tip_fact_keys") or ()),
            rain_alternative=draft.get("rain_alternative")))
