"""宠物运行总览与暂停（第九批；居民需求 §6「世界运行」、方案 §3「宠物排查」）。

**总览只读已经记下的事实**：运行表（上次心跳、下次心跳、安静原因、上次决定是 AI 还是规则、在途的思考）、
规则生活每个时段记下的决定、进行中的旅程、今天的额度用量、钱包。**不在查询时评估心跳、不推进世界、不调模型**
——要看「这一刻按事实评估一次」去宠物页的诊断。

心跳现在默认是对照模式（config：只评估并记下结论、不执行），让宠物真的出门打工的是规则生活；AI 思考默认关。
这一页把这些模式如实写在最上面，免得把「心跳按时」读成「宠物在按心跳行动」。

**暂停**：写运行表的 `maintenance` 一列（迁移 0060 就有，`web_runtime/state.py` 注明给管理员用），
同一事务里经共享 helper 给 runtime_epoch +1（在途的思考提交时作废；已经发出的调用与费用照记，不截断），
后台自己的依据（原因、谁、版本）记在 `admin_pet_maintenance`。**不写 last_evaluated_at / next_check_at**——那是心跳自己的标记。

**只在各条运行线都认暂停的范围内开放**（2026-09-24 心跳窗口与本窗口各自核过）：心跳与 AI 思考本来就认它；
规则生活（`web_agent/life.py`）的闸由心跳窗口在同日补上（共享谓词 `RuntimeStore.paused`，与 `due_pets` 同一口径），
本窗口的用例真跑规则生活、带对照验证过。**到点回复与主动来信还不认**（在 I 的文件里，等排期）——所以现在只对
**还在驿站生活的居民**开放：它们没有家人，不涉及回复与来信；玩家自己的宠物如实写「暂不开放」。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from ..web_platform.runtime_epochs import bump_in
from ..web_platform.uow import unit_of_work
from .commands import ActorContext, require_reason
from .content_types import builtin_name
from .errors import AdminAPIError, AdminErrorCode
from .labels import silence_label
from .permissions import Permission
from .social import people

# 规则生活的暂停闸已落地（2026-09-24，心跳窗口；本窗口用例带对照验证）：对驿站居民开放。改回 False 就整体不开放。
PAUSE_OPEN = True
PAUSE_CLOSED_REASON = ("暂停现在还挡不住规则生活（出门、打工）、到点回复和主动来信——按了也停不住，所以先不开放。"
                       "已请对应的窗口补上，补好并验证之后先对还在驿站生活的居民开放。")
THINKING_STUCK = timedelta(minutes=10)


def _dt(value: str | None) -> datetime | None:
    return parse_dt(value) if value else None


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row] | None:
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return None  # 表还不在：查不了 ≠ 没有


def rule_decision(decision: str | None) -> dict[str, Any] | None:
    """规则生活记下的决定（`rest` / `rest:enough_today` / `go:<地点>`）→ 代码与说法。认不出来的说法为 None，界面照原样显示。

    `go:` 在**出发之前**就记下，出发被拒也不撤回（`web_agent/life.py` 有意这样设计：同一时段不空转重试）。
    所以说法写成「决定出门去…」，不写成「出门去…」——后者读起来像已经走了（Q 独立验收报的）。
    """
    if not decision:
        return None
    if decision.startswith("go:"):
        key = decision.split(":", 1)[1]
        return {"code": decision, "label": f"决定出门去「{builtin_name('destination', key)}」"}
    from .labels import RULE_DECISION

    return {"code": decision, "label": RULE_DECISION.get(decision)}


class AdminPetRuntime:
    def __init__(self, storage: JourneyStorage, settings, commands, audit) -> None:
        self.storage = storage
        self.settings = settings
        self.commands = commands
        self.audit = audit

    # ---- 模式与执行者 ----
    def modes(self, now: datetime) -> dict[str, Any]:
        from ..web_platform.lease import lease_status

        from .lanes import configured_from_settings, lane_state

        tick = float(getattr(self.settings, "web_world_tick_seconds", 30.0))
        lanes = {name: lease_status(self.storage, name, now) for name in ("world", "cognition")}
        configured = configured_from_settings(self.settings)
        return {
            "world_runner": getattr(self.settings, "web_world_runner", "embedded"),
            "heartbeat_mode": getattr(self.settings, "web_heartbeat_mode", "shadow"),
            "brain_mode": getattr(self.settings, "web_brain_mode", "off"),
            "tick_seconds": tick,
            "world_alive": bool(lanes["world"] and lanes["world"]["alive"]),
            "cognition_alive": bool(lanes["cognition"] and lanes["cognition"]["alive"]),
            "world_configured": configured,
            "world_state": lane_state(configured, bool(lanes["world"] and lanes["world"]["alive"])),
            "cognition_state": lane_state(configured, bool(lanes["cognition"] and lanes["cognition"]["alive"])),
            "caps": {"brain_per_pet": int(getattr(self.settings, "web_brain_daily_per_pet", 12)),
                     "image_per_pet": int(getattr(self.settings, "web_image_per_pet_daily_cap", 6))},
            "accounting_day": now.date().isoformat(),  # 额度按 UTC 记账日（北京时间 08:00 换日）
            "pause_open": PAUSE_OPEN,
            "pause_closed_reason": None if PAUSE_OPEN else PAUSE_CLOSED_REASON,
        }

    # ---- 总览 ----
    def overview(self, *, wallets: bool, usage: bool, pet_id: str | None = None, now: datetime | None = None) -> dict[str, Any]:
        """`pet_id` 给了就只看这一只（宠物页用同一份口径）。"""
        now = now or utcnow()
        modes = self.modes(now)
        late_after = timedelta(seconds=max(120.0, 3 * modes["tick_seconds"]))
        with self.storage.connect() as conn:
            pets = conn.execute(
                # 物种与目录页同一口径（directory.py）：网页档案里有就用它，没有退回 pets.pet_type
                "SELECT pt.pet_id, pt.name, COALESCE(wp.species, pt.pet_type) AS species, hp.household_id, r.status AS resident_status, "
                "s.label AS residence, o.moved_in_at, h.activated_at "
                "FROM pets pt LEFT JOIN web_pet_profiles wp ON wp.pet_id = pt.pet_id LEFT JOIN web_household_pets hp ON hp.pet_id = pt.pet_id "
                "LEFT JOIN web_residents r ON r.pet_id = pt.pet_id LEFT JOIN web_residences s ON s.residence_id = r.residence_id "
                "LEFT JOIN web_pet_onboarding o ON o.pet_id = pt.pet_id LEFT JOIN web_homes h ON h.household_id = hp.household_id "
                "WHERE (hp.pet_id IS NOT NULL OR r.pet_id IS NOT NULL) AND (? IS NULL OR pt.pet_id = ?) ORDER BY pt.name, pt.pet_id",
                (pet_id, pet_id)).fetchall()
            ids = [p["pet_id"] for p in pets]
            marks = ",".join("?" for _ in ids) or "''"
            runtime = {r["pet_id"]: r for r in (_rows(conn, f"SELECT * FROM web_entity_runtime WHERE pet_id IN ({marks})", tuple(ids)) or [])}
            paused_by = {r["pet_id"]: r for r in (_rows(conn, f"SELECT * FROM admin_pet_maintenance WHERE pet_id IN ({marks})", tuple(ids)) or [])}
            rules = {r["pet_id"]: r for r in (_rows(
                conn, f"SELECT pet_id, slot_key, decision, created_at FROM web_pet_decisions d WHERE pet_id IN ({marks}) "
                      "AND created_at = (SELECT MAX(created_at) FROM web_pet_decisions x WHERE x.pet_id = d.pet_id)", tuple(ids)) or [])}
            trips = {r["pet_id"]: r for r in (_rows(
                conn, f"SELECT pet_id, title, city, departed_at, completes_at FROM web_journeys WHERE lifecycle = 'active' "
                      f"AND pet_id IN ({marks})", tuple(ids)) or [])}
            admins = {r["household_id"]: r["user_id"] for r in (_rows(
                conn, "SELECT household_id, user_id FROM web_household_members m WHERE role = 'admin' AND status = 'active' "
                      "AND joined_at = (SELECT MIN(joined_at) FROM web_household_members x WHERE x.household_id = m.household_id "
                      "AND x.role = 'admin' AND x.status = 'active')") or [])}
            names = people(conn, admins.values())
            coins = ({r["pet_id"]: int(r["travel_coin"]) for r in (_rows(
                conn, f"SELECT pet_id, travel_coin FROM pet_wallets WHERE pet_id IN ({marks})", tuple(ids)) or [])}
                     if wallets else None)
            counters = self._counters(conn, ids, modes["accounting_day"]) if usage else None

        rows = []
        for pet in pets:
            pid = pet["pet_id"]
            run = runtime.get(pid)
            maintenance = bool(run["maintenance"]) if run else False
            last_eval = _dt(run["last_evaluated_at"]) if run else None
            next_check = _dt(run["next_check_at"]) if run else None
            if maintenance:
                heartbeat_state = "paused"
            elif last_eval is None:
                heartbeat_state = "never"
            elif modes["world_configured"] and next_check is not None and next_check + late_after < now:
                heartbeat_state = "late"
            else:
                heartbeat_state = "ok"
            started = _dt(run["decision_started_at"]) if run and run["decision_operation_id"] else None
            brain_state = "idle" if started is None else ("stuck" if now - started > THINKING_STUCK else "thinking")
            household = pet["household_id"]
            owner = admins.get(household) if household else None
            record = paused_by.get(pid)
            rule = rules.get(pid)
            trip = trips.get(pid)
            rows.append({
                "pet_id": pid, "name": pet["name"], "species": pet["species"],
                "kind": "resident" if pet["resident_status"] == "resident" else "household",
                "residence": pet["residence"] if pet["resident_status"] == "resident" else None,
                "household_id": household, "owner_user_id": owner, "owner_name": names.get(owner) if owner else None,
                "moved_in": bool(pet["moved_in_at"] and pet["activated_at"]) if household else None,
                "heartbeat": {"state": heartbeat_state, "last_evaluated_at": last_eval, "next_check_at": next_check,
                              "silence_reason": run["silence_reason"] if run else None,
                              "silence_label": silence_label(run["silence_reason"]) if run else None, "has_runtime_row": run is not None},
                "brain": {"state": brain_state, "started_at": started,
                          "last_decision_at": _dt(run["last_decision_at"]) if run else None,
                          "last_decision_by": run["last_decision_by"] if run else None,
                          "next_review_at": _dt(run["next_review_at"]) if run else None},
                "rule_life": None if rule is None else {"slot": rule["slot_key"], "decision": rule_decision(rule["decision"]),
                                                         "at": _dt(rule["created_at"])},
                "trip": None if trip is None else {"title": trip["title"], "city": trip["city"], "departed_at": _dt(trip["departed_at"]),
                                                   "completes_at": _dt(trip["completes_at"])},
                "paused": maintenance,
                "pause_record": None if record is None else {"paused": bool(record["paused"]), "reason": record["reason"],
                                                              "changed_by": record["changed_by"], "changed_at": _dt(record["changed_at"]),
                                                              "version": int(record["version"])},
                "wallet": None if coins is None else coins.get(pid),
                "usage_today": None if counters is None else counters.get(pid, {}),
            })
        return {"modes": modes, "pets": rows, "sections": {"wallets": wallets, "usage": usage},
                "notes": {
                    "source": "只读已经记下的事实：这一页不评估心跳、不推进世界、不调用模型。要看这一刻的评估，打开宠物页。",
                    "wallet": "钱袋子是这只宠物游戏账本里的星币余额（游戏资产，与平台费用分开）。",
                    "usage": "今天＝UTC 记账日（北京时间 08:00 换日）；次数取额度计数器（已用＋在途），每宠上限是每个用途各算各的。",
                }}

    def _counters(self, conn: sqlite3.Connection, ids: list[str], day: str) -> dict[str, dict[str, dict[str, int]]]:
        rows = _rows(conn, "SELECT scope_key, used_units, inflight_units FROM web_budget_counters WHERE window_key = ? "
                           "AND scope_key LIKE 'pet:%'", (day,)) or []
        wanted = set(ids)
        out: dict[str, dict[str, dict[str, int]]] = {}
        for row in rows:
            parts = row["scope_key"].split(":")
            if len(parts) != 3 or parts[1] not in wanted:
                continue
            out.setdefault(parts[1], {})[parts[2]] = {"used": int(row["used_units"]), "inflight": int(row["inflight_units"])}
        return out

    # ---- 暂停 / 恢复 ----
    def _subject(self, conn: sqlite3.Connection, pet_id: str) -> dict[str, Any]:
        pet = conn.execute(
            "SELECT pt.pet_id, pt.name, r.status AS resident_status, hp.household_id FROM pets pt "
            "LEFT JOIN web_residents r ON r.pet_id = pt.pet_id LEFT JOIN web_household_pets hp ON hp.pet_id = pt.pet_id "
            "WHERE pt.pet_id = ? AND (r.pet_id IS NOT NULL OR hp.pet_id IS NOT NULL)", (pet_id,)).fetchone()
        if pet is None:
            raise AdminAPIError.not_found("这只宠物")
        runtime = conn.execute("SELECT maintenance FROM web_entity_runtime WHERE pet_id = ?", (pet_id,)).fetchone()
        record = conn.execute("SELECT paused, reason, changed_by, changed_at, version FROM admin_pet_maintenance WHERE pet_id = ?",
                              (pet_id,)).fetchone()
        resident = pet["resident_status"] == "resident"
        if not PAUSE_OPEN:
            blocked = PAUSE_CLOSED_REASON
        elif not resident:
            blocked = "玩家自己的宠物暂不开放暂停：到点回复与主动来信还不认暂停（已请 I 补上），按了也停不住它给家人回信。"
        else:
            blocked = None
        return {"pet_id": pet_id, "name": pet["name"], "resident": resident,
                "paused": bool(runtime["maintenance"]) if runtime else False,
                "version": int(record["version"]) if record else 0,
                "reason": record["reason"] if record else None, "changed_by": record["changed_by"] if record else None,
                "changed_at": _dt(record["changed_at"]) if record else None, "blocked_reason": blocked}

    def pause_preview(self, pet_id: str, now: datetime | None = None) -> dict[str, Any]:
        now = now or utcnow()
        world = self.modes(now)["world_alive"]
        with self.storage.connect() as conn:
            subject = self._subject(conn, pet_id)
        pause_effects = [
            "TA 不再做新的生活决定：规则生活不再安排出门、打工，AI 思考也不再为 TA 做决定。",
            "已经在路上的这一趟照常走完；已经在冲洗的照片仍会完成。",
            "已经发出的 AI 调用和费用记录照常保留，不截断、不抹掉。",
            "不删除这只宠物：身份、钱包、经历都不动，随时可以恢复。",
        ]
        if subject["resident"]:
            pause_effects.append("它仍在待领养名单上：暂停不等于撤下（撤下是另一件事）。")
        resume_effects = [
            "世界推进开着：恢复后大约半分钟内 TA 会重新开始自己做决定。" if world
            else "世界推进现在没在跑：恢复后要等世界推进开起来，TA 才会继续自己做决定。",
            "暂停期间没做的决定不会补做；从恢复那一刻按当时的事实往下走。",
        ]
        return {**subject, "world_running": world, "pause_effects": pause_effects, "resume_effects": resume_effects}

    def set_paused(self, ctx: ActorContext, pet_id: str, *, paused: bool, reason: str, expected_version: int | None) -> dict[str, Any]:
        reason = require_reason(reason)
        action = "pet.pause" if paused else "pet.resume"

        def handler() -> dict:
            now = utcnow()
            with unit_of_work(self.storage) as conn:
                subject = self._subject(conn, pet_id)
                if paused and subject["blocked_reason"]:
                    raise AdminAPIError(AdminErrorCode.conflict, subject["blocked_reason"], 409, details={"pet_id": pet_id})
                if expected_version is not None and expected_version != subject["version"]:
                    raise AdminAPIError.version_conflict(expected_version, subject["version"])
                if subject["paused"] == paused:
                    raise AdminAPIError(AdminErrorCode.conflict, "TA 已经是暂停状态了。" if paused else "TA 没有被暂停。", 409,
                                        details={"pet_id": pet_id, "paused": paused})
                conn.execute(
                    "INSERT INTO admin_pet_maintenance (pet_id, paused, reason, changed_by, changed_at, version) VALUES (?, ?, ?, ?, ?, 1) "
                    "ON CONFLICT(pet_id) DO UPDATE SET paused = excluded.paused, reason = excluded.reason, "
                    "changed_by = excluded.changed_by, changed_at = excluded.changed_at, version = admin_pet_maintenance.version + 1",
                    (pet_id, 1 if paused else 0, reason, ctx.staff_id, iso(now)))
                # 先换代（没有运行记录时它会建一行），再改开关；只写 maintenance，不碰心跳自己的 last_evaluated_at / next_check_at
                bump_in(conn, pet_id, "runtime_epoch", now)
                conn.execute("UPDATE web_entity_runtime SET maintenance = ? WHERE pet_id = ?", (1 if paused else 0, pet_id))
                version = int(conn.execute("SELECT version FROM admin_pet_maintenance WHERE pet_id = ?", (pet_id,)).fetchone()["version"])
                epoch = int(conn.execute("SELECT runtime_epoch FROM web_entity_runtime WHERE pet_id = ?", (pet_id,)).fetchone()["runtime_epoch"])
                self.audit.record_in(conn, status="succeeded", outcome="paused" if paused else "running",
                                     changes={"from": "paused" if subject["paused"] else "running", "to": "paused" if paused else "running",
                                              "version": version, "runtime_epoch": epoch},
                                     action=action, permission=Permission.PET_MAINTAIN.value, actor_staff_id=ctx.staff_id,
                                     actor_username=ctx.username, target_kind="pet", target_id=pet_id, reason=reason,
                                     operation_id=ctx.operation_id, request_id=ctx.request_id)
            return {"pet_id": pet_id, "paused": paused, "version": version,
                    "note": "已暂停：TA 不再做新的生活决定。" if paused else "已恢复：世界推进开着时，大约半分钟内 TA 会重新开始自己做决定。"}

        return self.commands.run(ctx, action, {"pet_id": pet_id, "paused": paused, "reason": reason,
                                               "expected_version": expected_version}, handler)
