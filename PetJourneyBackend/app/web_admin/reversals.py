"""冲正一笔后台补偿（方案 §3「游戏经济」：纠错用冲正 / 补偿记录，不用 SQL 覆盖余额）。

规则（每一条都有用例）：
- **只冲后台发出的补偿**：来源 `admin.compensation` / `admin.compensation.batch`、金额为正、状态 committed。
  游戏里自己产生的流水（工资、旅费、收成……）不走这里——那些要由各自的领域命令纠正。
- **整笔冲正、只能一次**：账本幂等键 `admin:reverse:<原流水号>` 在账本表上唯一，换一个操作号再冲也只会拿到「已经冲正过」。
- **不能冲正自己经手的补偿**：单笔是发放人（原流水的 operator）；批量是提交人、审批人与执行人（批次表里的三个员工号）。
  双人原则，与批量补偿不能自批是同一个道理——经手过这笔钱的人，不能一个人把它撤回。
- **余额不够就拒绝**：`apply_in` 在同一个写事务里核余额，不够就整笔回滚——不扣成负数，也不做部分冲正；由人决定怎么办。
- **写进账本的是给玩家看的说明**（默认「撤回一笔多发的补偿」），内部原因只进审计。玩家的星球银行卡会显示这一条。
- 类型沿用原补偿的 `web_reward`、金额取负，来源 `admin.compensation.reversal`：**不新增 EconomyTransactionType 枚举值**
  （那是共享 schema，要经 I / A）。原补偿那条流水一个字不改，冲正是新的一条。
"""

from __future__ import annotations

import json
from typing import Any

from ..schemas.base import EconomyTransactionType
from ..storage import JourneyStorage
from ..utils import parse_dt, utcnow
from ..web_economy.adapter import InsufficientFunds
from ..web_platform.uow import unit_of_work
from .audit import AuditLog
from .commands import ActorContext, player_view, require_reason, resolve_player_note
from .errors import AdminAPIError, AdminErrorCode
from .permissions import Permission

ADMIN_SOURCES = ("admin.compensation", "admin.compensation.batch")
REVERSAL_SOURCE = "admin.compensation.reversal"
DEFAULT_REVERSAL_NOTE = "撤回一笔多发的补偿"
SELF_REVERSAL_MESSAGE = "不能冲正自己经手（发放、提交、审批或执行）的补偿，换一位同事来做。"


def reversal_key(tx_id: str) -> str:
    return f"admin:reverse:{tx_id}"


def _coin(raw: str | None) -> int:
    try:
        return int((json.loads(raw or "{}") or {}).get("travel_coin") or 0)
    except (ValueError, TypeError, AttributeError):
        return 0


class AdminReversals:
    def __init__(self, storage: JourneyStorage, web, audit: AuditLog, idempotency) -> None:
        self.storage = storage
        self.web = web
        self.audit = audit
        self.idempotency = idempotency

    # ---- 读 ----
    def _load(self, conn, tx_id: str) -> dict[str, Any]:
        row = conn.execute("SELECT tx_id, pet_id, idempotency_key, amounts_json, reason, operator, source, status, created_at "
                           "FROM economy_transactions WHERE tx_id = ?", (tx_id,)).fetchone()
        if row is None:
            raise AdminAPIError.not_found("这一笔流水")
        original = dict(row)
        original["amount"] = _coin(row["amounts_json"])
        original["created_at"] = parse_dt(row["created_at"])
        done = conn.execute("SELECT tx_id, created_at, operator FROM economy_transactions WHERE idempotency_key = ?",
                            (reversal_key(tx_id),)).fetchone()
        original["reversed_by"] = ({"tx_id": done["tx_id"], "created_at": parse_dt(done["created_at"]), "operator": done["operator"]}
                                   if done else None)
        original["internal_reason"] = self._internal_reason(conn, row["idempotency_key"])
        original["handled_by"] = self._handlers(conn, row["idempotency_key"], row["operator"])
        return original

    @staticmethod
    def _internal_reason(conn, key: str) -> str | None:
        """原补偿的内部原因（账本里只有给玩家看的说明）：单笔从审计按操作号找，批量从批次表找。找不到就是 None，不猜。"""
        parts = (key or "").split(":")
        if key.startswith("admin:grant:") and len(parts) >= 3:
            row = conn.execute("SELECT reason FROM admin_audit WHERE action = 'economy.grant' AND operation_id = ? "
                               "AND status = 'succeeded' ORDER BY rowid LIMIT 1", (":".join(parts[2:]),)).fetchone()
            return row["reason"] if row else None
        if key.startswith("admin:batch:") and len(parts) >= 4:
            row = conn.execute("SELECT reason FROM admin_grant_batches WHERE batch_id = ?", (parts[2],)).fetchone()
            return row["reason"] if row else None
        return None

    @staticmethod
    def _handlers(conn, key: str, operator: str | None) -> list[str]:
        """经手过这笔补偿的员工：单笔是发放人；批量另加批次的提交人、审批人、执行人（执行人通常就是 operator）。"""
        handled = {operator} if operator else set()
        parts = (key or "").split(":")
        if key.startswith("admin:batch:") and len(parts) >= 4:
            row = conn.execute("SELECT submitted_by, decided_by, executed_by FROM admin_grant_batches WHERE batch_id = ?",
                               (parts[2],)).fetchone()
            if row is not None:
                handled |= {row["submitted_by"], row["decided_by"], row["executed_by"]} - {None}
        return sorted(handled)

    @staticmethod
    def _refusal(original: dict[str, Any], staff_id: str | None) -> tuple[str, str] | None:
        """不能冲正的原因（代码, 说明）；能冲正返回 None。顺序即优先级。"""
        if original["status"] != "committed":
            return "not_committed", "这笔流水不是已入账状态，不能冲正。"
        if original["source"] not in ADMIN_SOURCES or original["amount"] <= 0:
            return "not_admin_compensation", "只能冲正后台发出的补偿；游戏里产生的流水要由各自的业务纠正。"
        if original["reversed_by"] is not None:
            return "already_reversed", f"这一笔已经冲正过了（{original['reversed_by']['tx_id']}），不会再冲一次。"
        if staff_id is not None and staff_id in original["handled_by"]:
            return "self_reversal", SELF_REVERSAL_MESSAGE
        return None

    def preview(self, staff_id: str, tx_id: str, player_note: str | None = None) -> dict[str, Any]:
        note = resolve_player_note(player_note, DEFAULT_REVERSAL_NOTE)
        with self.storage.connect() as conn:
            original = self._load(conn, tx_id)
            name = conn.execute("SELECT name FROM pets WHERE pet_id = ?", (original["pet_id"],)).fetchone()
        balance = self.web.economy.wallet(original["pet_id"]).balance
        refusal = self._refusal(original, staff_id)
        amount = original["amount"]
        enough = balance >= amount
        return {
            "original": {k: original[k] for k in ("tx_id", "pet_id", "amount", "reason", "internal_reason", "operator",
                                                    "handled_by", "source", "created_at", "reversed_by")},
            "pet_name": name["name"] if name else None,
            "balance_before": balance,
            "balance_after": balance - amount if enough else None,
            "enough_balance": enough,
            "reversible": refusal is None and enough,
            "refusal": {"reason": refusal[0], "message": refusal[1]} if refusal else (
                None if enough else {"reason": "insufficient_balance",
                                     "message": f"余额 {balance}，不够整笔冲正 {amount}：不做部分冲正，也不扣成负数。"}),
            "player_view": player_view(-amount, note),
            "effects": [
                f"新增一条 -{amount} 的冲正流水；原补偿那条一个字不改。",
                f"玩家在星球银行卡上会看到：-{amount} 星币 · {note}。你写的原因只进审计，玩家看不到。",
                "整笔冲正、只能一次；余额不够就拒绝，不扣成负数。",
                "只动游戏账本，平台 API 调用账不变。",
            ],
        }

    # ---- 写 ----
    def reverse(self, ctx: ActorContext, tx_id: str, *, reason: str, player_note: str | None = None) -> dict[str, Any]:
        reason = require_reason(reason)
        note = resolve_player_note(player_note, DEFAULT_REVERSAL_NOTE)
        # 双人原则先在事务外判并留痕：原流水的 operator 与已执行批次的三个员工号都不会再变，在事务外读它们不存在竞态；
        # 放进下面的写事务里的话，随后的 raise 会把那条 denied 审计一起回滚掉。
        with self.storage.connect() as conn:
            original = self._load(conn, tx_id)
        if ctx.staff_id in original["handled_by"]:
            self._deny(ctx, original, reason, "self_reversal")
            raise AdminAPIError(AdminErrorCode.forbidden, SELF_REVERSAL_MESSAGE, 403, details={"reason": "self_reversal"})

        def handler() -> dict[str, Any]:
            key = reversal_key(tx_id)
            try:
                with unit_of_work(self.storage) as conn:
                    current = self._load(conn, tx_id)  # 拿到写锁之后再核一次：别人可能刚冲正过
                    refusal = self._refusal(current, None)
                    if refusal is not None:
                        raise AdminAPIError(AdminErrorCode.conflict, refusal[1], 409, details={
                            "reason": refusal[0],
                            "reversed_by_tx_id": (current["reversed_by"] or {}).get("tx_id")})  # 错误信封里只放可序列化的值
                    wallet = conn.execute("SELECT travel_coin FROM pet_wallets WHERE pet_id = ?", (current["pet_id"],)).fetchone()
                    balance_before = int(wallet["travel_coin"]) if wallet else 0
                    applied = self.web.economy.apply_in(
                        conn, current["pet_id"], -current["amount"], EconomyTransactionType.web_reward, key,
                        reason=note, source=REVERSAL_SOURCE, operator=ctx.staff_id, now=utcnow())
                    if not applied:  # 账本唯一键兜底：并发的另一次冲正已经先写进去了
                        raise AdminAPIError(AdminErrorCode.conflict, "这一笔已经冲正过了，不会再冲一次。", 409,
                                            details={"reason": "already_reversed"})
                    done = conn.execute("SELECT tx_id FROM economy_transactions WHERE idempotency_key = ?", (key,)).fetchone()
                    self.audit.record_in(
                        conn, action="economy.reverse", status="succeeded", outcome=f"-{current['amount']}",
                        permission=Permission.ECONOMY_REVERSE.value, actor_staff_id=ctx.staff_id, actor_username=ctx.username,
                        target_kind="pet", target_id=current["pet_id"], reason=reason, operation_id=ctx.operation_id,
                        request_id=ctx.request_id,
                        changes={"original_tx_id": tx_id, "original_operator": current["operator"],
                                 "original_source": current["source"], "amount": -current["amount"], "ledger_key": key,
                                 "reversal_tx_id": done["tx_id"], "player_note": note, "balance_before": balance_before,
                                 "balance_after": balance_before - current["amount"]})
            except AdminAPIError as exc:
                # 写事务已经整笔回滚；被拒绝的冲正也要留痕，所以在事务外补一条 denied 审计
                self._deny(ctx, original, reason, str((exc.details or {}).get("reason") or exc.code.value))
                raise
            except InsufficientFunds as exc:
                self._deny(ctx, original, reason, "insufficient_balance", balance=exc.balance)
                raise AdminAPIError(AdminErrorCode.conflict,
                                    f"余额 {exc.balance}，不够整笔冲正 {exc.needed}：不做部分冲正，也不扣成负数。请人来决定怎么处理。",
                                    409, details={"reason": "insufficient_balance", "balance": exc.balance,
                                                  "needed": exc.needed}) from exc
            balance = self.web.economy.wallet(original["pet_id"]).balance
            return {"reversal": {"tx_id": done["tx_id"], "ledger_key": key, "amount": -original["amount"],
                                 "original_tx_id": tx_id},
                    "pet_id": original["pet_id"], "balance": balance, "player_view": player_view(-original["amount"], note),
                    "note": "已冲正：账本多了一条负数流水，原补偿那条保留。只动了游戏账本。"}

        outcome = self.idempotency.run(user_id=ctx.staff_id, scope="admin:economy.reverse", key=ctx.operation_id,
                                       payload={"tx_id": tx_id, "reason": reason, "player_note": note}, handler=handler)
        return {**outcome.response, "replayed": outcome.replayed}

    def _deny(self, ctx: ActorContext, original: dict[str, Any], reason: str, why: str, **extra) -> None:
        self.audit.record(action="economy.reverse", status="denied", outcome=why,
                          permission=Permission.ECONOMY_REVERSE.value, actor_staff_id=ctx.staff_id,
                          actor_username=ctx.username, target_kind="pet", target_id=original["pet_id"], reason=reason,
                          operation_id=ctx.operation_id, request_id=ctx.request_id,
                          changes={"original_tx_id": original["tx_id"], "original_operator": original["operator"],
                                   "handled_by": original["handled_by"], **extra})

    def reversed_map(self, tx_ids: list[str]) -> dict[str, str]:
        """原流水号 → 冲正它的那条流水号（给账本页与对账页标「已冲正」用）。"""
        if not tx_ids:
            return {}
        keys = [reversal_key(t) for t in tx_ids]
        with self.storage.connect() as conn:
            rows = conn.execute(f"SELECT tx_id, idempotency_key FROM economy_transactions WHERE idempotency_key IN "
                                f"({','.join('?' for _ in keys)})", keys).fetchall()
        return {row["idempotency_key"].split(":", 2)[2]: row["tx_id"] for row in rows}
