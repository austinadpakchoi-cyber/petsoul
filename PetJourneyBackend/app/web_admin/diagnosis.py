"""宠物"为什么没动静"与"照片为什么没出来"的**只读**诊断。

复用的是既有事实，不另算一套：
- 运行投影 `web.projector`（所在地、当地作息、当前活动、版本、到期事项）；
- 心跳 `web_runtime.heartbeat_policy.evaluate` —— 和 `/ops/runtime/{pet_id}` 同一个调用，
  **按当前事实评估一次，不执行、不记录、不调模型、不推进世界**；
- 安静原因 `SilenceReason`，它自己带 normal / deferred / fault 三档，直接用来分"在生活" / "被推迟" / "出故障"；
- 照片链路：`web_illustrations`(processing/ready/failed) ×`web_tasks`(attempts/last_error) ×
  `web_budget_reservations`(reserved/settled/unknown/expired)。

关于 unknown：预占停在 reserved / unknown / expired 就表示"很可能已经发出去、结果没确认"。
这里只**如实显示**，不改状态、不释放额度、不自动重发，也不把它说成失败或未发送。
判断是否允许人工恢复的那段在 `commands.py`，用的也是这份依据。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..storage import JourneyStorage
from ..utils import parse_dt, utcnow
from ..web_runtime.heartbeat_policy import HeartbeatPolicy, evaluate
from ..web_runtime.reasons import SilenceKind, SilenceReason, silence_of
from . import labels as L
from .directory import owner_of_pet
from .metering import counted_units

# 面向运营的说明：把原因码翻译成"这是什么情况 / 还能做什么"。没收录的原因码如实显示原值，不编。
# 说法只有一份，在 labels.py（与领域枚举双向核对）；这里保留旧名字给调用方。
SILENCE_TEXT: dict[str, tuple[str, str]] = L.SILENCE

KIND_LABEL = {SilenceKind.NORMAL: "正常", SilenceKind.DEFERRED: "已推迟", SilenceKind.FAULT: "故障"}

# 额度预占停在这些状态＝很可能已经发出去、结果没确认（与 web_journey.illustrations 同一套判断）
UNCONFIRMED_RESERVATION_STATUSES = ("reserved", "unknown", "expired")


@dataclass(frozen=True, slots=True)
class PhotoAttempt:
    illustration_id: str
    pet_id: str
    user_id: str
    status: str                       # processing / ready / failed
    source_event_id: str
    task_id: str
    created_at: datetime
    updated_at: datetime
    provider: str | None
    model: str | None
    task_status: str | None           # queued / running / succeeded / failed / superseded
    attempts: int | None
    max_attempts: int | None
    last_error: str | None
    run_after: datetime | None
    reservations: list[dict] = field(default_factory=list)
    # 这张图在玩家那一侧用在哪里（明信片 / 通讯器消息 / 攻略手账），按任务号关联；None＝这个库查不了（表还不在），[]＝没找到
    surfaces: list[dict] | None = None

    @property
    def call_state(self) -> str:
        """给运营看的一句话状态：ready / processing / failed / unknown。

        unknown ＝ 最近一次预占停在 reserved/unknown/expired：**已经发出去，结果没确认**。
        它既不是失败也不是没发送，不自动重发，费用记录保留。
        """
        if self.status == "ready":
            return "ready"
        latest = self.reservations[0] if self.reservations else None
        if latest and latest["status"] in UNCONFIRMED_RESERVATION_STATUSES and self.status == "failed":
            return "unknown"
        if self.status == "failed":
            return "failed"
        return "processing"

    @property
    def recoverable(self) -> bool:
        """只有"明确没画成、且最近一次预占已经结清/退回"才允许人工恢复。unknown 一律不允许。"""
        if self.status != "failed" or self.task_status != "failed":
            return False
        latest = self.reservations[0] if self.reservations else None
        return not (latest and latest["status"] in UNCONFIRMED_RESERVATION_STATUSES)

    @property
    def error_label(self) -> str | None:
        """最近一次错误的一句人话；认不出来就是 None（界面照原样显示原始错误串）。"""
        return L.error_label(self.last_error)

    @property
    def retry_ticket(self) -> str:
        return f"{self.task_id}#{self.attempts if self.attempts is not None else 0}"


@dataclass(frozen=True, slots=True)
class PetDiagnosis:
    pet_id: str
    as_of: datetime
    available: bool                       # 运行投影是否启用；未启用时如实说明，不编状态
    unavailable_reason: str | None
    headline: str
    detail: str
    silence_reason: str | None
    silence_kind: str | None
    activity: dict[str, Any]
    place: dict[str, Any]
    heartbeat: dict[str, Any]
    versions: dict[str, Any]
    due_items: list[dict]
    consent: dict[str, Any]
    journey: dict[str, Any] | None
    photos: list[PhotoAttempt]
    world_runner: dict[str, Any]
    place_label: str | None = None          # 「香港 · 中环」；片区不在目录里就是 None（界面显示原始片区号）
    reasons: list[dict] = field(default_factory=list)  # 心跳依据：[{code, label}]，label 为 None＝没收录
    consent_rows: list[dict] = field(default_factory=list)  # 授权开关的人话版：[{key, label, value}]


class AdminDiagnosis:
    def __init__(self, storage: JourneyStorage, web) -> None:
        self.storage = storage
        self.web = web

    # ---- 宠物 ----
    def pet(self, pet_id: str, now: datetime | None = None) -> PetDiagnosis | None:
        if self.web.pets.profile(pet_id) is None:
            return None
        now = now or utcnow()
        projector = getattr(self.web, "projector", None)
        photos = self.photos_for_pet(pet_id)
        runner = self._runner()
        if projector is None:
            return PetDiagnosis(
                pet_id=pet_id, as_of=now, available=False,
                unavailable_reason="这个环境没有接上运行投影，诊断给不出所在地与心跳。这不是宠物的问题（技术上：运行投影没有装配）。",
                headline="诊断不可用", detail="运行投影未接入；这不是宠物的问题，是这套环境没开这项能力。",
                silence_reason=None, silence_kind=None, activity={}, place={}, heartbeat={}, versions={}, due_items=[],
                consent=self._consent(pet_id), journey=self._journey(pet_id), photos=photos, world_runner=runner,
                consent_rows=consent_rows(self._consent(pet_id)),
            )
        state = projector.state(pet_id, now)
        facts = projector.facts(pet_id, now)
        row = projector.runtime.row(pet_id)
        decision = evaluate(state, (), HeartbeatPolicy(), now, facts=facts)
        reason = decision.silence_reason or silence_of(decision) or row.get("silence_reason")
        reason_value = getattr(reason, "value", reason) if reason else None
        kind = None
        if reason_value:
            try:
                kind = SilenceReason(reason_value).kind
            except ValueError:
                kind = None
        headline, detail = SILENCE_TEXT.get(reason_value or "", ("在行动", "这一刻没有安静原因：TA 正要做事或刚做完。"))
        if reason_value and reason_value.startswith("brain:"):
            # AI 思考记下的：对照模式的结论，或这次没想成、稍后再试。不能落到上面的「在行动」
            text = L.silence_label(reason_value)
            headline, detail = (("AI 思考是对照模式", f"{text}。") if reason_value == "brain:shadow"
                                else ("AI 思考稍后再试", f"{text}。到了下次复查时间会再想一次。"))
        if bool(row.get("maintenance")):
            headline, detail = "已暂停", "后台暂停了 TA 的自主运行：不做新的生活决定，在途的旅程照常走完。谁、为什么，见下方「运行记录」。"
        activity = state.primary_activity
        consent = {**self._consent(pet_id), "cognition_enabled": facts.cognition.enabled}
        return PetDiagnosis(
            pet_id=pet_id, as_of=state.as_of, available=True, unavailable_reason=None,
            headline=headline, detail=detail,
            silence_reason=reason_value, silence_kind=(KIND_LABEL.get(kind) if kind else None),
            activity={
                "kind": activity.kind if activity else "unknown",
                "ref": activity.ref if activity else None,
                "ends_at": activity.ends_at if activity else None,
                "interruptible": bool(activity.interruptible) if activity else True,
            },
            place={
                "realm_id": state.realm_id, "household_id": state.household_id, "timezone": state.timezone,
                "region_id": state.region_id, "scene_ref": state.scene_ref,
                "sleep_window": [f"{t:%H:%M}" for t in state.sleep_window] if state.sleep_window else [],
            },
            heartbeat={
                "action": decision.action.value, "reason_codes": list(decision.reason_codes),
                "next_check_at": decision.next_check_at,
                "next_review_at": parse_dt(row["next_review_at"]) if row.get("next_review_at") else None,
                "last_evaluated_at": parse_dt(row["last_evaluated_at"]) if row.get("last_evaluated_at") else None,
                "last_decision_at": parse_dt(row["last_decision_at"]) if row.get("last_decision_at") else None,
                "last_decision_by": row.get("last_decision_by"),
                "maintenance": bool(row.get("maintenance")),
            },
            versions={
                "runtime": state.versions.runtime_epoch, "activity": state.versions.activity_epoch,
                "dna": state.versions.dna_version, "privacy": state.versions.privacy_epoch,
                "membership": state.versions.membership_epoch, "itinerary": state.versions.itinerary_version,
            },
            due_items=[{"ref": item.ref, "kind": item.kind.value, "due_at": item.due_at, "commitment": item.commitment}
                       for item in facts.due_items],
            consent=consent,
            journey=self._journey(pet_id), photos=photos, world_runner=runner,
            place_label=place_label(state.region_id),
            reasons=[{"code": code, "label": L.reason_label(code)} for code in decision.reason_codes],
            consent_rows=consent_rows(consent),
        )

    def _runner(self) -> dict[str, Any]:
        from ..web_platform.lease import lease_status
        lanes = {}
        for name, ticker in (("world", getattr(self.web, "ticker", None)), ("cognition", getattr(self.web, "cognition", None))):
            lease = lease_status(self.storage, name) or {}
            lanes[name] = {"running_here": bool(getattr(ticker, "running", False)), "lease_alive": bool(lease.get("alive")),
                           "last_tick_at": lease.get("last_tick_at"), "last_ok_at": lease.get("last_ok_at"),
                           "last_error": lease.get("last_error"), "ticks": int(lease.get("ticks") or 0)}
        return lanes

    def _consent(self, pet_id: str) -> dict[str, Any]:
        """用途授权只看布尔值，不取任何正文。宠物没有家庭（待领养居民）时家庭项为 None。"""
        with self.storage.connect() as conn:
            household = conn.execute("SELECT household_id FROM web_household_pets WHERE pet_id = ?", (pet_id,)).fetchone()
            row = None
            if household:
                row = conn.execute("SELECT generated_photos, pet_messages FROM web_households WHERE household_id = ?",
                                   (household["household_id"],)).fetchone()
            # 照顾人按家庭成员算，不用 web_pet_profiles.user_id：领养来的居民那一列停在系统账号上。
            owner_id = owner_of_pet(conn, pet_id)
            prefs = conn.execute("SELECT model_replies, generated_photos, pet_messages FROM web_user_prefs WHERE user_id = ?",
                                 (owner_id,)).fetchone() if owner_id else None
        return {
            "household_id": household["household_id"] if household else None,
            "owner_user_id": owner_id,
            "household_generated_photos": (None if row is None or row["generated_photos"] is None else bool(row["generated_photos"])),
            "household_pet_messages": (None if row is None or row["pet_messages"] is None else bool(row["pet_messages"])),
            "owner_model_replies": bool(prefs["model_replies"]) if prefs else False,
            "owner_generated_photos": bool(prefs["generated_photos"]) if prefs else False,
        }

    def _journey(self, pet_id: str) -> dict[str, Any] | None:
        with self.storage.connect() as conn:
            row = conn.execute(
                "SELECT journey_id, destination_key, title, city, lifecycle, departed_at, completes_at FROM web_journeys "
                "WHERE pet_id = ? ORDER BY departed_at DESC LIMIT 1", (pet_id,)).fetchone()
            if row is None:
                return None
            events = conn.execute(
                "SELECT event_key, kind, occurred_at FROM web_world_events WHERE journey_id = ? ORDER BY occurred_at DESC LIMIT 10",
                (row["journey_id"],)).fetchall()
            legs = _journey_legs(conn, row["journey_id"])
            visits = _journey_visits(conn, row["journey_id"])
        return {"journey_id": row["journey_id"], "destination_key": row["destination_key"], "title": row["title"], "city": row["city"],
                "lifecycle": row["lifecycle"], "lifecycle_label": L.label("journey_lifecycle", row["lifecycle"]),
                "departed_at": parse_dt(row["departed_at"]) if row["departed_at"] else None,
                "completes_at": parse_dt(row["completes_at"]) if row["completes_at"] else None,
                "recent_events": [{"event_key": e["event_key"], "kind": e["kind"], "label": event_label(e["kind"], e["event_key"]),
                                   "occurred_at": parse_dt(e["occurred_at"])} for e in events],
                "legs": legs, "visits": visits}

    # ---- 照片 ----
    def photos_for_pet(self, pet_id: str, limit: int = 20) -> list[PhotoAttempt]:
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT * FROM web_illustrations WHERE pet_id = ? ORDER BY created_at DESC LIMIT ?",
                                (pet_id, max(1, min(100, limit)))).fetchall()
            return [self._attempt(conn, row) for row in rows]

    def photo(self, illustration_id: str) -> PhotoAttempt | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_illustrations WHERE illustration_id = ?", (illustration_id,)).fetchone()
            return None if row is None else self._attempt(conn, row)

    def pending_photos(self, limit: int = 50) -> list[PhotoAttempt]:
        """运行首页用：还没出图的（processing / failed）按时间倒序。没有就是空。"""
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT * FROM web_illustrations WHERE status != 'ready' ORDER BY updated_at DESC LIMIT ?",
                                (max(1, min(200, limit)),)).fetchall()
            return [self._attempt(conn, row) for row in rows]

    def _attempt(self, conn: sqlite3.Connection, row) -> PhotoAttempt:
        task = conn.execute("SELECT status, attempts, max_attempts, last_error, run_after FROM web_tasks WHERE task_id = ?",
                            (row["task_id"],)).fetchone()
        prefix = f"illustration:{row['task_id']}:"
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        reservations: list[dict] = []
        try:
            for res in conn.execute(
                "SELECT operation_id, provider, purpose, status, outcome, reserved_units, actual_units, provider_request_id, created_at, settled_at "
                "FROM web_budget_reservations WHERE operation_id LIKE ? ESCAPE '\\' "
                "ORDER BY CAST(substr(operation_id, ?) AS INTEGER) DESC, rowid DESC", (escaped + "%", len(prefix) + 1)
            ):
                reservations.append({
                    "operation_id": res["operation_id"], "provider": res["provider"], "purpose": res["purpose"],
                    "status": res["status"], "outcome": res["outcome"], "reserved_units": int(res["reserved_units"]),
                    "actual_units": None if res["actual_units"] is None else int(res["actual_units"]),
                    # 展示用计量看这个，不看上一列：released（确定没发出）列里常是预占量，计数器却计 0（见 metering.py）
                    "counted_units": counted_units(res["status"], res["reserved_units"], res["actual_units"]),
                    "provider_request_id": res["provider_request_id"],
                    "created_at": parse_dt(res["created_at"]), "settled_at": parse_dt(res["settled_at"]) if res["settled_at"] else None,
                })
        except sqlite3.OperationalError:
            reservations = []  # 迁移 0050 之前的库没有额度表：如实为空，不假装"没有调用"
        return PhotoAttempt(
            surfaces=_surfaces(conn, row["task_id"]),
            illustration_id=row["illustration_id"], pet_id=row["pet_id"], user_id=row["user_id"], status=row["status"],
            source_event_id=row["source_event_id"], task_id=row["task_id"],
            created_at=parse_dt(row["created_at"]), updated_at=parse_dt(row["updated_at"]),
            provider=row["provider"], model=row["model"],
            task_status=task["status"] if task else None,
            attempts=int(task["attempts"]) if task else None,
            max_attempts=int(task["max_attempts"]) if task else None,
            last_error=task["last_error"] if task else None,
            run_after=parse_dt(task["run_after"]) if task and task["run_after"] else None,
            reservations=reservations,
        )


# ---- 人话（要查目录的那部分放这里；纯静态的说法在 labels.py）----
def place_label(region_id: str | None) -> str | None:
    """片区号 → 「城市 · 片区」。不在片区目录里（比如驿站或新片区）就是 None，界面照原样显示片区号。"""
    from ..web_home.place import AREAS
    hit = AREAS.get(region_id or "")
    return f"{hit[1].city} · {hit[1].label}" if hit else None


def event_label(kind: str, event_key: str) -> str | None:
    """旅程事件 → 人话：「到达第 2 站」「路上的小插曲：咖啡馆小侦探」。认不出来就是 None。"""
    base = L.label("world_event", kind)
    suffix = event_key.split(":", 1)[1] if ":" in event_key else ""
    if kind == "leg_arrived" and suffix.isdigit():
        return f"到达第 {suffix} 站"
    if kind == "adventure" and suffix:
        from ..web_journey.adventures import ADVENTURES
        template = ADVENTURES.get(suffix)
        return f"{base}：{template.title}" if template is not None and base else base
    return base


def consent_rows(consent: dict[str, Any]) -> list[dict]:
    return [{"key": key, "label": L.label("consent", key), "value": value} for key, value in consent.items()]


def _surfaces(conn: sqlite3.Connection, task_id: str) -> list[dict] | None:
    """这张图用在玩家那一侧的哪里。只取种类、城市与时间，**不取标题、正文或图片地址**。"""
    found: list[dict] = []
    try:
        for row in conn.execute("SELECT item_id, kind, city, obtained_at FROM web_collection_items WHERE image_task_id = ?", (task_id,)):
            found.append({"kind": "postcard" if row["kind"] == "postcard" else "keepsake", "item_kind": row["kind"], "ref": row["item_id"],
                          "city": row["city"], "at": parse_dt(row["obtained_at"]) if row["obtained_at"] else None})
        for row in conn.execute("SELECT message_id, created_at FROM web_messages WHERE photo_task_id = ?", (task_id,)):
            found.append({"kind": "message", "ref": row["message_id"], "city": None, "at": parse_dt(row["created_at"])})
        for row in conn.execute("SELECT guide_id, city, created_at FROM web_travel_guides WHERE image_task_id = ?", (task_id,)):
            found.append({"kind": "guide", "ref": row["guide_id"], "city": row["city"], "at": parse_dt(row["created_at"])})
    except sqlite3.OperationalError:
        return None  # 这个库里还没有这些表：查不了，不等于"没用在任何地方"
    return found


def photo_view(photo: PhotoAttempt) -> dict[str, Any]:
    """照片给界面的样子：原字段 + 一句话状态、能否恢复、错误的人话。三个接口共用，免得各拼各的。"""
    from dataclasses import asdict
    return {**asdict(photo), "call_state": photo.call_state, "recoverable": photo.recoverable,
            "retry_ticket": photo.retry_ticket, "error_label": photo.error_label}


def _json(raw) -> dict | list | None:
    import json
    try:
        return json.loads(raw) if raw else None
    except (TypeError, ValueError):
        return None


def _journey_legs(conn: sqlite3.Connection, journey_id: str) -> list[dict] | None:
    """一段旅程的逐段交通：去程 / 回程、怎么走、从哪到哪、几点出发几点到、时间的依据。此刻在哪一段由界面按时间判断。
    只取站点的名字，不取坐标与路线点（那是地图数据，排查用不上）。"""
    try:
        rows = conn.execute(
            "SELECT leg_id, sequence, direction, kind, mode, role, origin_json, destination_json, starts_at, ends_at, time_basis, freshness, "
            "position_basis FROM web_journey_legs WHERE journey_id = ? ORDER BY starts_at, sequence", (journey_id,)).fetchall()
    except sqlite3.OperationalError:
        return None
    out = []
    for r in rows:
        origin, destination = _json(r["origin_json"]) or {}, _json(r["destination_json"]) or {}
        out.append({"leg_id": r["leg_id"], "sequence": r["sequence"], "direction": r["direction"], "kind": r["kind"], "mode": r["mode"],
                    "role": r["role"], "from": origin.get("name"), "to": destination.get("name"),
                    "starts_at": parse_dt(r["starts_at"]) if r["starts_at"] else None, "ends_at": parse_dt(r["ends_at"]) if r["ends_at"] else None,
                    "time_basis": r["time_basis"], "freshness": r["freshness"], "position_basis": r["position_basis"]})
    return out


def _journey_visits(conn: sqlite3.Connection, journey_id: str) -> list[dict] | None:
    """到店明细：店名、类型、几点到几点走、店里的几件事做到哪了。不取活动的结果文字（那是写给玩家看的故事）。"""
    try:
        rows = conn.execute("SELECT visit_id, place_json, template, starts_at, ends_at, activities_json FROM web_visits WHERE journey_id = ? "
                            "ORDER BY starts_at", (journey_id,)).fetchall()
    except sqlite3.OperationalError:
        return None
    out = []
    for r in rows:
        place = _json(r["place_json"]) or {}
        activities = _json(r["activities_json"]) or []
        out.append({"visit_id": r["visit_id"], "place": place.get("name"), "category": place.get("category"), "template": r["template"],
                    "starts_at": parse_dt(r["starts_at"]) if r["starts_at"] else None, "ends_at": parse_dt(r["ends_at"]) if r["ends_at"] else None,
                    "activities": [{"kind": a.get("kind"), "label": a.get("label"), "state": a.get("state")}
                                   for a in activities if isinstance(a, dict)]})
    return out
