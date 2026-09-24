"""批量游戏补偿：提交 → 审批（另一个人）→ 执行。

方案 §4 P1 对批量动作的三条要求，这里逐条落实：

1. **独立权限**：提交要 `economy.grant_batch`，审批要 `economy.approve`，两条权限分开发；
   单笔补偿的 `economy.grant` 给不了批量的口子。
2. **影响预览**：提交时就算清楚——每只宠物当前余额、发完是多少、哪些发不出去（宠物不存在、
   照顾人被冻结）。预览**不写任何东西**。
3. **额度数值配置后才开放**：三个上限（人数、每只金额、合计金额）必须由部署方显式配置
   （`PETSOUL_ADMIN_BATCH_*`）。没配全就整条能力关闭，接口如实回 NOT_CONFIGURED——
   **不给默认额度**，因为"默认放开多少钱"这种事不该由代码替运营决定。

还有一条不在方案文字里、但必须守住的：**双人原则**。提交人不能审批自己的批次，
即使他同时握着两条权限（平台负责人就是这种情况）。

钱的真相仍然只有一本账：每一条执行都是 `economy.apply_in`，幂等键
`admin:batch:<batch_id>:<pet_id>`，靠 `economy_transactions.idempotency_key` 的唯一约束兜底。
平台 API 调用账一分不动。
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..schemas.base import EconomyTransactionType
from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from ..web_platform.uow import unit_of_work
from .audit import AuditLog
from .commands import DEFAULT_GRANT_NOTE, ActorContext, player_view, require_reason, resolve_player_note
from .errors import AdminAPIError, AdminErrorCode
from .permissions import Permission


@dataclass(frozen=True, slots=True)
class BatchLimits:
    max_recipients: int
    max_coins_per_pet: int
    max_total_coins: int

    @property
    def configured(self) -> bool:
        return self.max_recipients > 0 and self.max_coins_per_pet > 0 and self.max_total_coins > 0


def load_batch_limits() -> BatchLimits:
    """三个上限都要显式配置。任何一个缺失或非正数 → 整条能力关闭。"""

    def read(name: str) -> int:
        raw = (os.getenv(name) or "").strip()
        try:
            return int(raw)
        except ValueError:
            return 0

    return BatchLimits(
        max_recipients=read("PETSOUL_ADMIN_BATCH_MAX_RECIPIENTS"),
        max_coins_per_pet=read("PETSOUL_ADMIN_BATCH_MAX_COINS_PER_PET"),
        max_total_coins=read("PETSOUL_ADMIN_BATCH_MAX_TOTAL_COINS"),
    )


NOT_CONFIGURED_MESSAGE = (
    "批量补偿的额度还没有配置，这项能力处于关闭状态。"
    "要开放，请由部署方显式设置 PETSOUL_ADMIN_BATCH_MAX_RECIPIENTS / "
    "PETSOUL_ADMIN_BATCH_MAX_COINS_PER_PET / PETSOUL_ADMIN_BATCH_MAX_TOTAL_COINS。"
    "代码不提供默认额度。"
)


@dataclass(frozen=True, slots=True)
class BatchRow:
    batch_id: str
    title: str
    reason: str
    amount_per_pet: int
    recipient_count: int
    total_amount: int
    status: str
    version: int
    submitted_by: str
    submitted_at: datetime
    decided_by: str | None
    decided_at: datetime | None
    decision_note: str | None
    executed_by: str | None
    executed_at: datetime | None
    applied_count: int | None
    skipped_count: int | None
    applied_amount: int | None
    player_note: str   # 玩家在星球银行卡上看到的说明；旧批次为空时按默认说明


def _row(row) -> BatchRow:
    return BatchRow(
        batch_id=row["batch_id"], title=row["title"], reason=row["reason"],
        amount_per_pet=int(row["amount_per_pet"]), recipient_count=int(row["recipient_count"]),
        total_amount=int(row["total_amount"]), status=row["status"], version=int(row["version"]),
        submitted_by=row["submitted_by"], submitted_at=parse_dt(row["submitted_at"]),
        decided_by=row["decided_by"], decided_at=parse_dt(row["decided_at"]) if row["decided_at"] else None,
        decision_note=row["decision_note"], executed_by=row["executed_by"],
        executed_at=parse_dt(row["executed_at"]) if row["executed_at"] else None,
        applied_count=None if row["applied_count"] is None else int(row["applied_count"]),
        skipped_count=None if row["skipped_count"] is None else int(row["skipped_count"]),
        applied_amount=None if row["applied_amount"] is None else int(row["applied_amount"]),
        player_note=row["player_note"] or DEFAULT_GRANT_NOTE,
    )


class AdminBatchGrants:
    def __init__(self, storage: JourneyStorage, web, audit: AuditLog, frozen, idempotency=None) -> None:
        self.storage = storage
        self.web = web
        self.audit = audit
        self.frozen = frozen
        # 提交走既有的 IdempotencyStore：结果没确认时用同一个操作号重试，拿回的是第一次的结果，而不是 409。
        self.idempotency = idempotency
        self.limits = load_batch_limits()

    # ---- 能力状态 ----
    def capability(self) -> dict[str, Any]:
        return {
            "enabled": self.limits.configured,
            "max_recipients": self.limits.max_recipients or None,
            "max_coins_per_pet": self.limits.max_coins_per_pet or None,
            "max_total_coins": self.limits.max_total_coins or None,
            "note": NOT_CONFIGURED_MESSAGE if not self.limits.configured else
                    "提交与审批必须是两个人；执行只写游戏账本，不影响平台 API 调用账。",
        }

    def _require_enabled(self) -> None:
        if not self.limits.configured:
            raise AdminAPIError(AdminErrorCode.not_configured, NOT_CONFIGURED_MESSAGE, 503,
                                details={"capability": "economy.grant_batch", "reason": "limits_not_configured"})

    # ---- 影响预览（纯读）----
    def preview(self, pet_ids: list[str], amount_per_pet: int, player_note: str | None = None) -> dict[str, Any]:
        self._require_enabled()
        note = resolve_player_note(player_note, DEFAULT_GRANT_NOTE)
        unique = list(dict.fromkeys(pid.strip() for pid in pet_ids if pid and pid.strip()))
        if not unique:
            raise AdminAPIError.validation("至少要给一只宠物。", field="pet_ids")
        self._check_limits(unique, amount_per_pet)
        rows: list[dict[str, Any]] = []
        payable = 0
        with self.storage.connect() as conn:
            for pet_id in unique:
                pet = conn.execute("SELECT name FROM pets WHERE pet_id = ?", (pet_id,)).fetchone()
                if pet is None:
                    rows.append({"pet_id": pet_id, "name": None, "eligible": False, "reason": "没有这只宠物",
                                 "balance_before": None, "balance_after": None})
                    continue
                caregiver = conn.execute(
                    "SELECT m.user_id FROM web_household_pets hp JOIN web_household_members m ON m.household_id = hp.household_id "
                    "AND m.status = 'active' WHERE hp.pet_id = ? ORDER BY CASE m.role WHEN 'admin' THEN 0 ELSE 1 END LIMIT 1",
                    (pet_id,)).fetchone()
                owner_frozen = bool(caregiver and self.frozen.is_frozen(caregiver["user_id"]))
                balance = int((conn.execute("SELECT travel_coin FROM pet_wallets WHERE pet_id = ?", (pet_id,)).fetchone()
                               or {"travel_coin": 0})["travel_coin"])
                if owner_frozen:
                    rows.append({"pet_id": pet_id, "name": pet["name"], "eligible": False, "reason": "照顾人的账号已冻结",
                                 "balance_before": balance, "balance_after": balance})
                    continue
                payable += 1
                rows.append({"pet_id": pet_id, "name": pet["name"], "eligible": True, "reason": None,
                             "balance_before": balance, "balance_after": balance + amount_per_pet})
        return {
            "recipients": rows,
            "amount_per_pet": amount_per_pet,
            "eligible_count": payable,
            "skipped_count": len(unique) - payable,
            "total_amount": payable * amount_per_pet,
            "currency": "travel_coin",
            "effects": [
                f"给 {payable} 只宠物各发 {amount_per_pet} 星币，合计 {payable * amount_per_pet}。",
                f"玩家在星球银行卡上会看到：+{amount_per_pet} 星币 · {note}。批次原因只给审批人和审计看，玩家看不到。",
                "只写游戏账本；平台 API 调用账（次数与费用）不受影响。",
                "提交之后还需要另一位有审批权限的同事批准才能执行。",
                "同一个批次重复执行不会重复发放（账本幂等键按批次+宠物）。",
            ],
            "player_view": player_view(amount_per_pet, note),
            "limits": self.capability(),
        }

    def _check_limits(self, pet_ids: list[str], amount_per_pet: int) -> None:
        limits = self.limits
        if not isinstance(amount_per_pet, int) or amount_per_pet <= 0:
            raise AdminAPIError.validation("每只宠物的金额要是正整数。", field="amount_per_pet")
        if amount_per_pet > limits.max_coins_per_pet:
            raise AdminAPIError.validation(f"每只宠物最多 {limits.max_coins_per_pet} 星币。", field="amount_per_pet")
        if len(pet_ids) > limits.max_recipients:
            raise AdminAPIError.validation(f"一个批次最多 {limits.max_recipients} 只宠物，现在是 {len(pet_ids)} 只。", field="pet_ids")
        total = len(pet_ids) * amount_per_pet
        if total > limits.max_total_coins:
            raise AdminAPIError.validation(f"批次合计最多 {limits.max_total_coins} 星币，现在是 {total}。", field="amount_per_pet")

    # ---- 提交 ----
    def submit(self, ctx: ActorContext, *, title: str, reason: str, amount_per_pet: int, pet_ids: list[str],
               player_note: str | None = None) -> dict[str, Any]:
        self._require_enabled()
        reason = require_reason(reason)
        note = resolve_player_note(player_note, DEFAULT_GRANT_NOTE)
        title = (title or "").strip()[:80]
        if not title:
            raise AdminAPIError.validation("给这个批次起个名字，审批的人要看。", field="title")
        if self.idempotency is None:
            return {**self._submit(ctx, title=title, reason=reason, amount_per_pet=amount_per_pet, pet_ids=pet_ids, note=note),
                    "replayed": False}
        # 同一个操作号、同一份内容 → 回第一次的结果（replayed=true）；同一个操作号、不同内容 → 409。
        # 下面 operation_id 的唯一约束仍然留着，是第二道兜底。
        outcome = self.idempotency.run(
            user_id=ctx.staff_id, scope="admin:economy.batch_submit", key=ctx.operation_id,
            payload={"title": title, "reason": reason, "amount_per_pet": amount_per_pet, "pet_ids": list(pet_ids),
                     "player_note": note},
            handler=lambda: self._submit(ctx, title=title, reason=reason, amount_per_pet=amount_per_pet, pet_ids=pet_ids, note=note))
        return {**outcome.response, "replayed": outcome.replayed}

    def _submit(self, ctx: ActorContext, *, title: str, reason: str, amount_per_pet: int, pet_ids: list[str],
                note: str) -> dict[str, Any]:
        preview = self.preview(pet_ids, amount_per_pet)
        eligible = [row["pet_id"] for row in preview["recipients"] if row["eligible"]]
        if not eligible:
            raise AdminAPIError(AdminErrorCode.conflict, "这个名单里没有一只宠物能发放，批次不提交。", 409,
                                details={"recipients": preview["recipients"]})
        batch_id = f"GB-{uuid.uuid4().hex[:12].upper()}"
        now = iso(utcnow())
        with unit_of_work(self.storage) as conn:
            try:
                conn.execute(
                    "INSERT INTO admin_grant_batches (batch_id, title, reason, amount_per_pet, recipient_count, total_amount, status, "
                    "version, submitted_by, submitted_at, operation_id, player_note) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'pending_approval', 1, ?, ?, ?, ?)",
                    (batch_id, title, reason, amount_per_pet, len(eligible), len(eligible) * amount_per_pet,
                     ctx.staff_id, now, ctx.operation_id, note),
                )
            except sqlite3.IntegrityError as exc:
                raise AdminAPIError(AdminErrorCode.idempotency_key_reused, "这个操作号已经提交过批次了。", 409) from exc
            for pet_id in eligible:
                conn.execute(
                    "INSERT INTO admin_grant_batch_items (batch_id, pet_id, amount, status, updated_at) VALUES (?, ?, ?, 'pending', ?)",
                    (batch_id, pet_id, amount_per_pet, now))
            self.audit.record_in(
                conn, action="economy.batch_submit", status="succeeded", outcome=f"pending:{len(eligible)}",
                actor_staff_id=ctx.staff_id, actor_username=ctx.username, permission=Permission.ECONOMY_GRANT_BATCH.value,
                target_kind="grant_batch", target_id=batch_id, reason=reason, operation_id=ctx.operation_id,
                request_id=ctx.request_id,
                changes={"title": title, "amount_per_pet": amount_per_pet, "recipients": len(eligible),
                         "total": len(eligible) * amount_per_pet, "skipped": preview["skipped_count"], "player_note": note},
            )
        return {"batch_id": batch_id, "status": "pending_approval", "version": 1,
                "recipient_count": len(eligible), "total_amount": len(eligible) * amount_per_pet,
                "skipped": [row for row in preview["recipients"] if not row["eligible"]],
                "player_view": player_view(amount_per_pet, note),
                "note": "已提交，等另一位有审批权限的同事批准。还没有发出任何星币。"}

    # ---- 审批（必须换一个人）----
    def decide(self, ctx: ActorContext, batch_id: str, *, approve: bool, note: str, expected_version: int) -> dict[str, Any]:
        self._require_enabled()
        note = require_reason(note)
        now = iso(utcnow())
        # 双人原则：即使同时握有两条权限也不能自批。先在事务外查一次并留痕——
        # 放进下面那个写事务里的话，随后的 raise 会把整笔回滚，denied 那条审计也就跟着没了。
        # `submitted_by` 提交之后就不会变，所以在事务外读它不存在竞态。
        with self.storage.connect() as conn:
            row = conn.execute("SELECT submitted_by FROM admin_grant_batches WHERE batch_id = ?", (batch_id,)).fetchone()
        if row is not None and row["submitted_by"] == ctx.staff_id:
            self.audit.record(
                action="economy.batch_decide", status="denied", outcome="self_approval",
                actor_staff_id=ctx.staff_id, actor_username=ctx.username, permission=Permission.ECONOMY_APPROVE.value,
                target_kind="grant_batch", target_id=batch_id, reason=note, request_id=ctx.request_id,
                operation_id=ctx.operation_id, changes={"submitted_by": row["submitted_by"]})
            raise AdminAPIError(AdminErrorCode.forbidden, "不能审批自己提交的批次，换一位同事来批。", 403,
                                details={"reason": "self_approval"})
        with unit_of_work(self.storage) as conn:
            row = self._locked(conn, batch_id, expected_version)
            if row["status"] != "pending_approval":
                raise AdminAPIError(AdminErrorCode.conflict, f"这个批次当前是 {row['status']}，不能再审批。", 409,
                                    details={"status": row["status"]})
            status = "approved" if approve else "rejected"
            conn.execute("UPDATE admin_grant_batches SET status = ?, version = version + 1, decided_by = ?, decided_at = ?, "
                         "decision_note = ? WHERE batch_id = ?", (status, ctx.staff_id, now, note, batch_id))
            version = int(conn.execute("SELECT version FROM admin_grant_batches WHERE batch_id = ?", (batch_id,)).fetchone()["version"])
            self.audit.record_in(
                conn, action="economy.batch_decide", status="succeeded", outcome=status,
                actor_staff_id=ctx.staff_id, actor_username=ctx.username, permission=Permission.ECONOMY_APPROVE.value,
                target_kind="grant_batch", target_id=batch_id, reason=note, operation_id=ctx.operation_id,
                request_id=ctx.request_id, changes={"status": status, "submitted_by": row["submitted_by"]})
        return {"batch_id": batch_id, "status": status, "version": version,
                "note": "已批准，还需要执行一步才会真正入账。" if approve else "已驳回，这个批次不会再执行。"}

    # ---- 执行 ----
    def execute(self, ctx: ActorContext, batch_id: str, *, expected_version: int, note: str | None = None) -> dict[str, Any]:
        self._require_enabled()
        note = (note or "").strip()[:500] or None
        now_dt = utcnow()
        now = iso(now_dt)
        with unit_of_work(self.storage) as conn:
            row = self._locked(conn, batch_id, expected_version)
            if row["status"] == "executed":
                # 重放：如实回报"已经执行过"，不再发一次。
                return {**self._result(conn, batch_id), "replayed": True,
                        "note": "这个批次之前已经执行过了，没有重复发放。"}
            if row["status"] != "approved":
                raise AdminAPIError(AdminErrorCode.conflict, f"只有已批准的批次才能执行，当前是 {row['status']}。", 409,
                                    details={"status": row["status"]})
            amount = int(row["amount_per_pet"])
            applied = skipped = 0
            applied_amount = 0
            for item in conn.execute("SELECT pet_id FROM admin_grant_batch_items WHERE batch_id = ? ORDER BY pet_id", (batch_id,)).fetchall():
                pet_id = item["pet_id"]
                ledger_key = f"admin:batch:{batch_id}:{pet_id}"
                if conn.execute("SELECT 1 FROM pets WHERE pet_id = ?", (pet_id,)).fetchone() is None:
                    self._item(conn, batch_id, pet_id, "skipped", "宠物已不存在", None, now)
                    skipped += 1
                    continue
                # 提交到执行之间照顾人可能被冻结：执行时再核一次，不拿提交时的快照当数。
                caregiver = conn.execute(
                    "SELECT m.user_id FROM web_household_pets hp JOIN web_household_members m ON m.household_id = hp.household_id "
                    "AND m.status = 'active' WHERE hp.pet_id = ? ORDER BY CASE m.role WHEN 'admin' THEN 0 ELSE 1 END LIMIT 1",
                    (pet_id,)).fetchone()
                if caregiver and self.frozen.is_frozen(caregiver["user_id"]):
                    self._item(conn, batch_id, pet_id, "skipped", "照顾人的账号已冻结", None, now)
                    skipped += 1
                    continue
                changed = self.web.economy.apply_in(
                    conn, pet_id, amount, EconomyTransactionType.web_reward, ledger_key,
                    reason=row["player_note"] or DEFAULT_GRANT_NOTE, source="admin.compensation.batch",
                    operator=ctx.staff_id, now=now_dt)  # 账本里是给玩家看的说明；批次的内部原因只进审计
                self._item(conn, batch_id, pet_id, "applied", None if changed else "账本里已有同键记录", ledger_key, now)
                applied += 1
                if changed:
                    applied_amount += amount
            conn.execute("UPDATE admin_grant_batches SET status = 'executed', version = version + 1, executed_by = ?, executed_at = ?, "
                         "applied_count = ?, skipped_count = ?, applied_amount = ? WHERE batch_id = ?",
                         (ctx.staff_id, now, applied, skipped, applied_amount, batch_id))
            self.audit.record_in(
                conn, action="economy.batch_execute", status="succeeded", outcome=f"applied:{applied}/skipped:{skipped}",
                actor_staff_id=ctx.staff_id, actor_username=ctx.username, permission=Permission.ECONOMY_GRANT_BATCH.value,
                target_kind="grant_batch", target_id=batch_id, reason=row["reason"], operation_id=ctx.operation_id,
                request_id=ctx.request_id,
                changes={"applied": applied, "skipped": skipped, "applied_amount": applied_amount, "currency": "travel_coin",
                         "execute_note": note})
            result = self._result(conn, batch_id)
        return {**result, "replayed": False,
                "note": f"已执行：{applied} 只入账、{skipped} 只跳过。只动了游戏账本，平台 API 调用账没有变化。"}

    def _item(self, conn: sqlite3.Connection, batch_id: str, pet_id: str, status: str, outcome: str | None,
              ledger_key: str | None, now: str) -> None:
        conn.execute("UPDATE admin_grant_batch_items SET status = ?, outcome = ?, ledger_key = ?, updated_at = ? "
                     "WHERE batch_id = ? AND pet_id = ?", (status, outcome, ledger_key, now, batch_id, pet_id))

    def _locked(self, conn: sqlite3.Connection, batch_id: str, expected_version: int):
        row = conn.execute("SELECT * FROM admin_grant_batches WHERE batch_id = ?", (batch_id,)).fetchone()
        if row is None:
            raise AdminAPIError.not_found("这个批次")
        if int(row["version"]) != expected_version:
            raise AdminAPIError.version_conflict(expected_version, int(row["version"]))
        return row

    # ---- 读 ----
    def _result(self, conn: sqlite3.Connection, batch_id: str) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM admin_grant_batches WHERE batch_id = ?", (batch_id,)).fetchone()
        items = [dict(r) for r in conn.execute(
            "SELECT pet_id, amount, status, outcome, ledger_key FROM admin_grant_batch_items WHERE batch_id = ? ORDER BY pet_id",
            (batch_id,))]
        return {"batch": _as_dict(_row(row)), "items": items}

    def get(self, batch_id: str) -> dict[str, Any]:
        with self.storage.connect() as conn:
            if conn.execute("SELECT 1 FROM admin_grant_batches WHERE batch_id = ?", (batch_id,)).fetchone() is None:
                raise AdminAPIError.not_found("这个批次")
            return self._result(conn, batch_id)

    def list_batches(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.storage.connect() as conn:
            return [_as_dict(_row(row)) for row in conn.execute(
                "SELECT * FROM admin_grant_batches ORDER BY submitted_at DESC LIMIT ?", (max(1, min(200, limit)),))]


def _as_dict(row: BatchRow) -> dict[str, Any]:
    return {field: getattr(row, field) for field in BatchRow.__slots__}
