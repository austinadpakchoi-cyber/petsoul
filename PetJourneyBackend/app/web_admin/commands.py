"""后台写操作：每一个都是 权限 → 原因 → 影响预览 → 提交时复核版本 → 业务与审计同一事务 → 真实回执。

共同约定：
- 幂等走**既有**的 `web_platform.idempotency.IdempotencyStore`（user_id 位置放 staff_id，scope 为 `admin:<动作>`）。
  同键同请求返回首个结果并标 `replayed`；同键不同请求 409。领域侧另有稳定唯一键兜底
  （`admin_report_actions.operation_id`、`economy_transactions.idempotency_key`、`admin_content_publications.operation_id`）。
- 版本检查在**拿到写锁之后**读：先 BEGIN IMMEDIATE 再读当前版本，不在事务外先读后写。
- 业务写入与审计在同一个 `conn` 上，一起提交或一起回滚。
- 异步动作的回执写清楚"受理"还是"完成"，不把"已入队"说成"已修好"。

本批**不提供**：整库导出、宠物归属转移、账号硬删除、无上限发币、一键重跑所有任务、
把 unknown 改写成未发送或自动补发。
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from ..schemas.base import EconomyTransactionType
from ..storage import JourneyStorage
from ..utils import iso, utcnow
from ..web_platform.uow import unit_of_work
from .audit import AuditLog
from .errors import AdminAPIError, AdminErrorCode
from .identity import AdminPrincipal
from .permissions import Permission

# 单次游戏补偿上限（星币）。这是**开发期的安全阀**，不是生产授权额度；调高要单独交接（方案 §4 P1）。
MAX_GRANT_COINS = 200
MIN_REASON_LENGTH = 4


@dataclass(frozen=True, slots=True)
class ActorContext:
    principal: AdminPrincipal
    request_id: str
    operation_id: str

    @property
    def staff_id(self) -> str:
        return self.principal.staff.staff_id

    @property
    def username(self) -> str:
        return self.principal.staff.username


def require_reason(reason: str | None) -> str:
    text = (reason or "").strip()
    if len(text) < MIN_REASON_LENGTH:
        raise AdminAPIError.validation("请写清楚处理原因（至少 4 个字），它会进审计。", field="reason")
    return text[:500]


PLAYER_NOTE_MAX = 30
DEFAULT_GRANT_NOTE = "运营补偿"
_NOTE_FORBIDDEN = ("http://", "https://", "www.", "\n", "\r", "\t")


def resolve_player_note(text: str | None, default: str) -> str:
    """账本流水的 `reason` 是**给玩家看的**：星球银行卡直接显示它（`routers/web/credentials.py`）。
    所以写进账本的只能是这句短说明，员工的内部处理原因只进审计。空着就用默认说明；不收链接与换行。"""
    note = " ".join((text or "").split())
    if not note:
        return default
    if len(note) > PLAYER_NOTE_MAX:
        raise AdminAPIError.validation(f"给玩家看的说明最多 {PLAYER_NOTE_MAX} 个字。", field="player_note")
    if any(bad in (text or "").lower() for bad in _NOTE_FORBIDDEN):
        raise AdminAPIError.validation("给玩家看的说明里不能有链接或换行。", field="player_note")
    return note


def player_view(delta: int, note: str) -> dict:
    """玩家在星球银行卡上会看到的那一行（与 credentials.py 的展示字段一致：变动、类型、说明）。"""
    return {"where": "星球银行卡", "delta": delta, "type": EconomyTransactionType.web_reward.value, "reason": note}


def _check_grant_amount(amount: int) -> None:
    # bool 是 int 的子类：True 不能被当成"发 1 星币"。
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0 or amount > MAX_GRANT_COINS:
        raise AdminAPIError.validation(f"补偿金额要在 1–{MAX_GRANT_COINS} 之间。", field="amount")


class AdminCommands:
    def __init__(self, storage: JourneyStorage, web, audit: AuditLog, switches, frozen_accounts, idempotency) -> None:
        self.storage = storage
        self.web = web
        self.audit = audit
        self.switches = switches
        self.frozen = frozen_accounts
        self.idempotency = idempotency

    # ---- 幂等外壳 ----
    def run(self, ctx: ActorContext, action: str, payload: Any, handler: Callable[[], dict]) -> dict:
        outcome = self.idempotency.run(user_id=ctx.staff_id, scope=f"admin:{action}", key=ctx.operation_id,
                                       payload=payload, handler=handler)
        return {**outcome.response, "replayed": outcome.replayed}

    def _audit_kwargs(self, ctx: ActorContext, action: str, permission: Permission, target_kind: str, target_id: str, reason: str) -> dict:
        return {"action": action, "permission": permission.value, "actor_staff_id": ctx.staff_id, "actor_username": ctx.username,
                "target_kind": target_kind, "target_id": target_id, "reason": reason,
                "operation_id": ctx.operation_id, "request_id": ctx.request_id}

    # ---- 账号处置 ----
    def freeze_preview(self, user_id: str) -> dict:
        with self.storage.connect() as conn:
            if conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone() is None:
                raise AdminAPIError.not_found("这个账号")
            flag = conn.execute("SELECT status, version FROM admin_account_flags WHERE user_id = ?", (user_id,)).fetchone()
            sessions = int(conn.execute("SELECT COUNT(*) FROM web_sessions WHERE user_id = ? AND revoked_at IS NULL AND expires_at > ?",
                                        (user_id, iso(utcnow()))).fetchone()[0])
            households = [dict(r) for r in conn.execute(
                "SELECT household_id, role, status FROM web_household_members WHERE user_id = ?", (user_id,))]
            from .directory import PETS_OF_USER  # 同一份"这位用户有哪些宠物"的口径
            pets = int(conn.execute(f"SELECT COUNT(*) FROM ({PETS_OF_USER})", (user_id,)).fetchone()[0])
        return {
            "user_id": user_id,
            "current_status": flag["status"] if flag else "active",
            "current_version": int(flag["version"]) if flag else 0,
            "active_sessions": sessions,
            "households": households,
            "pets": pets,
            "effects": [
                "这个账号登录立刻失效，且不能再登录。",
                f"会撤销它当前 {sessions} 个有效会话。",
                "家庭不会被解散，其他家人的权利不变；宠物不会被转移或删除。",
                "已经发生的费用记录、已入账的星币都不改。",
            ],
        }

    def set_account_frozen(self, ctx: ActorContext, user_id: str, *, frozen: bool, reason: str, expected_version: int | None) -> dict:
        reason = require_reason(reason)
        action = "account.freeze" if frozen else "account.unfreeze"
        permission = Permission.ACCOUNT_FREEZE

        def handler() -> dict:
            now = iso(utcnow())
            with unit_of_work(self.storage) as conn:
                if conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone() is None:
                    raise AdminAPIError.not_found("这个账号")
                row = conn.execute("SELECT status, version FROM admin_account_flags WHERE user_id = ?", (user_id,)).fetchone()
                current_version = int(row["version"]) if row else 0
                current_status = row["status"] if row else "active"
                if expected_version is not None and expected_version != current_version:
                    raise AdminAPIError.version_conflict(expected_version, current_version)
                target = "frozen" if frozen else "active"
                conn.execute(
                    "INSERT INTO admin_account_flags (user_id, status, reason, changed_at, changed_by, version) VALUES (?, ?, ?, ?, ?, 1) "
                    "ON CONFLICT(user_id) DO UPDATE SET status = excluded.status, reason = excluded.reason, changed_at = excluded.changed_at, "
                    "changed_by = excluded.changed_by, version = admin_account_flags.version + 1",
                    (user_id, target, reason, now, ctx.staff_id),
                )
                revoked = 0
                if frozen:
                    # 冻结＝不能再用：撤销这个账号当前全部有效会话，与状态同一事务。
                    cur = conn.execute("UPDATE web_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL", (now, user_id))
                    revoked = cur.rowcount
                new_version = int(conn.execute("SELECT version FROM admin_account_flags WHERE user_id = ?", (user_id,)).fetchone()["version"])
                self.audit.record_in(conn, status="succeeded", outcome=target,
                                     changes={"from": current_status, "to": target, "revoked_sessions": revoked, "version": new_version},
                                     **self._audit_kwargs(ctx, action, permission, "user", user_id, reason))
            self.frozen.invalidate(user_id)
            return {"user_id": user_id, "status": target, "version": new_version, "revoked_sessions": revoked,
                    "note": "解冻不会恢复被撤销的会话，用户需要重新登录。" if not frozen else "已撤销的会话不会自动恢复。"}

        return self.run(ctx, action, {"user_id": user_id, "frozen": frozen, "reason": reason, "expected_version": expected_version}, handler)

    def revoke_user_sessions(self, ctx: ActorContext, user_id: str, *, reason: str) -> dict:
        reason = require_reason(reason)

        def handler() -> dict:
            now = iso(utcnow())
            with unit_of_work(self.storage) as conn:
                if conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone() is None:
                    raise AdminAPIError.not_found("这个账号")
                cur = conn.execute("UPDATE web_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL", (now, user_id))
                revoked = cur.rowcount
                self.audit.record_in(conn, status="succeeded", outcome=f"revoked:{revoked}", changes={"revoked_sessions": revoked},
                                     **self._audit_kwargs(ctx, "account.revoke_session", Permission.ACCOUNT_REVOKE_SESSION,
                                                          "user", user_id, reason))
            return {"user_id": user_id, "revoked_sessions": revoked, "note": "账号本身未冻结；用户可以重新登录。"}

        return self.run(ctx, "account.revoke_session", {"user_id": user_id, "reason": reason}, handler)

    # ---- 举报处理 ----
    def moderation_preview(self, target_kind: str, target_id: str) -> dict:
        with self.storage.connect() as conn:
            current = self._moderation_state(conn, target_kind, target_id)
        return {"target_kind": target_kind, "target_id": target_id, **current,
                "effects": ["下架只改公开可见性；举报记录、原文与审计依据都保留，不做硬删除。",
                            "恢复会把可见性改回 public；两次操作都会留审计。"]}

    def _moderation_state(self, conn: sqlite3.Connection, target_kind: str, target_id: str) -> dict:
        if target_kind == "post":
            row = conn.execute("SELECT visibility, removed_at FROM web_posts WHERE post_id = ?", (target_id,)).fetchone()
            if row is None:
                raise AdminAPIError.not_found("这条动态")
            return {"visible": row["visibility"] != "removed", "visibility": row["visibility"], "removed_at": row["removed_at"]}
        if target_kind == "comment":
            row = conn.execute("SELECT removed_at FROM web_comments WHERE comment_id = ?", (target_id,)).fetchone()
            if row is None:
                raise AdminAPIError.not_found("这条评论")
            return {"visible": row["removed_at"] is None, "visibility": None, "removed_at": row["removed_at"]}
        raise AdminAPIError.validation("只支持处理公开动态（post）与评论（comment）。", field="target_kind")

    def moderate(self, ctx: ActorContext, *, report_id: str | None, target_kind: str, target_id: str, decision: str, reason: str) -> dict:
        reason = require_reason(reason)
        if decision not in ("takedown", "restore", "dismiss"):
            raise AdminAPIError.validation("处理结果只能是 takedown / restore / dismiss。", field="decision")

        def handler() -> dict:
            now_dt = utcnow()
            now = iso(now_dt)
            try:
                return _apply(now_dt, now)
            except AdminAPIError as exc:
                if (exc.details or {}).get("reason") == "claimed_by_other":
                    # 写事务已经回滚；被挡下的这一次也要留痕，所以在事务外补一条 denied 审计
                    self.audit.record(status="denied", outcome="claimed_by_other", changes={"claimed_by": exc.details.get("claimed_by")},
                                      **self._audit_kwargs(ctx, f"report.{decision}", Permission.REPORT_ACTION, target_kind, target_id, reason))
                raise

        def _apply(now_dt, now: str) -> dict:
            from .moderation import active_claim, claimed_by_other  # 认领：同一条内容同一时刻只归一位审核员
            with unit_of_work(self.storage) as conn:
                claim = active_claim(conn, target_kind, target_id, now_dt)
                if claim is not None and claim["staff_id"] != ctx.staff_id:
                    raise claimed_by_other(claim)
                before = self._moderation_state(conn, target_kind, target_id)
                changed = 0
                if decision == "takedown":
                    if target_kind == "post":
                        changed = conn.execute("UPDATE web_posts SET visibility = 'removed', removed_at = ? WHERE post_id = ? AND visibility != 'removed'",
                                               (now, target_id)).rowcount
                    else:
                        changed = conn.execute("UPDATE web_comments SET removed_at = ? WHERE comment_id = ? AND removed_at IS NULL",
                                               (now, target_id)).rowcount
                elif decision == "restore":
                    if target_kind == "post":
                        changed = conn.execute("UPDATE web_posts SET visibility = 'public', removed_at = NULL WHERE post_id = ? AND visibility = 'removed'",
                                               (target_id,)).rowcount
                    else:
                        changed = conn.execute("UPDATE web_comments SET removed_at = NULL WHERE comment_id = ? AND removed_at IS NOT NULL",
                                               (target_id,)).rowcount
                try:
                    conn.execute(
                        "INSERT INTO admin_report_actions (action_id, report_id, target_kind, target_id, decision, reason, staff_id, operation_id, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (f"RA-{uuid.uuid4().hex[:16]}", report_id, target_kind, target_id, decision, reason, ctx.staff_id, ctx.operation_id, now),
                    )
                except sqlite3.IntegrityError as exc:  # operation_id 唯一：并发重放的第二笔在这里被挡住
                    raise AdminAPIError(AdminErrorCode.idempotency_key_reused, "这个操作号已经处理过了。", 409) from exc
                after = self._moderation_state(conn, target_kind, target_id)
                # 处理完了，认领就结束（同一个事务里）；下一次有人举报，重新进队列、重新认领
                conn.execute("DELETE FROM admin_report_claims WHERE target_kind = ? AND target_id = ?", (target_kind, target_id))
                self.audit.record_in(conn, status="succeeded", outcome=decision,
                                     changes={"decision": decision, "before": before, "after": after, "rows_changed": changed},
                                     **self._audit_kwargs(ctx, f"report.{decision}", Permission.REPORT_ACTION, target_kind, target_id, reason))
            return {"target_kind": target_kind, "target_id": target_id, "decision": decision, "changed": changed,
                    "visible": after["visible"],
                    "note": "举报记录与原文保留；这次只改了公开可见性。" if decision != "dismiss" else "记为不处理；内容可见性未改。"}

        return self.run(ctx, f"report.{decision}", {"target_kind": target_kind, "target_id": target_id,
                                                    "decision": decision, "reason": reason, "report_id": report_id}, handler)

    # ---- 供应商开关 ----
    def set_ai_calls(self, ctx: ActorContext, *, state: str, reason: str, expected_version: int | None) -> dict:
        from .switches import AI_CALLS
        reason = require_reason(reason)

        def handler() -> dict:
            result = self.switches.set(
                AI_CALLS, state, reason=reason, actor=ctx.staff_id, expected_version=expected_version,
                audit=self.audit,
                audit_kwargs=self._audit_kwargs(ctx, f"provider.{state}", Permission.PROVIDER_PAUSE, "switch", AI_CALLS, reason),
            )
            return {"switch": AI_CALLS, "state": result.state, "version": result.version,
                    "note": "暂停只挡住还没发出的调用；在途的调用、已经记下的用量、结果未确认的调用都不动，也不补发。"}

        return self.run(ctx, f"provider.{state}", {"switch": "ai_calls", "state": state, "reason": reason,
                                                   "expected_version": expected_version}, handler)

    # ---- 失败任务的受控恢复 ----
    def recover_photo(self, ctx: ActorContext, illustration_id: str, *, reason: str, diagnosis) -> dict:
        reason = require_reason(reason)

        def handler() -> dict:
            # 可恢复性判断放在幂等外壳**里面**：同键重放直接拿首次结果，不会因为
            # "任务已经被上一轮排回队列"而在第二次被误判成不可恢复。
            attempt = diagnosis.photo(illustration_id)
            if attempt is None:
                raise AdminAPIError.not_found("这张照片的记录")
            if not attempt.recoverable:
                # 明确拒绝，并说清是哪一种不可恢复。unknown 绝不放行。
                latest = attempt.reservations[0] if attempt.reservations else None
                if attempt.call_state == "unknown":
                    why = (f"这次调用的结果未确认（额度预占停在 {latest['status'] if latest else '未知'}），很可能已经发出去了。"
                           "不自动重发、不抹掉费用记录；要处理请先向供应商确认，再由人决定。")
                else:
                    why = ("只有「明确没画成」的任务才允许恢复：当前状态是 "
                           f"illustration={attempt.status} / task={attempt.task_status}。")
                self.audit.record(status="denied", outcome=attempt.call_state,
                                  changes={"illustration_status": attempt.status, "task_status": attempt.task_status,
                                           "call_state": attempt.call_state},
                                  **self._audit_kwargs(ctx, "task.recover", Permission.TASK_RECOVER, "illustration", illustration_id, reason))
                raise AdminAPIError(AdminErrorCode.not_recoverable, why, 409,
                                    details={"call_state": attempt.call_state, "illustration_status": attempt.status,
                                             "task_status": attempt.task_status})
            # 真正的防重复在 illustrations.retry 的同一个写事务里（条件更新：状态＋失败尝试次数）。
            # 它返回四种结果，这里**照实**回报，不一律说成"已创建新尝试"。
            result = self.web.illustrations.retry(attempt.retry_ticket)
            status = "succeeded" if result == "requeued" else "failed" if result == "not_retryable" else "succeeded"
            self.audit.record(status=status, outcome=result,
                              changes={"ticket": attempt.retry_ticket, "result": result, "task_id": attempt.task_id},
                              **self._audit_kwargs(ctx, "task.recover", Permission.TASK_RECOVER, "illustration", illustration_id, reason))
            if result == "not_retryable":
                raise AdminAPIError(AdminErrorCode.not_recoverable, "这个任务已经不能重排（可能已经画好或已作废）。", 409,
                                    details={"result": result})
            texts = {"requeued": "已受理：新的一次尝试已经排进队列，还没执行。",
                     "already_queued": "没有新建尝试：这个任务已经在排队或执行中。",
                     "stale_attempt": "没有新建尝试：你看到的是更早那次失败，请刷新后再判断。"}
            return {"illustration_id": illustration_id, "task_id": attempt.task_id, "result": result,
                    "accepted": result == "requeued", "note": texts[result]}

        return self.run(ctx, "task.recover", {"illustration_id": illustration_id, "reason": reason}, handler)

    # ---- 游戏补偿（只动游戏账本）----
    def grant_preview(self, pet_id: str, amount: int, player_note: str | None = None) -> dict:
        # 预览与提交用同一套校验：不存在的宠物不给算"余额 0 → 20"，超限金额不给算出一个发不出去的结果。
        _check_grant_amount(amount)
        note = resolve_player_note(player_note, DEFAULT_GRANT_NOTE)
        profile = self.web.pets.profile(pet_id)
        if profile is None:
            raise AdminAPIError.not_found("这只宠物")
        from .directory import owner_of_pet  # 同一份"谁在照顾这只宠物"的口径
        with self.storage.connect() as conn:
            caregiver = owner_of_pet(conn, pet_id)
        caregiver_frozen = bool(caregiver and self.frozen.is_frozen(caregiver))
        wallet = self.web.economy.wallet(pet_id)
        effects = ["只写游戏账本，一条可以追溯的入账记录。",
                   f"玩家在星球银行卡上会看到：+{amount} 星币 · {note}。你写的处理原因只进审计，玩家看不到。",
                   "不影响平台 API 调用账：调用次数、估算费用、账单确认费用都不变。",
                   f"单次上限 {MAX_GRANT_COINS} 星币（开发期安全阀，不是生产授权额度）。",
                   "这一次操作有固定的操作号：结果没确认时用同一个操作号重试，不会入账两次。"]
        if caregiver_frozen:
            # 批量补偿会跳过这种宠物；单笔是员工逐只点名，只提醒、不拦——但要让人在点确认之前就看到。
            effects.insert(0, "注意：照顾这只宠物的账号当前是冻结状态。批量补偿会跳过它；单笔不拦，请在原因里写明为什么仍要发。")
        return {"pet_id": pet_id, "pet_name": profile.name, "caregiver_user_id": caregiver,
                "caregiver_frozen": caregiver_frozen, "balance_before": wallet.balance, "amount": amount,
                "balance_after": wallet.balance + amount, "currency": "travel_coin", "max_amount": MAX_GRANT_COINS,
                "player_view": player_view(amount, note), "effects": effects}

    def grant_coins(self, ctx: ActorContext, pet_id: str, amount: int, *, reason: str, player_note: str | None = None) -> dict:
        reason = require_reason(reason)
        _check_grant_amount(amount)
        note = resolve_player_note(player_note, DEFAULT_GRANT_NOTE)
        if self.web.pets.profile(pet_id) is None:
            raise AdminAPIError.not_found("这只宠物")

        def handler() -> dict:
            # 账本自己的幂等键就是这次操作号：同键重放在 economy_transactions.idempotency_key 唯一约束上只生效一次。
            key = f"admin:grant:{ctx.operation_id}"
            with unit_of_work(self.storage) as conn:
                # 写进账本的是给玩家看的说明；内部原因只进下面这条审计。
                applied = self.web.economy.apply_in(
                    conn, pet_id, amount, EconomyTransactionType.web_reward, key,
                    reason=note, source="admin.compensation", operator=ctx.staff_id, now=utcnow(),
                )
                self.audit.record_in(conn, status="succeeded" if applied else "replayed", outcome=f"+{amount}",
                                     changes={"amount": amount, "currency": "travel_coin", "ledger_key": key, "applied": applied,
                                              "player_note": note},
                                     **self._audit_kwargs(ctx, "economy.grant", Permission.ECONOMY_GRANT, "pet", pet_id, reason))
            wallet = self.web.economy.wallet(pet_id)
            return {"pet_id": pet_id, "amount": amount, "applied": applied, "balance": wallet.balance,
                    "currency": "travel_coin", "ledger_key": key, "player_view": player_view(amount, note),
                    "note": "只动了游戏账本；平台 API 调用账没有变化。" if applied else "同一个操作号之前已经入过账，这次没有重复记账。"}

        return self.run(ctx, "economy.grant", {"pet_id": pet_id, "amount": amount, "reason": reason, "player_note": note}, handler)
