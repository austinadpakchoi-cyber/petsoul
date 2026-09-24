#!/usr/bin/env python3
"""真实验收的逐项判定与去敏关联导出（由 scripts/real_acceptance.py 的 judge / verify-job / export 调用）。

- 只读：读 evidence/*.json、验收库（sqlite mode=ro）和进程日志；不调用接口、不产生供应商费用、不改数据。
- 判定结果：PASS / FAIL / PENDING（自然时间还没到，或到点后仍在补齐宽限内）/ UNPROVEN（缺证据，不算通过）。
- 关联只按领域编号：journey_id、世界事件键、账本幂等键、消息 source_event_id；不按文案，也不用账户收入总数。
- 导出的 15-linkage.json 不含消息正文、用户编号、口令与主机名，可以交给独立验收。

退出码：0 全部 PASS；2 没有 FAIL / UNPROVEN 但还有 PENDING；1 有 FAIL 或 UNPROVEN。
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "PetJourneyBackend" / "data" / "web-real-acceptance"
EVIDENCE = DATA / "evidence"
DB = DATA / "petjourney.sqlite3"
PASS, FAIL, PENDING, UNPROVEN = "PASS", "FAIL", "PENDING", "UNPROVEN"
SETTLE_GRACE = timedelta(minutes=5)  # 到点后给任务进程（30 秒一轮）补齐的宽限；过了仍没结算判 FAIL
FLORIST_PAY = 16  # app/web_journey/local.py：work:florist 花店帮忙 2 小时 16 星币
DEFAULT_WAKE = time(7, 30)  # 没改作息的宠物默认 07:30 起床（当地时间）
HK = ZoneInfo("Asia/Hong_Kong")
PRIVATE_KEYS = {"user_id", "household_id", "wallet", "balance", "owner_title", "shared_memories", "email", "username", "password"}
# F 打工期间的进程重启（本窗口操作时记下的 PID；worker.log 只记启动时刻、不记 PID，现任持有者另由 web_worker_leases 佐证）
OPERATOR_RESTARTS = (
    {"at": "2026-09-22T15:01:57Z", "what": "API 与任务进程一起重启", "holder_before": 35824, "holder_after": 50704},
    {"at": "2026-09-22T15:06:13Z", "what": "强制结束任务进程，新进程等旧租约过期后接管", "holder_before": 50704, "holder_after": 41600},
    {"at": "2026-09-22T15:39:29Z", "what": "API 与任务进程一起重启", "holder_before": 41600, "holder_after": 35544},
    {"at": "2026-09-22T15:41:23Z", "what": "API 与任务进程一起重启（当前 18763）", "holder_before": 35544, "holder_after": 57580},
)


@dataclass
class Verdict:
    case: str
    status: str
    expected: str
    actual: object
    basis: str


class Judge:
    def __init__(self, now: datetime) -> None:
        self.now = now
        self.items: list[Verdict] = []

    def check(self, case: str, ok: bool | None, expected: str, actual: object, basis: str) -> None:
        """ok 为 None 表示证据缺失：UNPROVEN，不算通过。"""
        status = UNPROVEN if ok is None else (PASS if ok else FAIL)
        self.items.append(Verdict(case, status, expected, actual, basis))

    def due(self, case: str, at: datetime | None, ok: bool | None, expected: str, actual: object, basis: str) -> None:
        """到点才判：没到 at 保持 PENDING；到点后宽限内结果还没齐也是 PENDING；再之后按 ok 判，不提前写成功。"""
        if at is not None and self.now < at:
            self.items.append(Verdict(case, PENDING, expected, {"due_at": _iso(at), "observed_so_far": actual}, basis))
        elif at is not None and ok is False and self.now < at + SETTLE_GRACE:
            self.items.append(Verdict(case, PENDING, expected, {"settle_grace_until": _iso(at + SETTLE_GRACE), "observed_so_far": actual}, basis))
        else:
            self.check(case, None if at is None else ok, expected, actual, basis)

    def exit_code(self) -> int:
        statuses = {item.status for item in self.items}
        if not self.items or statuses & {FAIL, UNPROVEN}:
            return 1
        return 2 if PENDING in statuses else 0


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _at(text: str | None) -> datetime | None:
    if not text:
        return None
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _load(name: str):
    path = EVIDENCE / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _dig(value, *path):
    for key in path:
        if isinstance(value, dict):
            value = value.get(key)
        elif isinstance(value, list) and isinstance(key, int) and -len(value) <= key < len(value):
            value = value[key]
        else:
            return None
    return value


def _tx(row) -> dict:
    return {"tx_id": row["tx_id"], "pet_id": row["pet_id"], "type": row["type"], "idempotency_key": row["idempotency_key"],
            "delta": json.loads(row["amounts_json"] or "{}").get("travel_coin"), "status": row["status"], "created_at": row["created_at"]}


def _members() -> dict[str, str]:
    """用户编号 → 验收账号标签（只读 accounts.json 里的 user_id，不读、不输出口令）。"""
    path = DATA / "accounts.json"
    stored = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return {info["user_id"]: label for label, info in stored.items() if info.get("user_id")}


def _grouped(con, sql: str, params: tuple, labels: dict[str, str]):
    """按账号标签分组（未知用户归 member）；只带消息编号，不带正文。"""
    buckets: dict[str, list] = {}
    for row in con.execute(sql, params):
        buckets.setdefault(labels.get(row["user_id"], "member"), []).append(row)
    return buckets.items()


def export_linkage() -> dict:
    """从验收库只读导出去敏关联表：旅程、世界事件、账本、消息来源、租约与进程启动记录。"""
    report = _load("00-report") or {}
    journeys = {"F": _dig(report, "F_job_started", "journey_id"), "D": _dig(_load("05-D-cafe"), "snapshot", "journey_id"),
                "E": _dig(_load("07-E-trip"), "journey_id")}
    labels = _members()
    out: dict = {"exported_at": _iso(datetime.now(timezone.utc)), "read_mode": "sqlite mode=ro（不写库）", "journeys": {}}
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        for label, jid in journeys.items():
            if not jid:
                continue
            row = con.execute("SELECT journey_id, pet_id, destination_key, lifecycle, itinerary_version, fee, departed_at, completes_at, completed_at "
                              "FROM web_journeys WHERE journey_id = ?", (jid,)).fetchone()
            events = [dict(r) for r in con.execute("SELECT event_key, kind, occurred_at, applied_at FROM web_world_events WHERE journey_id = ? "
                                                   "ORDER BY occurred_at, event_key", (jid,))]
            messages = [{"message_id": r["message_id"], "channel": r["channel"], "audience": "family" if r["user_id"] == "*" else labels.get(r["user_id"], "member"),
                         "sender": r["sender"], "source_event_id": r["source_event_id"], "composed_by": r["composed_by"], "created_at": r["created_at"]}
                        for r in con.execute("SELECT * FROM web_messages WHERE source_event_id LIKE ? OR source_event_id LIKE ? ORDER BY created_at",
                                             (f"{jid}:%", f"replan:{jid}:%"))]
            ledger = [_tx(r) for r in con.execute("SELECT * FROM economy_transactions WHERE idempotency_key LIKE ? ORDER BY created_at", (f"%{jid}%",))]
            out["journeys"][label] = {"journey": dict(row) if row else None, "events": events, "messages": messages, "ledger": ledger}
        adopted, pet1 = _dig(report, "pets", "adopted"), _dig(report, "pets", "pet1")
        out["job_income"] = [_tx(r) for r in con.execute("SELECT * FROM economy_transactions WHERE pet_id = ? AND type = 'web_job_income' ORDER BY created_at",
                                                        (adopted,))] if adopted else []
        out["pet1_private_ids"] = {label: [r["message_id"] for r in rows] for label, rows in
                                   _grouped(con, "SELECT message_id, user_id FROM web_messages WHERE pet_id = ? AND channel = 'private' ORDER BY created_at",
                                            (pet1,), labels)} if pet1 else {}
        out["pet1_threads"] = [{"audience": "family" if r["user_id"] == "*" else labels.get(r["user_id"], "member"), "channel": r["channel"], "sender": r["sender"],
                                "count": r["n"]} for r in con.execute("SELECT user_id, channel, sender, COUNT(*) AS n FROM web_messages WHERE pet_id = ? "
                                                                      "GROUP BY user_id, channel, sender ORDER BY user_id, channel, sender", (pet1,))] if pet1 else []
        reply_id = _dig(_load("08-C-model"), "reply", "message_id")
        reply = con.execute("SELECT message_id, channel, sender, composed_by, reply_to, created_at FROM web_messages WHERE message_id = ?",
                            (reply_id,)).fetchone() if reply_id else None
        out["c_reply"] = dict(reply) if reply else None
        out["leases"] = [{k: r[k] for k in ("name", "pid", "role", "started_at", "heartbeat_at", "expires_at", "last_ok_at", "ticks")}
                         for r in con.execute("SELECT * FROM web_worker_leases ORDER BY name")]
    finally:
        con.close()
    api_log = (DATA / "api.log").read_text(encoding="utf-8", errors="replace") if (DATA / "api.log").exists() else ""
    worker_log = (DATA / "worker.log").read_text(encoding="utf-8", errors="replace") if (DATA / "worker.log").exists() else ""
    out["process_starts"] = {"api_pids_in_order": [int(p) for p in re.findall(r"Started server process \[(\d+)\]", api_log)],
                             "worker_started_at_utc": re.findall(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ INFO petsoul\.web_worker ", worker_log, re.M),
                             "current_run": json.loads((DATA / "run.json").read_text(encoding="utf-8")) if (DATA / "run.json").exists() else None}
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "15-linkage.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def restart_evidence(rep: dict, link: dict) -> dict:
    """14-F-restart.json：打工期间每次重启前后的租约持有进程。启动时刻来自 worker.log，现任持有者来自租约表，
    之前的 PID 来自本窗口操作记录；0.4.0 的租约没有领取代数（A 包的新租约接入后才有），所以代数记为 null。"""
    started = rep.get("F_job_started") or {}
    logged = set(_dig(link, "process_starts", "worker_started_at_utc") or [])
    lease = next((l for l in link.get("leases") or [] if l["name"] == "world"), None)
    restarts = [{**r, "claim_generation_before": None, "claim_generation_after": None,
                 "start_in_worker_log": r["at"].replace("T", " ").rstrip("Z") in logged,
                 "during_work": bool(_at(started.get("work_from")) and _at(started.get("work_until"))
                                     and _at(started["work_from"]) <= _at(r["at"]) <= _at(started["work_until"]))}
                for r in OPERATOR_RESTARTS]
    return {"journey_id": started.get("journey_id"), "journey_window": [started.get("work_from"), started.get("work_until"), started.get("home_at")],
            "restarts": restarts, "lease_now": lease, "api_pids_in_order": _dig(link, "process_starts", "api_pids_in_order"),
            "basis": "启动时刻：worker.log；现任持有者与接管时刻：web_worker_leases（started_at 晚于进程启动约一个租期，即等旧租约过期后接管）；"
                     "之前的 PID：本窗口操作记录。claim_generation 在 0.4.0 租约里不存在，记 null。"}


def _by_source(messages: list, source: str) -> list:
    return [m for m in messages if m["source_event_id"] == source]


def _judge_a(j: Judge, rep: dict, world) -> None:
    reg, home, hh, relog = rep.get("A_register"), rep.get("A_home"), rep.get("A_household"), rep.get("A_relogin")
    chosen = _dig(world, "residents", 0, "pet_id")
    j.check("A1 注册后先等伙伴，入口带着访客页选中的居民", None if not reg else reg.get("step") == "needs_companion" and reg.get("households") == []
            and _dig(reg, "entry", "pending_adoption", "pet_id") == chosen, "step=needs_companion、没有家庭、入口是访客页第一位居民",
            {"step": _dig(reg, "step"), "households": _dig(reg, "households"), "entry_pet": _dig(reg, "entry", "pending_adoption", "pet_id"), "chosen": chosen}, "00-report A_register、01")
    cards = {c.get("kind"): c.get("status") for c in (home or {}).get("cards") or []}
    j.check("A2 入住后签发三张证件与欢迎旅费", None if not home else home.get("step") == "active" and _dig(home, "wallet", "balance") == 20
            and cards == {"identity_card": "active", "bank_card": "active", "care_profile": "active"}, "step=active、三张证件 active、余额 20",
            {"step": _dig(home, "step"), "cards": cards, "balance": _dig(home, "wallet", "balance")}, "00-report A_home、02")
    pets = (hh or {}).get("pets") or []
    j.check("A3 一个家三只宠物、领养保留 pet_id、不指明宠物 409", None if not hh else hh.get("adopted_resident_keeps_pet_id") is True and len(pets) == 3
            and all(p.get("join_step") == "moved_in" for p in pets) and hh.get("no_pet_id_without_choice") == 409, "三只都 moved_in；领养前后 pet_id 相同；/home 不带 pet_id 409",
            {"pets": [(p.get("origin"), p.get("join_step")) for p in pets], "keeps_pet_id": _dig(hh, "adopted_resident_keeps_pet_id"),
             "no_pet_id": _dig(hh, "no_pet_id_without_choice")}, "00-report A_household、03")
    j.check("A4 退出后 401，重新登录三只宠物与余额一致", None if not relog else relog.get("logged_out_status") == 401 and relog.get("pets_after") == 3
            and relog.get("wallets_before") == relog.get("wallets_after") and bool(relog.get("wallets_before")), "401；余额逐只相同；3 只宠物",
            relog, "00-report A_relogin")


def _judge_b(j: Judge, rep: dict) -> None:
    b = rep.get("B")
    j.check("B1 两个账号同时领养同一位居民只成功一个", None if not b else sorted((b.get("statuses") or {}).values()) == [200, 409],
            "状态码恰好 [200, 409]", _dig(b, "statuses"), "00-report B、10")
    j.check("B2 账号之间隔离", None if not b else (b.get("loser_cannot_see_winner_pet"), b.get("loser_cannot_read_messages"), b.get("A_cannot_see_B_pet")) == (404, 404, 404),
            "失败方看家与消息、A 看 B 的宠物都是 404", {k: _dig(b, k) for k in ("loser_cannot_see_winner_pet", "loser_cannot_read_messages", "A_cannot_see_B_pet")},
            "00-report B、10")


def _judge_c(j: Judge, rep: dict, link: dict) -> None:
    reply, row = _dig(_load("08-C-model"), "reply"), link.get("c_reply")
    composed = _dig(reply, "composed_by")
    ok = None if not reply else (False if composed != "model" else (None if row is None else row.get("composed_by") == "model" and row.get("sender") == "pet"))
    j.check("C1 真实模型按 DNA 回信（必须 composed_by=model，模板不算）", ok, "接口返回与库里同一条消息都是 composed_by=model",
            {"api_composed_by": composed, "db": row, "text": _dig(reply, "text")}, "08-C-model（接口）+ 15-linkage c_reply（库，按 message_id）")
    sent_id = _dig(_load("08-C-model"), "sent", "message_id")
    j.check("C1b 这条回信对应家人发的那条消息", None if not row or not sent_id else row.get("reply_to") == sent_id,
            "库里这条回信的 reply_to 就是家人那条消息的编号（0.4.1 起接口也下发 reply_to）",
            {"reply_to": (row or {}).get("reply_to"), "owner_message": sent_id}, "15-linkage c_reply + 08-C-model")
    llm = next((p for p in _dig(rep, "ops", "providers") or [] if p.get("provider") == "llm"), None)
    j.check("C2 供应商健康记录了这次成功调用", None if not llm else llm.get("state") == "verified" and (llm.get("calls_today") or 0) >= 1 and bool(llm.get("last_success_at")),
            "llm=verified、当天调用 ≥ 1、有最近成功时间", llm, "00-report ops")


def _judge_d(j: Judge) -> None:
    recheck, cafe = _load("12-D-recheck"), _load("05-D-cafe")
    place, legs = _dig(recheck, "place") or {}, _dig(recheck, "legs") or []
    j.check("D1 真实地点与路线估时（高德 POI + 高德步行）", None if not recheck else place.get("provider") == "amap" and str(place.get("place_id", "")).startswith("amap:")
            and bool(legs) and all(l.get("time_source") == "routed_estimate" and l.get("source") for l in legs), "地点 amap:*；每段 time_source=routed_estimate 且有来源说明",
            {"place": {k: place.get(k) for k in ("provider", "place_id", "name")}, "legs": [(l.get("mode"), l.get("time_source")) for l in legs]}, "12-D-recheck")
    fallback = _dig(cafe, "visit", "place") or {}
    fallback_legs = _dig(cafe, "snapshot", "legs") or []
    labelled = fallback.get("provider") == "amap" or (fallback.get("provider") == "world" and bool(fallback.get("attribution"))
                                                        and all(l.get("time_source") == "world_rule" for l in fallback_legs))
    j.check("D2 地图失败时落到“星球内的地方”并明确标注", None if not cafe else labelled, "provider=world 时有署名说明、路段 time_source=world_rule（不冒充现实地址）",
            {"provider": fallback.get("provider"), "attribution": fallback.get("attribution"), "legs": [l.get("time_source") for l in fallback_legs]}, "05-D-cafe")


def _judge_e(j: Judge, rep: dict, link: dict) -> None:
    trip, entry = rep.get("E_trip"), _dig(link, "journeys", "E") or {}
    ferry = (trip or {}).get("ferry") or []
    fee = [t for t in entry.get("ledger") or [] if t["type"] == "web_travel_fee"]
    j.check("E1 远行计划有来源：参考班次、动物世界编号可追溯、现实票价与星币分开、旅费只扣一次", None if not trip or not entry else len(ferry) == 2
            and all(f.get("world_service", "").startswith("Otter") and f.get("world_reference") == f.get("reference_id") and ":20" in f.get("reference_id", "") for f in ferry)
            and bool(trip.get("fares")) and _dig(trip, "venue", "provider") == "amap" and len(fee) == 1 and fee[0]["delta"] == -40,
            "去程/回程各一班、编号指向参考班次；有参考票价；目的地是高德地点；旅费 web_travel_fee 恰好一条 -40",
            {"ferry": [(f.get("world_service"), f.get("reference_id")) for f in ferry], "fares": len(trip.get("fares") or []) if trip else None,
             "venue": _dig(trip, "venue", "place_id"), "fee_ledger": fee}, "00-report E_trip、07、15-linkage E")
    journey = entry.get("journey") or {}
    planned_leave = _at(_dig(trip, "leave_home_at"))
    departed = _at(journey.get("departed_at"))
    replans = [m for m in entry.get("messages") or [] if str(m["source_event_id"]).startswith("replan:")]
    refunds = [t for t in entry.get("ledger") or [] if t["type"] != "web_travel_fee"]
    # 复核可能不止一次（每次改签都会 +1 个行程版本、发一条说明）：只要出门时刻落在 TA 醒着的时候、且每次改签都说明过就算成立。
    # 只数"至少一条"证明不了没有重复通知：**按 source_event_id 逐条查唯一**，不同版本的合法改签各算一条。
    replan_ids = [str(m.get("source_event_id") or "") for m in replans]
    no_duplicate_notice = len(set(replan_ids)) == len(replan_ids)
    told_once = len(replans) >= 1 and no_duplicate_notice
    awake_ok = departed is not None and departed.astimezone(HK).time() >= DEFAULT_WAKE and (journey.get("itinerary_version") or 1) >= 2 and told_once
    cancelled_ok = journey.get("lifecycle") == "cancelled" and len(refunds) == 1 and told_once
    j.due("E2 原计划 06:21 出门（TA 还在睡）：出门前按作息复核，改到醒着的班次或取消退款，家庭频道每次改签只说明一次", planned_leave,
          None if not journey else (awake_ok or cancelled_ok),
          "出门时刻（香港）≥ 07:30 且行程版本 ≥ 2，或取消并恰好退款一次；改签说明每个 source_event_id 恰好一条、不重复",
          {"departed_at": journey.get("departed_at"), "itinerary_version": journey.get("itinerary_version"), "lifecycle": journey.get("lifecycle"),
           "replan_messages": replans, "replan_event_ids": replan_ids, "no_duplicate_notice": no_duplicate_notice,
           "refunds": refunds}, "15-linkage E（web_journeys、replan:* 家庭消息、账本）")


def _judge_f(j: Judge, rep: dict, link: dict) -> None:
    started, entry = rep.get("F_job_started") or {}, _dig(link, "journeys", "F") or {}
    jid = started.get("journey_id")
    work_until, home_at, work_from = _at(started.get("work_until")), _at(started.get("home_at")), _at(started.get("work_from"))
    key = f"web:job:{jid}"
    wage = [t for t in entry.get("ledger") or [] if t["idempotency_key"] == key]
    other = [t for t in link.get("job_income") or [] if t["idempotency_key"] != key and work_from and _at(t["created_at"]) >= work_from]
    wage_ok = None if not jid else (False if not wage else len(wage) == 1 and wage[0]["type"] == "web_job_income" and wage[0]["delta"] == FLORIST_PAY and not other)
    j.due("F1 工资恰好一次（按工作实例幂等键）", work_until, wage_ok, f"{key} 恰好 1 条 web_job_income、+{FLORIST_PAY}；开工后没有别的工资记录",
          {"wage": wage, "other_job_income": other}, "15-linkage：economy_transactions 按幂等键；job_income 按宠物")
    messages, events = entry.get("messages") or [], entry.get("events") or []
    done = _by_source(messages, f"{jid}:work_done")
    done_ok = None if not jid else (False if not done else len(done) == 1 and done[0]["audience"] == "family" and done[0]["channel"] == "family")
    j.due("F2 家庭频道“打工结束”消息恰好一次（按 source_event_id）", work_until, done_ok, f"source_event_id={jid}:work_done 恰好 1 条，全家一条（family）",
          done, "15-linkage：web_messages 按 source_event_id")
    keys = {e["event_key"]: e for e in events}
    effective_ok = None if not jid else ("work_done" in keys and "visit_ended" in keys and _at(keys["work_done"]["occurred_at"]) == work_until)
    j.due("F3 结束事件按原本应发生的时间记账", work_until, effective_ok, "work_done 与 visit_ended 已记录，work_done.occurred_at = 计划收工时间（晚恢复不改有效时间）",
          {k: keys.get(k) for k in ("visit_ended", "work_done")}, "15-linkage：web_world_events")
    journey = entry.get("journey") or {}
    home_msgs = _by_source(messages, f"{jid}:returned_home")
    home_ok = None if not journey else ("returned_home" in keys and journey.get("lifecycle") == "completed" and _at(journey.get("completed_at")) == home_at
                                         and len(home_msgs) == 1 and home_msgs[0]["audience"] == "family")
    j.due("F4 回家：旅程完成一次、到家消息恰好一次", home_at, home_ok, "returned_home 已记录；lifecycle=completed、completed_at=计划到家时间；到家消息 1 条",
          {"lifecycle": journey.get("lifecycle"), "completed_at": journey.get("completed_at"), "returned_home": keys.get("returned_home"), "messages": home_msgs},
          "15-linkage")
    starts = [datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) for s in _dig(link, "process_starts", "worker_started_at_utc") or []]
    during = [_iso(s) for s in starts if work_from and work_until and work_from <= s <= work_until]
    lease = next((l for l in link.get("leases") or [] if l["name"] == "world"), None)
    first_pid = _dig(rep, "ops", "world", "lease_pid")
    api_pids = _dig(link, "process_starts", "api_pids_in_order") or []
    j.check("F5 打工期间确实重启过任务进程与 API，并由新进程接管租约", None if not started or not lease else len(during) >= 1 and lease["pid"] != first_pid
            and len(api_pids) >= 2, "开工到收工之间 worker 至少启动 1 次；现在的租约持有者不是开跑时那个进程；API 进程换过",
            {"worker_starts_during_job": during, "lease_pid_at_run": first_pid, "lease_now": lease, "api_pids_in_order": api_pids},
            "worker.log 启动行、web_worker_leases、api.log、00-report ops")


def _judge_h(j: Judge, rep: dict, link: dict) -> None:
    dup, busy, broke = rep.get("H_duplicate"), rep.get("H_one_place"), rep.get("H_insufficient")
    fee = [t for t in _dig(link, "journeys", "D", "ledger") or [] if t["type"] == "web_travel_fee"]
    j.check("H1 同一个幂等键重复出发：同一趟行程、只扣一次", None if not dup else dup.get("same_journey") is True and dup.get("charged") == 8
            and len(fee) == 1 and fee[0]["delta"] == -8, "两次返回同一 journey_id；余额只少 8；旅费账本恰好 1 条 -8", {"api": dup, "fee_ledger": fee},
            "00-report H_duplicate + 15-linkage D")
    j.check("H2 在外面时不能再出发", None if not busy else busy.get("status") == 409 and busy.get("reason") == "already_traveling", "409 already_traveling", busy,
            "00-report H_one_place")
    j.check("H3 钱不够：远行不成立、不扣钱", None if not broke else broke.get("status") == 409 and broke.get("code") == "INSUFFICIENT_FUNDS"
            and broke.get("balance_after") == broke.get("balance_before") is not None,
            "409 INSUFFICIENT_FUNDS，余额一分没少（地图状态只作旁证：领养来的居民本来就有旧行程，不能据此判有没有新行程）",
            broke, "00-report H_insufficient")


def _judge_family(j: Judge, rep: dict, link: dict) -> None:
    fam = _load("09-family") or rep.get("family")
    threads = link.get("pet1_threads") or []
    c_private = sum(t["count"] for t in threads if t["audience"] == "C" and t["channel"] == "private" and t["sender"] == "owner")
    family_rows = sum(t["count"] for t in threads if t["audience"] == "family")
    j.check("FAM1 邀请预览与角色：看到三只宠物、以共同照顾者加入、不能改家庭设置", None if not fam else len(fam.get("invite_preview_pets") or []) == 3
            and fam.get("joined_role") == "caregiver" and fam.get("caregiver_changes_settings") == 403, "预览 3 个名字；role=caregiver；改设置 403",
            {k: fam.get(k) for k in ("invite_preview_pets", "joined_role", "caregiver_changes_settings")} if fam else None, "09")
    ids = link.get("pet1_private_ids") or {}
    overlap = sorted(set(ids.get("A") or []) & set(ids.get("C") or []))
    j.check("FAM2 私聊按家人隔离", None if not fam or not threads else fam.get("private_message_hidden_from_A") is True and c_private >= 1 and not overlap
            and bool(ids.get("A")) and bool(ids.get("C")),
            "两位家人的私聊消息编号互不相交；库里按用户分开存；A 的线程里没有 C 的那条",
            {"hidden_from_A": fam.get("private_message_hidden_from_A") if fam else None, "c_private_user_messages": c_private,
             "shared_message_ids": overlap, "counts": {k: len(v) for k, v in ids.items()}}, "09 + 15-linkage pet1_private_ids")
    same = fam.get("family_ids_A") == fam.get("family_ids_C") and bool(fam.get("family_ids_A")) if fam and "family_ids_A" in fam else (fam or {}).get("family_channel_same_for_both")
    j.check("FAM3 家庭频道全家同一份", None if not fam or not threads else same is True and family_rows >= 1, "两人看到的家庭频道消息编号完全相同；库里家庭消息只存一份（user_id='*'）",
            {"same": same, "family_rows": family_rows}, "09 + 15-linkage pet1_threads")
    j.check("FAM4 被移除后立即失去访问", None if not fam else fam.get("after_removal_status") == 404, "移除后下一次请求 404", fam.get("after_removal_status") if fam else None, "09")


def _judge_visitor(j: Judge, world) -> None:
    def keys(value, acc: set) -> set:
        if isinstance(value, dict):
            for k, v in value.items():
                acc.add(k)
                keys(v, acc)
        elif isinstance(value, list):
            for v in value:
                keys(v, acc)
        return acc

    leaked = sorted(keys(world, set()) & PRIVATE_KEYS) if world else None
    j.check("VIS1 访客不登录看世界：四个入口、没有私密字段", None if not world else [e.get("route") for e in world.get("entries") or []]
            == ["browse", "own_pet", "adopt", "invite"] and not leaked and bool(world.get("residents")), "四个入口；整份返回里没有用户/家庭/钱包/称呼等字段",
            {"entries": [e.get("route") for e in (world or {}).get("entries") or []], "private_keys_found": leaked}, "01")


def _judge_chain(j: Judge, link: dict) -> None:
    chain, entry = _load("13-chain"), _dig(link, "journeys", "D") or {}
    jid = _dig(chain, "journey_id")
    messages = entry.get("messages") or []
    counts = {k: len(_by_source(messages, f"{jid}:{k}")) for k in ("departed", "visit_started", "returned_home")}
    j.check("CH1 家庭频道：出发、到店、回家各恰好一条（按 source_event_id）", None if not chain or not entry else counts == {"departed": 1, "visit_started": 1, "returned_home": 1}
            and all(m["audience"] == "family" for m in messages), "三类各 1 条，都在家庭频道", counts, "15-linkage D")
    posts = _dig(chain, "posts") or []
    events = {e["event_key"] for e in entry.get("events") or []}
    j.check("CH2 公开动态指向同一次到访结束事件，访客能看到", None if not chain else bool(posts) and all(p.get("source_event_id") == f"{jid}:visit_ended" for p in posts)
            and "visit_ended" in events and bool(set(p["post_id"] for p in posts) & set(chain.get("visitor_sees_posts") or [])),
            "动态的 source_event_id = <journey>:visit_ended，事件表里有这条；访客页能看到", {"posts": [(p.get("post_id"), p.get("source_event_id")) for p in posts],
                                                                              "visitor_sees": chain.get("visitor_sees_posts") if chain else None}, "13-chain + 15-linkage D")
    j.check("CH3 时间线与账本指向同一趟行程", None if not chain else any(i.get("ref_id") == jid for i in chain.get("timeline") or [])
            and len([t for t in entry.get("ledger") or [] if t["type"] == "web_travel_fee"]) == 1, "时间线有 ref_id=<journey> 的条目；旅费账本恰好 1 条",
            {"timeline": len(chain.get("timeline") or []) if chain else None, "ledger": entry.get("ledger")}, "13-chain + 15-linkage D")


def judge(scope: str = "all") -> int:
    """scope=all：全部；scope=F：只判自然时间打工（verify-job）。结果写 evidence 并按退出码约定返回。"""
    link = export_linkage()
    rep, world = _load("00-report") or {}, _load("01-visitor-world")
    j = Judge(datetime.now(timezone.utc))
    if scope == "F":
        _judge_f(j, rep, link)
    else:
        _judge_a(j, rep, world)
        _judge_b(j, rep)
        _judge_c(j, rep, link)
        _judge_d(j)
        _judge_e(j, rep, link)
        _judge_f(j, rep, link)
        _judge_h(j, rep, link)
        _judge_family(j, rep, link)
        _judge_visitor(j, world)
        _judge_chain(j, link)
    code = j.exit_code()
    result = {"judged_at": _iso(j.now), "scope": scope, "exit_code": code, "summary": {s: sum(1 for v in j.items if v.status == s) for s in (PASS, FAIL, PENDING, UNPROVEN)},
              "not_covered": "G（驾照/回放/DNA 否定句）由自动化测试证明，不在本判定器范围", "verdicts": [asdict(v) for v in j.items]}
    (EVIDENCE / ("21-F-verdicts.json" if scope == "F" else "20-verdicts.json")).write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for v in j.items:
        print(f"{v.status:<9} {v.case}")
        if v.status != PASS:
            print(f"          期望：{v.expected}")
            print(f"          实际：{json.dumps(v.actual, ensure_ascii=False, default=str)[:400]}")
    print(f"汇总：{result['summary']}；退出码 {code}")
    return code
