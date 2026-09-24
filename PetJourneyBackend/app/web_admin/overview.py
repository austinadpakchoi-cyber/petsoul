"""运营首页与两本独立账目的**只读**汇总。

每个数字都带 `source`（它是从哪张表、哪个窗口算出来的）。拿不到来源的指标 `available=False`、
`value=None`，界面显示"未接入"——**不填 0、不填随机数**。"0 元"和"不知道多少钱"是两件事，
后者一律写成 unknown。

两本账在这里就是两个互不相干的结构，没有任何换算函数：
- 游戏账：`economy_transactions` / `pet_wallets.travel_coin`，单位是星币；
- 平台调用账：`web_budget_counters` / `web_budget_reservations`，单位是**调用次数**。
  金额只来自员工录入的价格表（迁移 1540，只追加，带来源与生效时间；估算见 pricing.py）：
  没有适用价格的就是未知，不显示 0 元；账单确认费用要等账单导入，在那之前一律未知。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from ..web_platform import WEB_BACKEND_VERSION
from ..web_platform.lease import lease_status
from .metering import COUNTED_NOTE, COUNTED_UNITS_SQL, counted_units

ADMIN_GRANT_SOURCES = ("admin.compensation", "admin.compensation.batch")  # 可以被冲正的两种来源

# 价格不在代码里：由员工在价格表（迁移 1540，只追加）里带来源与生效时间录入，估算见 pricing.py。
# 没录价就是未知，不是 0。


@dataclass(frozen=True, slots=True)
class Metric:
    key: str
    label: str
    value: int | None
    available: bool
    source: str
    window: str | None = None
    note: str | None = None


def metric(key: str, label: str, value: int | None, source: str, *, window: str | None = None, note: str | None = None) -> Metric:
    return Metric(key=key, label=label, value=value, available=value is not None, source=source, window=window, note=note)


class AdminOverview:
    def __init__(self, storage: JourneyStorage, web, settings, *, pricing=None, economy_checks=None) -> None:
        self.storage = storage
        self.web = web
        self.settings = settings
        self.pricing = pricing                # 价格表与估算（没接就一律未知）
        self.economy_checks = economy_checks  # 游戏经济只读对账（没接就「未接入」）

    # ---- 首页 ----
    def environment(self) -> dict[str, Any]:
        return {
            "environment": getattr(self.settings, "web_environment", "dev"),
            "backend_version": WEB_BACKEND_VERSION,
            "server_time": utcnow(),
            "database": str(getattr(self.settings, "database_path", "")),
            "providers_enabled": bool(getattr(self.settings, "web_providers_enabled", False)),
            "world_runner": getattr(self.settings, "web_world_runner", "embedded"),
            "world_tick_seconds": getattr(self.settings, "web_world_tick_seconds", 0),
            "brain_mode": getattr(self.settings, "web_brain_mode", "off"),
            "heartbeat_mode": getattr(self.settings, "web_web_heartbeat_mode", None) or getattr(self.settings, "web_heartbeat_mode", None),
        }

    def metrics(self, now: datetime | None = None) -> list[Metric]:
        now = now or utcnow()
        day_start = datetime.combine(now.astimezone(timezone.utc).date(), datetime.min.time(), tzinfo=timezone.utc)
        with self.storage.connect() as conn:
            def count(sql: str, params: tuple = ()) -> int:
                return int(conn.execute(sql, params).fetchone()[0])

            registered = count("SELECT COUNT(*) FROM users")
            new_today = count("SELECT COUNT(*) FROM users WHERE created_at >= ?", (iso(day_start),))
            # "活跃"只认一个来源：web_user_prefs.last_active_at（读会话时最多每 10 分钟写一次）。
            # 它不是页面轮询次数，也不是请求数。
            active_24h = count("SELECT COUNT(*) FROM web_user_prefs WHERE last_active_at >= ?", (iso(now - timedelta(hours=24)),))
            households = count("SELECT COUNT(*) FROM web_households")
            pets = count("SELECT COUNT(*) FROM web_household_pets")  # 已被某个家庭照顾的宠物；待领养居民不算
            moved_in = count("SELECT COUNT(*) FROM web_homes WHERE activated_at IS NOT NULL")
            frozen = count("SELECT COUNT(*) FROM admin_account_flags WHERE status = 'frozen'")
            photos_pending = count("SELECT COUNT(*) FROM web_illustrations WHERE status = 'processing'")
            photos_failed = count("SELECT COUNT(*) FROM web_illustrations WHERE status = 'failed'")
            tasks_queued = count("SELECT COUNT(*) FROM web_tasks WHERE status = 'queued'")
            tasks_failed = count("SELECT COUNT(*) FROM web_tasks WHERE status = 'failed'")
            tasks_overdue = count("SELECT COUNT(*) FROM web_tasks WHERE status = 'queued' AND run_after <= ?", (iso(now),))
            open_reports = count(
                "SELECT COUNT(*) FROM web_reports r WHERE NOT EXISTS ("
                "SELECT 1 FROM admin_report_actions a WHERE a.target_kind = r.target_kind AND a.target_id = r.target_id "
                "AND a.created_at >= r.created_at)"
            )
            unknown_calls = count("SELECT COUNT(*) FROM web_budget_reservations WHERE status IN ('unknown', 'expired')")
            inflight_calls = count("SELECT COUNT(*) FROM web_budget_reservations WHERE status = 'reserved'")
            # 宠物运行（第九批）：与「宠物运行」页同一口径（web_admin/pet_runtime.py）
            paused = count("SELECT COUNT(*) FROM web_entity_runtime WHERE maintenance = 1")
            stuck = count("SELECT COUNT(*) FROM web_entity_runtime WHERE decision_operation_id IS NOT NULL "
                          "AND decision_started_at <= ?", (iso(now - timedelta(minutes=10)),))
            from .lanes import configured_from_settings

            # 按配置该跑的时候才算「过点」——执行者失联时照样算（那正是要暴露的故障）；按配置关着时不算，写明原因
            tick = float(getattr(self.settings, "web_world_tick_seconds", 30.0))
            late = (count("SELECT COUNT(*) FROM web_entity_runtime WHERE maintenance = 0 AND next_check_at IS NOT NULL "
                          "AND next_check_at <= ?", (iso(now - timedelta(seconds=max(120.0, 3 * tick))),))
                    if configured_from_settings(self.settings) else None)
        return [
            metric("users.registered", "注册账号", registered, "users"),
            metric("users.new_today", "今天新注册", new_today, "users.created_at", window="UTC 当日"),
            metric("users.active_24h", "24 小时内来过", active_24h, "web_user_prefs.last_active_at", window="最近 24 小时",
                   note="来源是会话读取时的活跃标记（每 10 分钟最多写一次），不是页面请求数。"),
            metric("households.total", "家庭", households, "web_households"),
            metric("pets.total", "家庭在养宠物", pets, "web_household_pets"),
            metric("homes.moved_in", "已入住的家", moved_in, "web_homes.activated_at"),
            metric("accounts.frozen", "已冻结账号", frozen, "admin_account_flags"),
            metric("photos.processing", "照片处理中", photos_pending, "web_illustrations"),
            metric("photos.failed", "照片没画成", photos_failed, "web_illustrations"),
            metric("tasks.queued", "任务排队中", tasks_queued, "web_tasks"),
            metric("tasks.overdue", "任务已到期未执行", tasks_overdue, "web_tasks.run_after"),
            metric("tasks.failed", "任务失败", tasks_failed, "web_tasks"),
            metric("reports.open", "待处理举报", open_reports, "web_reports × admin_report_actions"),
            metric("calls.unknown", "结果未确认的调用", unknown_calls, "web_budget_reservations",
                   note="结果未确认、或占着的额度过期了：很可能已经发出去，只是没等到结果。不是失败，也不是没发送。"),
            metric("calls.inflight", "在途调用", inflight_calls, "web_budget_reservations"),
            metric("pets.paused", "被暂停的宠物", paused, "web_entity_runtime.maintenance",
                   note="后台暂停了它们的自主运行（不做新的生活决定）。谁、为什么，见「宠物运行」。"),
            metric("pets.thinking_stuck", "思考超过 10 分钟没结束", stuck, "web_entity_runtime.decision_started_at"),
            metric("pets.heartbeat_late", "心跳过了该看的时间还没看", late, "web_entity_runtime.next_check_at",
                   note=None if late is not None else "世界推进按配置关着，这一项不算（不是 0）。"),
            metric("economy.mismatch", "账目对不上的宠物",
                   self.economy_checks.run(now)["pets_with_errors"] if self.economy_checks is not None else None,
                   "pet_wallets × economy_transactions",
                   # 判据与 PetEconomyEngine.rebuild_derived_state 同口径（余额＝从 0 起全部 committed 流水之和）
                   note="余额应当等于从 0 开始把所有已入账的流水加起来（和游戏自己重建钱包的算法一样）；"
                        "另外查流水前后接不接得上、每一条算得对不对、有没有负余额。只报不修。"),
        ]

    def runtime_health(self) -> dict[str, Any]:
        from .lanes import configured_from_settings, lane_state

        configured = configured_from_settings(self.settings)
        lanes = {}
        for name, ticker in (("world", getattr(self.web, "ticker", None)), ("cognition", getattr(self.web, "cognition", None))):
            lease = lease_status(self.storage, name) or {}
            lanes[name] = {
                "runner": getattr(self.settings, "web_world_runner", "embedded") if getattr(self.settings, "web_world_tick_seconds", 0) > 0 else "off",
                "running_here": bool(getattr(ticker, "running", False)),
                "lease_alive": bool(lease.get("alive")), "holder_role": lease.get("holder_role"), "pid": lease.get("pid"),
                "state": lane_state(configured, bool(lease.get("alive"))),  # 按配置判：关着 / 在岗 / 失联（lanes.py）
                "last_tick_at": lease.get("last_tick_at"), "last_ok_at": lease.get("last_ok_at"),
                "last_error": lease.get("last_error"), "ticks": int(lease.get("ticks") or 0),
            }
        tasks = self.web.illustrations.tasks.task_health() if getattr(self.web, "illustrations", None) is not None else {}
        outbox = self.web.journeys.outbox.stats(utcnow()) if getattr(self.web, "journeys", None) is not None else {}
        return {"lanes": lanes, "tasks": tasks, "outbox": {name: counts for name, counts in sorted(outbox.items())},
                "due_lag_seconds": self.web.journeys.due_lag_seconds() if getattr(self.web, "journeys", None) is not None else None}

    # ---- 平台调用账（单位：调用次数；金额未配置价格 → 未知）----
    def provider_usage(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or utcnow()
        day = now.astimezone(timezone.utc).date().isoformat()
        with self.storage.connect() as conn:
            rows = conn.execute(
                "SELECT scope_key, used_units, inflight_units FROM web_budget_counters WHERE window_key = ? AND scope_key LIKE 'usage:%'",
                (day,)).fetchall()
            by_status = {r["status"]: int(r["n"]) for r in conn.execute(
                "SELECT status, COUNT(*) AS n FROM web_budget_reservations WHERE accounting_window = ? GROUP BY status", (day,))}
            # 计量按 UTC 日切窗；但"结果未确认"要一直看得到，不能因为跨了一天就从页面上消失
            # （运营首页的 calls.unknown 数的就是全部时间）。两个口径分开给，不混成一个数。
            all_time = {r["status"]: int(r["n"]) for r in conn.execute(
                "SELECT status, COUNT(*) AS n FROM web_budget_reservations GROUP BY status")}
            unsettled = [dict(r) for r in conn.execute(
                "SELECT operation_id, provider, purpose, status, actual_units, reserved_units, accounting_window, created_at "
                "FROM web_budget_reservations WHERE status IN ('reserved', 'unknown', 'expired') ORDER BY created_at DESC LIMIT 50")]
            # units＝与计数器同口径的"计入已用"（见 metering.py）：released 计 0、在途不计。原始列里的数不能直接加。
            models = conn.execute(
                f"SELECT provider, purpose, status, COUNT(*) AS calls, SUM({COUNTED_UNITS_SQL}) AS units "
                "FROM web_budget_reservations WHERE accounting_window = ? GROUP BY provider, purpose, status", (day,)).fetchall()
            health = {r["provider"]: dict(r) for r in conn.execute("SELECT * FROM web_provider_health").fetchall()}
        today = now.astimezone(timezone.utc).date()
        estimate = self.pricing.estimate(start=today, end=today) if self.pricing is not None else None
        priced = {(line["provider"], line["purpose"]): line for line in (estimate or {}).get("lines", [])}
        lines = []
        for row in rows:
            _, _, rest = row["scope_key"].partition("usage:")
            provider, _, purpose = rest.partition(":")
            hit = priced.get((provider, purpose))
            if estimate is None or not estimate["price_table_configured"]:
                state, cost = "unknown_no_price_table", None
            elif hit is None or hit["counted_units"] == 0:
                state, cost = "not_counted", None
            elif hit["priced_units"] == 0:
                state, cost = "unknown_no_price", None
            else:
                state, cost = ("estimated" if hit["complete"] else "partial"), hit["by_currency"]
            lines.append({
                "provider": provider, "purpose": purpose or "(未标注用途)",
                "used_units": int(row["used_units"]), "inflight_units": int(row["inflight_units"]),
                # 金额：没有适用价格就是未知，**不放 0**。有价时按币种分开给，不相加、不换算。
                "estimated_cost": cost, "billed_cost": None, "currency": None, "cost_state": state,
                "unpriced_units": hit["unpriced_units"] if hit else None,
            })
        return {
            "accounting_window": day,
            "unit": "调用次数（provider call unit）",
            "lines": sorted(lines, key=lambda item: (item["provider"], item["purpose"])),
            "reservations_by_status": by_status,
            "reservations_all_time_by_status": all_time,
            "unsettled": [{**row, "created_at": parse_dt(row["created_at"]),
                           "counted_units": counted_units(row["status"], row["reserved_units"], row["actual_units"])}
                          for row in unsettled],
            "counted_note": COUNTED_NOTE,
            "by_provider_purpose": [dict(r) for r in models],
            "provider_health": health,
            "price_table_configured": bool(estimate and estimate["price_table_configured"]),
            "window_note": "上面的用量按 UTC 日切窗，只算今天；"
                           "『结果未确认 / 在途』一栏是全部时间，跨天也不会从页面上消失。",
            "cost_note": ("估算费用＝计入用量 × 调用时有效的单价（价格表只追加，带来源与生效时间）；没有适用价格的是未知，不显示为 0。"
                          "账单确认费用要等账单导入，现在一律未知。调用次数与游戏星币没有兑换关系。"
                          if estimate and estimate["price_table_configured"] else
                          "价格表里没有有效的价格（没录过，或录过的都已作废），所以估算费用与账单确认费用都是未知，不显示为 0。"
                          "调用次数与游戏星币没有兑换关系。"),
        }

    # ---- 单只宠物的平台调用账（单位：调用次数）；与它的星币账分开给，两边没有任何换算 ----
    def pet_calls(self, pet_id: str, *, limit: int = 50, now: datetime | None = None) -> dict[str, Any]:
        """归集口径：`web_budget_reservations.subject_scope = 'pet:<id>'`。所有按宠物发起的模型与生图调用
        （`web_agent/brain_wiring.py`）都记在这个主体上；以家庭或全局为主体的调用不在这里。

        今日用量直接读账本自己的计数器（`web_budget_counters` 里 `pet:<id>:` 开头的那几层），
        不在这里按行重算——重算就要复制一遍"unknown 按已发出次数计、expired 按预占计"的规则，那是 budget.py 的事。
        只有配置了每宠上限的那几层才有计数器；没有的层如实缺席，不补 0。
        """
        now = now or utcnow()
        day = now.astimezone(timezone.utc).date().isoformat()
        subject = f"pet:{pet_id}"
        prefix = f"pet:{pet_id}:"
        with self.storage.connect() as conn:
            # 前缀用 substr 精确比较，不用 LIKE：宠物号里的下划线在 LIKE 里是通配符。
            counters = [dict(r) for r in conn.execute(
                "SELECT scope_key, used_units, inflight_units FROM web_budget_counters "
                "WHERE window_key = ? AND substr(scope_key, 1, ?) = ? ORDER BY scope_key", (day, len(prefix), prefix))]
            by_status = {r["status"]: int(r["n"]) for r in conn.execute(
                "SELECT status, COUNT(*) AS n FROM web_budget_reservations WHERE subject_scope = ? GROUP BY status", (subject,))}
            rows = conn.execute(
                "SELECT operation_id, provider, purpose, status, outcome, reserved_units, actual_units, accounting_window, "
                "created_at, settled_at FROM web_budget_reservations WHERE subject_scope = ? ORDER BY created_at DESC LIMIT ?",
                (subject, max(1, min(200, limit)))).fetchall()
        view = {
            "pet_id": pet_id,
            "subject_scope": subject,
            "unit": "调用次数（provider call unit）",
            "accounting_window": day,
            "counters_today": [{"scope_key": c["scope_key"], "used_units": int(c["used_units"]),
                                "inflight_units": int(c["inflight_units"])} for c in counters],
            "reservations_by_status": by_status,
            "reservations": [{
                "operation_id": r["operation_id"], "provider": r["provider"], "purpose": r["purpose"],
                "status": r["status"], "outcome": r["outcome"], "reserved_units": int(r["reserved_units"]),
                "actual_units": int(r["actual_units"]) if r["actual_units"] is not None else None,
                "counted_units": counted_units(r["status"], r["reserved_units"], r["actual_units"]),
                "accounting_window": r["accounting_window"], "created_at": parse_dt(r["created_at"]),
                "settled_at": parse_dt(r["settled_at"]) if r["settled_at"] else None,
            } for r in rows],
            "scope_note": "只含记在这只宠物名下的调用；记在家庭或全平台名下的不在这里。"
                          "今日用量只列配置了每宠上限的那几层，没有计数器的层不显示，也不补 0。",
            "cost_note": "单位是调用次数。估算＝计入用量 × 调用时有效的单价；没有适用价格就是未知，不显示为 0。"
                         "账单确认费用要等账单导入。与游戏星币没有兑换关系。",
            "counted_note": COUNTED_NOTE,
        }
        # 金额：逐条按价格历史现算；没有有效价格或没有适用价格就是未知（None），不放 0。
        book = self.pricing.book() if self.pricing is not None else None
        if self.pricing is not None:
            self.pricing.annotate(view["reservations"], book)
        else:
            for row in view["reservations"]:
                row.update(estimated_cost=None, billed_cost=None, cost_state="unknown_no_price_table")
        view["price_table_configured"] = bool(book)
        return view

    # ---- 游戏账（单位：星币）----
    def economy_ledger(self, *, pet_id: str | None = None, user_id: str | None = None, limit: int = 50) -> dict[str, Any]:
        where, params = [], []
        if pet_id:
            where.append("t.pet_id = ?")
            params.append(pet_id)
        if user_id:
            from .directory import PETS_OF_USER  # 同一份"这位用户有哪些宠物"的口径
            where.append(f"t.pet_id IN ({PETS_OF_USER})")
            params.append(user_id)
        clause = f" WHERE {' AND '.join(where)}" if where else ""
        with self.storage.connect() as conn:
            rows = conn.execute(
                f"SELECT t.tx_id, t.pet_id, t.type, t.idempotency_key, t.amounts_json, t.reason, t.operator, t.source, t.status, t.created_at "
                f"FROM economy_transactions t{clause} ORDER BY t.created_at DESC LIMIT ?", [*params, max(1, min(200, limit))]).fetchall()
            wallets = conn.execute(
                "SELECT pet_id, travel_coin, updated_at FROM pet_wallets" + (" WHERE pet_id = ?" if pet_id else "") + " ORDER BY updated_at DESC LIMIT 50",
                (pet_id,) if pet_id else ()).fetchall()
            # 哪些后台补偿已经被冲正（冲正流水的幂等键是 admin:reverse:<原流水号>）
            keys = [f"admin:reverse:{r['tx_id']}" for r in rows if r["source"] in ADMIN_GRANT_SOURCES]
            reversed_by = ({k.split(":", 2)[2]: tx for k, tx in conn.execute(
                f"SELECT idempotency_key, tx_id FROM economy_transactions WHERE idempotency_key IN ({','.join('?' for _ in keys)})",
                keys).fetchall()} if keys else {})
        import json as _json
        return {
            "currency": "星币（游戏内资产）",
            "currency_code": "travel_coin",  # 机器可读：游戏币，不是人民币/美元（显示用上面那句）
            "separation_note": "星币只在游戏账本里流动；平台 API 调用记在另一本账，两者没有兑换关系。",
            "reason_note": "「说明」一栏就是玩家在星球银行卡上看到的文字；后台补偿与冲正的内部原因只在审计里。",
            "transactions": [{
                "tx_id": r["tx_id"], "pet_id": r["pet_id"], "type": r["type"], "idempotency_key": r["idempotency_key"],
                "travel_coin": int((_json.loads(r["amounts_json"]) or {}).get("travel_coin", 0)),
                "reason": r["reason"], "operator": r["operator"], "source": r["source"], "status": r["status"],
                "created_at": parse_dt(r["created_at"]),
                # 后台补偿：能不能冲正、是不是已经被冲正；冲正流水：它冲的是哪一笔
                "admin_compensation": r["source"] in ADMIN_GRANT_SOURCES,
                "reversed_by": reversed_by.get(r["tx_id"]),
                "reversal_of": (r["idempotency_key"].split(":", 2)[2]
                                if (r["idempotency_key"] or "").startswith("admin:reverse:") else None),
            } for r in rows],
            "wallets": [{"pet_id": r["pet_id"], "travel_coin": int(r["travel_coin"]),
                         "updated_at": parse_dt(r["updated_at"]) if r["updated_at"] else None} for r in wallets],
        }

    # ---- 一位用户名下各只宠物的两本账汇总（两段各自要自己的权限，路由层决定给哪几段）----
    def user_ledger_summary(self, user_id: str, *, economy: bool, calls: bool) -> dict[str, Any]:
        import json as _json

        from .directory import PETS_OF_USER  # 同一份"这位用户有哪些宠物"的口径
        admin_sources = ("admin.compensation", "admin.compensation.batch")
        book = self.pricing.book() if (calls and self.pricing is not None) else None
        pets_out = []
        with self.storage.connect() as conn:
            pets = conn.execute(f"SELECT pet_id, name FROM pets WHERE pet_id IN ({PETS_OF_USER}) ORDER BY name, pet_id",
                                (user_id,)).fetchall()
            for pet in pets:
                item: dict[str, Any] = {"pet_id": pet["pet_id"], "name": pet["name"]}
                if economy:
                    wallet = conn.execute("SELECT travel_coin, updated_at FROM pet_wallets WHERE pet_id = ?", (pet["pet_id"],)).fetchone()
                    entries = conn.execute("SELECT amounts_json, source, created_at FROM economy_transactions "
                                           "WHERE pet_id = ? AND status = 'committed'", (pet["pet_id"],)).fetchall()
                    admin = [e for e in entries if e["source"] in admin_sources]
                    item["economy"] = {
                        "balance": int(wallet["travel_coin"]) if wallet else None,  # 没有钱包行就是 None，不是 0
                        "entries": len(entries),
                        "last_entry_at": max((parse_dt(e["created_at"]) for e in entries), default=None),
                        "admin_compensations": len(admin),
                        "admin_compensated_coins": sum(int((_json.loads(e["amounts_json"]) or {}).get("travel_coin") or 0) for e in admin),
                    }
                if calls:
                    rows = [dict(r) for r in conn.execute(
                        "SELECT operation_id, provider, purpose, status, reserved_units, actual_units, created_at "
                        "FROM web_budget_reservations WHERE subject_scope = ?", (f"pet:{pet['pet_id']}",))]
                    by_status: dict[str, int] = {}
                    counted_total = 0
                    for row in rows:
                        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
                        row["counted_units"] = counted_units(row["status"], row["reserved_units"], row["actual_units"])
                        row["created_at"] = parse_dt(row["created_at"])
                        counted_total += row["counted_units"] or 0
                    costs: dict[str, dict[str, int]] = {}
                    unpriced = 0
                    if self.pricing is not None and book:
                        self.pricing.annotate(rows, book)
                        for row in rows:
                            if row["cost_state"] == "unknown_no_price":
                                unpriced += row["counted_units"] or 0
                            elif row["cost_micros"] is not None:
                                bucket = "unconfirmed" if row["cost_state"] == "unconfirmed_estimate" else "estimated"
                                costs.setdefault(row["cost_currency"], {"estimated": 0, "unconfirmed": 0})[bucket] += row["cost_micros"]
                    if not book:
                        state = "unknown_no_price_table"
                    elif costs:
                        state = "partial" if unpriced else "estimated"
                    else:
                        state = "unknown_no_price" if unpriced else "not_counted"
                    from .pricing import format_micros
                    item["calls"] = {
                        "reservations_by_status": by_status,
                        "counted_units": counted_total,
                        "estimated_cost": {c: {"estimated": format_micros(v["estimated"]), "unconfirmed": format_micros(v["unconfirmed"])}
                                           for c, v in sorted(costs.items())} or None,
                        "unpriced_units": unpriced if book else None,
                        "cost_state": state,
                    }
                pets_out.append(item)
        return {
            "user_id": user_id,
            "sections": {"economy": economy, "calls": calls},
            "pets": pets_out,
            "notes": {
                "economy": "星币余额与流水条数；「后台补偿」只数后台的单笔补偿与批量补偿。",
                "calls": "只含记在这只宠物名下的调用。估算按价格历史现算，没有适用价格的计入用量单列，不是免费；"
                         "人民币与美元分开，不相加、不换算。",
                "separation": "两本账各记各的：星币是游戏资产，调用次数与费用是平台成本，两者没有兑换关系。",
            },
        }

    # ---- 举报队列 ----
    def reports(self, *, only_open: bool = True, limit: int = 50) -> list[dict[str, Any]]:
        from .moderation import active_claim  # 当前认领（按被举报的内容记；过期的不算）
        now = utcnow()
        with self.storage.connect() as conn:
            rows = conn.execute(
                "SELECT r.report_id, r.reporter_user_id, r.target_kind, r.target_id, r.reason, r.created_at "
                "FROM web_reports r ORDER BY r.created_at DESC LIMIT ?", (max(1, min(200, limit)),)).fetchall()
            out = []
            for row in rows:
                actions = conn.execute(
                    "SELECT decision, reason, staff_id, created_at FROM admin_report_actions "
                    "WHERE target_kind = ? AND target_id = ? ORDER BY created_at DESC LIMIT 5",
                    (row["target_kind"], row["target_id"])).fetchall()
                target = self._report_target(conn, row["target_kind"], row["target_id"])
                handled = any(parse_dt(a["created_at"]) >= parse_dt(row["created_at"]) for a in actions)
                if only_open and handled:
                    continue
                out.append({
                    "report_id": row["report_id"], "reporter_user_id": row["reporter_user_id"],
                    "target_kind": row["target_kind"], "target_id": row["target_id"], "reason": row["reason"],
                    "created_at": parse_dt(row["created_at"]), "handled": handled, "target": target,
                    "actions": [{"decision": a["decision"], "reason": a["reason"], "staff_id": a["staff_id"],
                                 "created_at": parse_dt(a["created_at"])} for a in actions],
                    "claim": active_claim(conn, row["target_kind"], row["target_id"], now),
                })
            return out

    def _report_target(self, conn: sqlite3.Connection, kind: str, target_id: str) -> dict[str, Any] | None:
        """只取公开可见部分：公开动态的正文本来就是公开的；评论同理。私聊、叮嘱不在举报范围内，也取不到。"""
        if kind == "post":
            row = conn.execute("SELECT post_id, author_pet_id, user_id, text, visibility, created_at, removed_at FROM web_posts WHERE post_id = ?",
                               (target_id,)).fetchone()
            if row is None:
                return None
            return {"kind": "post", "post_id": row["post_id"], "author_pet_id": row["author_pet_id"], "user_id": row["user_id"],
                    "text": row["text"], "visibility": row["visibility"], "created_at": parse_dt(row["created_at"]),
                    "removed_at": parse_dt(row["removed_at"]) if row["removed_at"] else None}
        if kind == "comment":
            row = conn.execute("SELECT comment_id, post_id, actor_kind, actor_id, user_id, text, created_at, removed_at "
                               "FROM web_comments WHERE comment_id = ?", (target_id,)).fetchone()
            if row is None:
                return None
            return {"kind": "comment", "comment_id": row["comment_id"], "post_id": row["post_id"], "actor_kind": row["actor_kind"],
                    "actor_id": row["actor_id"], "user_id": row["user_id"], "text": row["text"],
                    "created_at": parse_dt(row["created_at"]),
                    "removed_at": parse_dt(row["removed_at"]) if row["removed_at"] else None}
        return {"kind": kind, "target_id": target_id, "note": "这种举报对象没有可展示的公开内容投影。"}
