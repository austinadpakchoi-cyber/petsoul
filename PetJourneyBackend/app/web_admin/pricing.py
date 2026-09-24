"""平台调用的价格表与费用估算（方案 §3「平台 API 成本」）。

几条硬规则，每一条都落在代码里，不靠界面自觉：

- **没有价格就是未知，不是 0。** 估算只用员工录入、带来源与生效时间的单价；没录价的那部分计入用量单独列出
  （`unpriced_units`），不会被悄悄当成免费。
- **币种分开。** 人民币与美元各算各的，不互相换算、不相加；与游戏星币没有任何关系（这个模块不引用任何经济模块）。
- **价格只追加。** 改价＝录一条生效时间更晚的新价；录错了＝把那条标为作废（留原因）。历史不删不改，数据库触发器守着
  （迁移 1540）。一次调用用哪一条价：按预占创建时刻，取同一供应商、同一用途里生效时间最晚且不晚于那一刻的有效价；
  这个用途没有专门的价，才退回同一供应商的通用价（用途 `*`）。
- **计入用量与额度计数器同口径**（`metering.counted_units`）：确定没发出的计 0，预占过期按预占全额，在途不计入。
- **账本只记调用次数，不记 token。** 单价按「每个计量单位」录入；对按 token 计费的模型，这只能是按平均每次的粗估。
- **「账单确认费用」要等供应商账单导入（方案 P2）。** 在那之前一律为未知。
- 已结清的调用算进「估算费用」；结果未确认（unknown）与预占过期（expired）的算进「未确认费用」——
  它们很可能已经发出、也可能已经计费，但没有确认，不能和已结清的混成一个数。
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from ..web_platform.uow import unit_of_work
from .audit import AuditLog
from .commands import ActorContext, require_reason
from .errors import AdminAPIError, AdminErrorCode
from .metering import counted_units
from .permissions import Permission

CURRENCIES = ("CNY", "USD")
MICROS = 1_000_000
MAX_UNIT_PRICE_MICROS = 10_000 * MICROS      # 单价上限：每个计量单位 1 万（防手滑多打几个 0）
MAX_WINDOW_DAYS = 31                           # 分析查询有边界（方案 §5）
_PRICE_RE = re.compile(r"^\d{1,5}(\.\d{1,6})?$")
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,39}$")
UNCONFIRMED_STATUSES = ("unknown", "expired")

UNIT_NOTE = ("额度账只记调用次数，没有 token 数；单价按「每个计量单位」录入。"
             "对按 token 计费的模型，估算只能是按平均每次的粗估。")
BILLED_NOTE = "账单确认费用要等供应商账单导入（方案 P2）；在那之前一律为未知，不显示为 0。"


def parse_price(text: str) -> int:
    """'0.28' → 280000（百万分之一货币单位）。只收普通十进制写法，最多 6 位小数；不收科学计数法与负数。"""
    raw = (text or "").strip()
    if not _PRICE_RE.match(raw):
        raise AdminAPIError.validation("单价写成普通小数，例如 0.28；最多 6 位小数，不能是负数。", field="unit_price")
    micros = int(Decimal(raw) * MICROS)
    if micros > MAX_UNIT_PRICE_MICROS:
        raise AdminAPIError.validation("单价超过每个计量单位 10000，请核对是不是多打了位数。", field="unit_price")
    return micros


def format_micros(micros: int) -> str:
    """280000 → '0.28'；12000000 → '12'。只用整数运算，不经过浮点。"""
    sign = "-" if micros < 0 else ""
    whole, frac = divmod(abs(int(micros)), MICROS)
    text = f"{whole}.{frac:06d}".rstrip("0").rstrip(".")
    return sign + text


@dataclass(frozen=True, slots=True)
class PriceRow:
    price_id: str
    provider: str
    purpose: str
    currency: str
    unit_price_micros: int
    effective_from: datetime
    source_note: str
    model_note: str | None
    status: str
    created_by: str
    created_at: datetime
    retired_by: str | None
    retired_at: datetime | None
    retired_reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "price_id": self.price_id, "provider": self.provider, "purpose": self.purpose, "currency": self.currency,
            "unit_price": format_micros(self.unit_price_micros), "unit_price_micros": self.unit_price_micros,
            "unit": "call_unit", "effective_from": self.effective_from, "source_note": self.source_note,
            "model_note": self.model_note, "status": self.status, "created_by": self.created_by,
            "created_at": self.created_at, "retired_by": self.retired_by, "retired_at": self.retired_at,
            "retired_reason": self.retired_reason,
        }


def _row(row) -> PriceRow:
    return PriceRow(
        price_id=row["price_id"], provider=row["provider"], purpose=row["purpose"], currency=row["currency"],
        unit_price_micros=int(row["unit_price_micros"]), effective_from=parse_dt(row["effective_from"]),
        source_note=row["source_note"], model_note=row["model_note"], status=row["status"],
        created_by=row["created_by"], created_at=parse_dt(row["created_at"]), retired_by=row["retired_by"],
        retired_at=parse_dt(row["retired_at"]) if row["retired_at"] else None, retired_reason=row["retired_reason"],
    )


class PriceBook:
    """某一时刻读出来的全部**有效**价格，按（供应商, 用途）分组、按生效时间排好。只读，不缓存到进程外。"""

    def __init__(self, rows: list[PriceRow]) -> None:
        self._by_key: dict[tuple[str, str], list[PriceRow]] = {}
        for row in sorted(rows, key=lambda r: (r.effective_from, r.created_at)):
            if row.status == "active":
                self._by_key.setdefault((row.provider, row.purpose), []).append(row)

    def __bool__(self) -> bool:
        return bool(self._by_key)

    def price_for(self, provider: str, purpose: str, at: datetime) -> PriceRow | None:
        for key in ((provider, purpose), (provider, "*")):
            hit = None
            for row in self._by_key.get(key, ()):
                if row.effective_from <= at:
                    hit = row  # 已按生效时间升序：最后一条不晚于 at 的就是当时有效的那一条
                else:
                    break
            if hit is not None:
                return hit
        return None


class AdminPricing:
    def __init__(self, storage: JourneyStorage, audit: AuditLog, idempotency) -> None:
        self.storage = storage
        self.audit = audit
        self.idempotency = idempotency

    # ---- 读 ----
    def prices(self, *, include_retired: bool = True) -> list[PriceRow]:
        sql = "SELECT * FROM admin_provider_prices"
        if not include_retired:
            sql += " WHERE status = 'active'"
        with self.storage.connect() as conn:
            return [_row(r) for r in conn.execute(sql + " ORDER BY provider, purpose, effective_from DESC, created_at DESC")]

    def book(self) -> PriceBook:
        return PriceBook(self.prices(include_retired=False))

    def observed_scopes(self) -> list[dict[str, Any]]:
        """额度账里实际出现过的（供应商, 用途），给录价表单当候选——录价之前先看清楚账上到底记的是什么名字。"""
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT provider, purpose, COUNT(*) AS calls, MIN(created_at) AS first_at, MAX(created_at) AS last_at "
                                "FROM web_budget_reservations GROUP BY provider, purpose ORDER BY provider, purpose").fetchall()
        return [{"provider": r["provider"], "purpose": r["purpose"], "calls": int(r["calls"]),
                 "first_at": parse_dt(r["first_at"]), "last_at": parse_dt(r["last_at"])} for r in rows]

    # ---- 写（只追加）----
    def add(self, ctx: ActorContext, *, provider: str, purpose: str, currency: str, unit_price: str,
            effective_from: datetime, source_note: str, model_note: str | None) -> dict[str, Any]:
        provider = (provider or "").strip()
        purpose = (purpose or "").strip()
        if not _NAME_RE.match(provider):
            raise AdminAPIError.validation("供应商名要与额度账里记的一致（小写字母、数字、._-）。", field="provider")
        if purpose != "*" and not _NAME_RE.match(purpose):
            raise AdminAPIError.validation("用途要与额度账里记的一致；对这个供应商的全部用途生效就填 *。", field="purpose")
        if currency not in CURRENCIES:
            raise AdminAPIError.validation("币种只能是 CNY 或 USD；两种各算各的，不互相换算。", field="currency")
        micros = parse_price(unit_price)
        source = (source_note or "").strip()
        if len(source) < 4:
            raise AdminAPIError.validation("写清楚这个价格从哪来（价目页、合同或账单，至少 4 个字），它会进审计。", field="source_note")
        source = source[:300]
        model = (model_note or "").strip()[:120] or None
        if effective_from.tzinfo is None:
            raise AdminAPIError.validation("生效时间要带时区。", field="effective_from")
        effective = effective_from.astimezone(timezone.utc)
        payload = {"provider": provider, "purpose": purpose, "currency": currency, "unit_price_micros": micros,
                   "effective_from": iso(effective), "source_note": source, "model_note": model}

        def handler() -> dict[str, Any]:
            price_id = f"PR-{uuid.uuid4().hex[:12].upper()}"
            now = iso(utcnow())
            with unit_of_work(self.storage) as conn:
                try:
                    conn.execute(
                        "INSERT INTO admin_provider_prices (price_id, provider, purpose, currency, unit_price_micros, unit, "
                        "effective_from, source_note, model_note, status, created_by, created_at, operation_id) "
                        "VALUES (?, ?, ?, ?, ?, 'call_unit', ?, ?, ?, 'active', ?, ?, ?)",
                        (price_id, provider, purpose, currency, micros, iso(effective), source, model, ctx.staff_id, now,
                         ctx.operation_id))
                except sqlite3.IntegrityError as exc:
                    raise AdminAPIError(AdminErrorCode.idempotency_key_reused, "这个操作号已经录过一条价格了。", 409) from exc
                self.audit.record_in(conn, action="cost.price_add", status="succeeded", outcome=f"{currency}:{format_micros(micros)}",
                                     permission=Permission.COST_MANAGE.value, actor_staff_id=ctx.staff_id,
                                     actor_username=ctx.username, target_kind="price", target_id=price_id, reason=source,
                                     operation_id=ctx.operation_id, request_id=ctx.request_id,
                                     changes={**payload, "unit": "call_unit"})
                row = conn.execute("SELECT * FROM admin_provider_prices WHERE price_id = ?", (price_id,)).fetchone()
            return {"price": _row(row).as_dict(),
                    "note": "已录入。它只影响预占时刻不早于生效时间的调用；已经算过的估算不会被悄悄改写——每次查看都按价格历史现算。"}

        outcome = self.idempotency.run(user_id=ctx.staff_id, scope="admin:cost.price_add", key=ctx.operation_id,
                                       payload=payload, handler=handler)
        return {**outcome.response, "replayed": outcome.replayed}

    def retire(self, ctx: ActorContext, price_id: str, *, reason: str) -> dict[str, Any]:
        reason = require_reason(reason)

        def handler() -> dict[str, Any]:
            now = iso(utcnow())
            with unit_of_work(self.storage) as conn:
                row = conn.execute("SELECT * FROM admin_provider_prices WHERE price_id = ?", (price_id,)).fetchone()
                if row is None:
                    raise AdminAPIError.not_found("这条价格")
                if row["status"] != "active":
                    raise AdminAPIError(AdminErrorCode.conflict, "这条价格已经作废过了。", 409, details={"status": row["status"]})
                conn.execute("UPDATE admin_provider_prices SET status = 'retired', retired_by = ?, retired_at = ?, retired_reason = ? "
                             "WHERE price_id = ? AND status = 'active'", (ctx.staff_id, now, reason, price_id))
                self.audit.record_in(conn, action="cost.price_retire", status="succeeded", outcome="retired",
                                     permission=Permission.COST_MANAGE.value, actor_staff_id=ctx.staff_id,
                                     actor_username=ctx.username, target_kind="price", target_id=price_id, reason=reason,
                                     operation_id=ctx.operation_id, request_id=ctx.request_id,
                                     changes={"provider": row["provider"], "purpose": row["purpose"], "currency": row["currency"],
                                              "unit_price_micros": int(row["unit_price_micros"])})
                updated = conn.execute("SELECT * FROM admin_provider_prices WHERE price_id = ?", (price_id,)).fetchone()
            return {"price": _row(updated).as_dict(),
                    "note": "已作废：这条价格从此不参与估算，行本身保留，历史可查。"}

        outcome = self.idempotency.run(user_id=ctx.staff_id, scope="admin:cost.price_retire", key=ctx.operation_id,
                                       payload={"price_id": price_id, "reason": reason}, handler=handler)
        return {**outcome.response, "replayed": outcome.replayed}

    # ---- 估算 ----
    def annotate(self, rows: list[dict[str, Any]], book: PriceBook | None = None) -> list[dict[str, Any]]:
        """给逐条预占填上估算费用。没有适用价格的保持 None（未知），不填 0。"""
        book = book if book is not None else self.book()
        for row in rows:
            row.setdefault("billed_cost", None)  # 账单确认费用：没有账单导入之前一律未知
            if not book:  # 没有任何有效价格（没录过，或都已作废）：不逐条区分
                row.update(estimated_cost=None, cost_micros=None, cost_currency=None, price_id=None,
                           cost_state="unknown_no_price_table")
                continue
            counted = row.get("counted_units")
            price = book.price_for(row["provider"], row["purpose"], row["created_at"]) if counted else None
            if counted is None:
                row.update(estimated_cost=None, cost_micros=None, cost_currency=None, price_id=None, cost_state="in_flight")
            elif counted == 0:
                row.update(estimated_cost=None, cost_micros=None, cost_currency=None, price_id=None, cost_state="not_counted")
            elif price is None:
                row.update(estimated_cost=None, cost_micros=None, cost_currency=None, price_id=None, cost_state="unknown_no_price")
            else:
                state = "unconfirmed_estimate" if row["status"] in UNCONFIRMED_STATUSES else "estimated"
                micros = counted * price.unit_price_micros
                row.update(estimated_cost=format_micros(micros), cost_micros=micros, cost_currency=price.currency,
                           price_id=price.price_id, cost_state=state)
        return rows

    def estimate(self, *, start: date, end: date) -> dict[str, Any]:
        """按记账日（UTC，额度账的 accounting_window）估算一个日期区间。区间最长 31 天。"""
        if end < start:
            raise AdminAPIError.validation("结束日期不能早于开始日期。", field="to")
        if (end - start).days + 1 > MAX_WINDOW_DAYS:
            raise AdminAPIError.validation(f"一次最多估算 {MAX_WINDOW_DAYS} 天。", field="from")
        book = self.book()
        with self.storage.connect() as conn:
            rows = conn.execute(
                "SELECT operation_id, provider, purpose, status, reserved_units, actual_units, created_at "
                "FROM web_budget_reservations WHERE accounting_window BETWEEN ? AND ?",
                (start.isoformat(), end.isoformat())).fetchall()
        lines: dict[tuple[str, str], dict[str, Any]] = {}
        totals = {c: {"estimated_micros": 0, "unconfirmed_micros": 0} for c in CURRENCIES}
        for r in rows:
            key = (r["provider"], r["purpose"])
            line = lines.setdefault(key, {
                "provider": r["provider"], "purpose": r["purpose"], "calls": 0, "in_flight_calls": 0,
                "not_counted_calls": 0, "counted_units": 0, "priced_units": 0, "unpriced_units": 0,
                "by_currency": {}, "price_ids": set(),
            })
            line["calls"] += 1
            counted = counted_units(r["status"], r["reserved_units"], r["actual_units"])
            if counted is None:
                line["in_flight_calls"] += 1
                continue
            if counted == 0:
                line["not_counted_calls"] += 1
                continue
            line["counted_units"] += counted
            price = book.price_for(r["provider"], r["purpose"], parse_dt(r["created_at"]))
            if price is None:
                line["unpriced_units"] += counted
                continue
            line["priced_units"] += counted
            line["price_ids"].add(price.price_id)
            bucket = "unconfirmed_micros" if r["status"] in UNCONFIRMED_STATUSES else "estimated_micros"
            cost = counted * price.unit_price_micros
            per = line["by_currency"].setdefault(price.currency, {"estimated_micros": 0, "unconfirmed_micros": 0})
            per[bucket] += cost
            totals[price.currency][bucket] += cost
        out_lines = []
        for line in sorted(lines.values(), key=lambda item: (item["provider"], item["purpose"])):
            out_lines.append({
                **{k: v for k, v in line.items() if k not in ("by_currency", "price_ids")},
                "price_ids": sorted(line["price_ids"]),
                "by_currency": {c: {"estimated": format_micros(v["estimated_micros"]),
                                    "unconfirmed": format_micros(v["unconfirmed_micros"])}
                                for c, v in sorted(line["by_currency"].items())},
                # 这一行里有没录价的计入用量：整行就不是「完整估算」，界面要如实标出来
                "complete": line["unpriced_units"] == 0,
            })
        unpriced = sum(line["unpriced_units"] for line in out_lines)
        return {
            "window": {"from": start.isoformat(), "to": end.isoformat(), "days": (end - start).days + 1,
                       "basis": "按占用额度那天的记账日（UTC）"},
            "price_table_configured": bool(book),
            # 每个币种只在「这个窗口里真有按它计价的调用」时出现；没有就不出现，而不是给一个 0
            "currencies": {c: {"estimated": format_micros(v["estimated_micros"]),
                               "unconfirmed": format_micros(v["unconfirmed_micros"]),
                               "estimated_micros": v["estimated_micros"], "unconfirmed_micros": v["unconfirmed_micros"]}
                           for c, v in totals.items() if any(line["by_currency"].get(c) for line in out_lines)},
            "lines": out_lines,
            "unpriced_units": unpriced,
            "billed": None,
            "notes": {
                "estimated": "已结清调用 × 调用时有效的单价。",
                "unconfirmed": "结果未确认、或占着的额度过期了的调用 × 单价：很可能已发出、也可能已计费，没有确认，单列。",
                "unpriced": "没有适用价格的计入用量不计价，单独列出——不是免费。",
                "unit": UNIT_NOTE,
                "billed": BILLED_NOTE,
                "separation": "人民币与美元各算各的，不互相换算；与游戏星币没有兑换关系。",
            },
        }


def parse_day(text: str | None, default: date) -> date:
    if not text:
        return default
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise AdminAPIError.validation("日期写成 YYYY-MM-DD（UTC 记账日）。", field="date") from exc


def default_window(now: datetime | None = None) -> tuple[date, date]:
    today = (now or utcnow()).astimezone(timezone.utc).date()
    return today - timedelta(days=6), today
