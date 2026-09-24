"""经自建中转站的逐次调用回执：幂等导入与按日汇总（c84a 审查 ADM-COST-01，`docs/coordination/CR-ADMIN-RELAY-COST-2026-09-24.md`）。

**现在还没有真实来源**：中转还没有 PetSoul 专属的客户端，也没有逐次回执的只读接口
（PetSoul 生图配置复用的是 okeymind 客户端，旧 petsoul_image 已停用）。所以：
- 导入默认**关闭**：部署方显式设置 `PETSOUL_ADMIN_RELAY_CLIENTS`（PetSoul 专属客户端的 client_id，逗号分隔）才开放；
  白名单以外的客户端一律拒收并留下原因——**不把 okeymind 的历史当 PetSoul 消费**。代码不给默认白名单。
- 离线导入只是临时桥接；正式做法是后端用只读凭据按游标同步（接口清单见交接），入库走同一套幂等规则。
- 汇总分四块，缺什么就是缺什么：中转实测用量 / 按有来源价格估算 / 供应商账单确认 / 结果未确认·待对账；
  不填均价、不补 0、币种分开，和游戏星币没有任何关系。
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from ..web_platform.uow import unit_of_work
from .commands import ActorContext, require_reason
from .errors import AdminAPIError, AdminErrorCode
from .permissions import Permission

CLIENTS_ENV = "PETSOUL_ADMIN_RELAY_CLIENTS"
MAX_RECORDS = 5000
TEXT_FIELDS = ("relay_instance", "relay_event_id", "client_id", "project_id", "environment", "operation_id", "dispatch_attempt_id",
               "purpose", "provider", "endpoint", "requested_model", "reported_model", "provider_request_id", "usage_source",
               "price_version", "bill_reference", "currency")
TIME_FIELDS = ("started_at_utc", "completed_at_utc", "reconciled_at")
INT_FIELDS = ("http_status", "input_text_tokens", "input_image_tokens", "cached_tokens", "output_tokens", "images_returned")
AMOUNT_FIELDS = ("estimated_amount", "billed_amount")
REQUIRED = ("relay_instance", "relay_event_id", "client_id", "started_at_utc", "dispatch_outcome", "usage_present", "cost_state")
# 一次发送的结局（与额度账的 outcome 同一组词）与金额状态；认不出来的值整条拒收并写明原因，不猜
DISPATCH_OUTCOMES = ("succeeded", "failed", "not_sent", "unknown")
COST_STATES = ("estimated", "unpriced", "unknown")
ALL_FIELDS = TEXT_FIELDS + TIME_FIELDS + INT_FIELDS + AMOUNT_FIELDS + ("dispatch_outcome", "usage_present", "cost_state")

NOT_CONFIGURED = ("还没有配置 PetSoul 专属的中转客户端，导入处于关闭状态。要开放，请由部署方显式设置 PETSOUL_ADMIN_RELAY_CLIENTS"
                  "（专属客户端的编号，逗号分隔）。代码不给默认白名单：PetSoul 现在复用的是 okeymind 客户端，那份历史不能算成 PetSoul 的消费。")


def allowed_clients() -> tuple[str, ...]:
    return tuple(sorted({c.strip() for c in os.getenv(CLIENTS_ENV, "").split(",") if c.strip()}))


def _amount(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("金额要写成普通小数") from exc
    if amount < 0 or not amount.is_finite():
        raise ValueError("金额不能是负数")
    return format(amount.normalize(), "f")


def normalize(record: Any) -> dict[str, Any]:
    """把一条回执整理成入库的样子；不合规就抛 ValueError（整条拒收，原因写进导入问题）。"""
    if not isinstance(record, dict):
        raise ValueError("每一条回执都要是一个对象")
    unknown = sorted(set(record) - set(ALL_FIELDS))
    if unknown:
        raise ValueError(f"有不认识的字段：{'、'.join(unknown)}")
    missing = [field for field in REQUIRED if record.get(field) in (None, "")]
    if missing:
        raise ValueError(f"缺少必填字段：{'、'.join(missing)}")
    out: dict[str, Any] = {}
    for field in TEXT_FIELDS:
        value = record.get(field)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{field} 要是文本")
        out[field] = value.strip()[:300] if isinstance(value, str) and value.strip() else None
    for field in TIME_FIELDS:
        value = record.get(field)
        if value in (None, ""):
            out[field] = None
            continue
        try:
            moment = parse_dt(value) if isinstance(value, str) else None
        except ValueError:
            moment = None
        if moment is None or moment.tzinfo is None:
            raise ValueError(f"{field} 要是带时区的时间（UTC）")
        out[field] = iso(moment.astimezone(timezone.utc))
    for field in INT_FIELDS:
        value = record.get(field)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise ValueError(f"{field} 要是不小于 0 的整数")
        out[field] = value
    for field in AMOUNT_FIELDS:
        out[field] = _amount(record.get(field))
    if record["dispatch_outcome"] not in DISPATCH_OUTCOMES:
        raise ValueError(f"dispatch_outcome 只能是 {' / '.join(DISPATCH_OUTCOMES)}")
    if record["cost_state"] not in COST_STATES:
        raise ValueError(f"cost_state 只能是 {' / '.join(COST_STATES)}")
    if not isinstance(record["usage_present"], bool):
        raise ValueError("usage_present 要是 true / false")
    out.update(dispatch_outcome=record["dispatch_outcome"], cost_state=record["cost_state"], usage_present=record["usage_present"])
    if (out["estimated_amount"] or out["billed_amount"]) and not (out["currency"] or "").isalpha():
        raise ValueError("有金额就要写币种（例如 USD、CNY）")
    if out["currency"]:
        out["currency"] = out["currency"].upper()
    if out["cost_state"] == "estimated" and (out["estimated_amount"] is None or out["price_version"] is None):
        raise ValueError("写了「已估算」就要同时给估算金额与价格版本；没有来源的价格不能算估算")
    return out


def content_hash(normalized: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps({field: normalized.get(field) for field in ALL_FIELDS}, sort_keys=True,
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


class AdminRelayReceipts:
    def __init__(self, storage: JourneyStorage, commands, audit) -> None:
        self.storage = storage
        self.commands = commands
        self.audit = audit

    # ---- 幂等导入 ----
    def import_records(self, ctx: ActorContext, records: list[Any], *, source_note: str, file_name: str | None) -> dict[str, Any]:
        source_note = require_reason(source_note)
        clients = allowed_clients()
        if not clients:
            raise AdminAPIError(AdminErrorCode.not_configured, NOT_CONFIGURED, 503)
        if not records:
            raise AdminAPIError.validation("没有要导入的回执。", field="records")
        if len(records) > MAX_RECORDS:
            raise AdminAPIError.validation(f"一次最多导入 {MAX_RECORDS} 条，这次是 {len(records)} 条；请分批。", field="records")

        def handler() -> dict:
            now = iso(utcnow())
            batch_id = f"RB-{uuid.uuid4().hex[:16].upper()}"
            counts = {"received": len(records), "inserted": 0, "duplicates": 0, "conflicts": 0, "rejected": 0}
            issues: list[tuple] = []
            with unit_of_work(self.storage) as conn:
                for record in records:
                    key = (record.get("relay_instance"), record.get("relay_event_id")) if isinstance(record, dict) else (None, None)
                    try:
                        row = normalize(record)
                    except ValueError as exc:
                        counts["rejected"] += 1
                        issues.append((key[0], key[1], "rejected", str(exc), None, None))
                        continue
                    if row["client_id"] not in clients:
                        counts["rejected"] += 1
                        issues.append((row["relay_instance"], row["relay_event_id"], "rejected",
                                       f"客户端 {row['client_id']} 不在 PetSoul 专属白名单里（不把别的项目的调用算成 PetSoul 的消费）", None, None))
                        continue
                    digest = content_hash(row)
                    existing = conn.execute("SELECT content_sha256 FROM admin_relay_receipts WHERE relay_instance = ? AND relay_event_id = ?",
                                            (row["relay_instance"], row["relay_event_id"])).fetchone()
                    if existing is None:
                        columns = ALL_FIELDS + ("content_sha256", "import_batch_id", "imported_at")
                        values = [int(row[f]) if f == "usage_present" else row[f] for f in ALL_FIELDS] + [digest, batch_id, now]
                        conn.execute(f"INSERT INTO admin_relay_receipts ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})", values)
                        counts["inserted"] += 1
                    elif existing["content_sha256"] == digest:
                        counts["duplicates"] += 1
                    else:
                        counts["conflicts"] += 1
                        issues.append((row["relay_instance"], row["relay_event_id"], "conflict",
                                       "同一条回执（同一个中转实例 + 事件号）内容和已入库的不一样：保留原来的，不覆盖，请向中转核对", existing["content_sha256"], digest))
                for relay_instance, relay_event_id, kind, reason, old, new in issues:
                    conn.execute("INSERT INTO admin_relay_import_issues (issue_id, batch_id, relay_instance, relay_event_id, kind, reason, "
                                 "existing_sha256, incoming_sha256, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                 (f"RI-{uuid.uuid4().hex[:16].upper()}", batch_id, relay_instance, relay_event_id, kind, reason, old, new, now))
                conn.execute("INSERT INTO admin_relay_import_batches (batch_id, staff_id, source_note, file_name, received, inserted, duplicates, "
                             "conflicts, rejected, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (batch_id, ctx.staff_id, source_note, file_name, counts["received"], counts["inserted"], counts["duplicates"],
                              counts["conflicts"], counts["rejected"], now))
                self.audit.record_in(conn, status="succeeded", outcome=f"inserted:{counts['inserted']}", changes={**counts, "batch_id": batch_id},
                                     action="cost.relay_import", permission=Permission.COST_MANAGE.value, actor_staff_id=ctx.staff_id,
                                     actor_username=ctx.username, target_kind="relay_import", target_id=batch_id, reason=source_note,
                                     operation_id=ctx.operation_id, request_id=ctx.request_id)
            return {"batch_id": batch_id, **counts,
                    "note": "重复的回执不会记两次；同号内容不一样的保留原来的并记成冲突；被拒的写明了原因。"}

        digest = hashlib.sha256(json.dumps(records, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
        # 同一个操作号重放：回第一次的结果；同号换了内容：由幂等存储按载荷摘要拒绝
        return self.commands.run(ctx, "cost.relay_import", {"records_sha256": digest, "count": len(records), "file_name": file_name,
                                                            "source_note": source_note}, handler)

    # ---- 按日汇总：四块各算各的 ----
    def consumption(self, *, days: int = 30, now: datetime | None = None) -> dict[str, Any]:
        now = now or utcnow()
        since = (now.astimezone(timezone.utc).date() - timedelta(days=days - 1)).isoformat()
        clients = allowed_clients()
        try:
            with self.storage.connect() as conn:
                rows = conn.execute("SELECT r.*, EXISTS (SELECT 1 FROM web_budget_reservations b WHERE b.operation_id = r.operation_id) AS attributed "
                                    "FROM admin_relay_receipts r WHERE substr(r.started_at_utc, 1, 10) >= ? ORDER BY r.started_at_utc",
                                    (since,)).fetchall()
                totals = conn.execute("SELECT COUNT(*) AS n, SUM(CASE WHEN operation_id IS NULL OR NOT EXISTS (SELECT 1 FROM web_budget_reservations b "
                                      "WHERE b.operation_id = admin_relay_receipts.operation_id) THEN 1 ELSE 0 END) AS unattributed, "
                                      "SUM(CASE WHEN cost_state != 'estimated' THEN 1 ELSE 0 END) AS unpriced, "
                                      "SUM(CASE WHEN dispatch_outcome = 'unknown' THEN 1 ELSE 0 END) AS unknown_outcome, "
                                      "SUM(CASE WHEN usage_present = 0 THEN 1 ELSE 0 END) AS no_usage, "
                                      "SUM(CASE WHEN billed_amount IS NOT NULL THEN 1 ELSE 0 END) AS billed FROM admin_relay_receipts").fetchone()
                last = conn.execute("SELECT created_at, inserted, received FROM admin_relay_import_batches ORDER BY created_at DESC LIMIT 1").fetchone()
                batches = conn.execute("SELECT COUNT(*) FROM admin_relay_import_batches").fetchone()[0]
                issues = {r["kind"]: int(r["n"]) for r in conn.execute("SELECT kind, COUNT(*) AS n FROM admin_relay_import_issues GROUP BY kind")}
        except sqlite3.OperationalError:
            return {"available": False, "note": "这个库里还没有中转回执的表，查不了（不等于没有）。"}

        by_day: dict[tuple[str, str, str], dict[str, Any]] = {}
        for r in rows:
            model = r["reported_model"] or r["requested_model"]
            key = (r["started_at_utc"][:10], r["purpose"] or "", model or "")
            cell = by_day.setdefault(key, {
                "day": key[0], "purpose": r["purpose"], "model": model, "model_confirmed": True,
                "measured": {"dispatches": 0, "succeeded": 0, "images": 0, "input_text_tokens": 0, "input_image_tokens": 0,
                             "cached_tokens": 0, "output_tokens": 0, "with_usage": 0},
                "estimated": {}, "unpriced": 0, "billed": {}, "unbilled": 0, "pending": 0, "unattributed": 0})
            if model and not r["reported_model"]:
                cell["model_confirmed"] = False  # 只有请求时写的模型，供应商没确认
            m = cell["measured"]
            m["dispatches"] += 1
            m["succeeded"] += 1 if r["dispatch_outcome"] == "succeeded" else 0
            m["with_usage"] += 1 if r["usage_present"] else 0
            for field, target in (("images_returned", "images"), ("input_text_tokens", "input_text_tokens"),
                                  ("input_image_tokens", "input_image_tokens"), ("cached_tokens", "cached_tokens"), ("output_tokens", "output_tokens")):
                m[target] += int(r[field] or 0)
            if r["cost_state"] == "estimated" and r["estimated_amount"] is not None:
                currency = r["currency"] or "?"
                cell["estimated"][currency] = str(Decimal(cell["estimated"].get(currency, "0")) + Decimal(r["estimated_amount"]))
            else:
                cell["unpriced"] += 1
            if r["billed_amount"] is not None:
                currency = r["currency"] or "?"
                cell["billed"][currency] = str(Decimal(cell["billed"].get(currency, "0")) + Decimal(r["billed_amount"]))
            else:
                cell["unbilled"] += 1
            if r["dispatch_outcome"] == "unknown" or not r["usage_present"] or r["cost_state"] == "unknown":
                cell["pending"] += 1
            if not r["attributed"]:
                cell["unattributed"] += 1
        return {
            "available": True,
            "capability": {"enabled": bool(clients), "clients": list(clients), "note": None if clients else NOT_CONFIGURED},
            "sync": {"batches": int(batches), "last_import_at": parse_dt(last["created_at"]) if last else None,
                     "receipts": int(totals["n"] or 0), "unattributed": int(totals["unattributed"] or 0), "unpriced": int(totals["unpriced"] or 0),
                     "unknown_outcome": int(totals["unknown_outcome"] or 0), "no_usage": int(totals["no_usage"] or 0),
                     "billed": int(totals["billed"] or 0), "conflicts": issues.get("conflict", 0), "rejected": issues.get("rejected", 0)},
            "days": sorted(by_day.values(), key=lambda c: (c["day"], c["purpose"] or "", c["model"] or ""), reverse=True),
            "since": since,
            "notes": {
                "measured": "中转自己记下的用量（发了几次、成了几次、返回几张图、各类 token）。它是用量事实，不是钱。",
                "estimated": "只有带价格版本的回执才算估算；没有来源的价格不算，单列成「未定价」。",
                "billed": "只有导入了供应商账单的才有确认金额；没有就是未知，不补 0。",
                "pending": "结果未确认、没有用量、金额未知的：待对账，不当成失败，也不当成没发送。",
                "attributed": "按业务操作号对上后台额度账的才算「已归属」；对不上的单列，不凭相近时间猜。",
            },
        }
