"""爪爪驾校考局的存取与视图：题目（不含答案）或场地配置、已保存的作答或操作、复算快照与结果。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta

from ..utils import iso, parse_dt
from .courses import FORMAL_ITEMS, TITLES, VARIANTS, course_for
from .curriculum import META, RULES_VERSION
from .errors import DrivingError
from .grading import topic_title
from .questions import ALL, BANK_VERSION, paper
from .replay import Replay

OPEN_STATES = ("preparing", "running")
PREPARING_TTL = timedelta(hours=1)


def content(subject: str, mode: str, item: str | None, number: int) -> tuple[dict, dict]:
    """(配置, 初始进度)。number 决定抽哪组题或哪个场地变体：补考与首次必然不同。"""
    if META[subject]["kind"] == "quiz":
        questions = paper(subject, number, practice=mode == "practice")
        return {"kind": "quiz", "questions": [q.question_id for q in questions]}, {"answers": {}, "feedback": {}}
    names = [item] if item else list(FORMAL_ITEMS[subject])
    variant = VARIANTS[number % len(VARIANTS)]
    courses = [course_for(name, variant) for name in names]
    items = [{"status": "running" if index == 0 else "pending", "events": [], "chunks": [], "snapshot": Replay(course).snapshot()} for index, course in enumerate(courses)]
    return {"kind": "drive", "items": [{"item": name, "variant": variant, "course": course} for name, course in zip(names, courses)]}, {"items": items}


def insert(conn: sqlite3.Connection, *, pet_id: str, user_id: str, subject: str, mode: str, item: str | None, attempt_kind: str | None, round_no: int | None,
           number: int, now: datetime) -> str:
    config, progress = content(subject, mode, item, number)
    session_id = f"ds-{uuid.uuid4().hex[:16]}"
    conn.execute(
        "INSERT INTO web_school_sessions (session_id, pet_id, user_id, subject, mode, item, attempt_kind, round_no, paper_no, rules_version, content_version, config_json, "
        "state, item_index, progress_json, created_at, last_active_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'preparing', 0, ?, ?, ?)",
        (session_id, pet_id, user_id, subject, mode, item, attempt_kind, round_no, number, RULES_VERSION, BANK_VERSION if config["kind"] == "quiz" else "courses-2026.1",
         json.dumps(config, ensure_ascii=False), json.dumps(progress, ensure_ascii=False), iso(now), iso(now)))
    return session_id


def load_in(conn: sqlite3.Connection, session_id: str, pet_id: str):
    return conn.execute("SELECT * FROM web_school_sessions WHERE session_id = ? AND pet_id = ?", (session_id, pet_id)).fetchone()


def require(conn: sqlite3.Connection, pet_id: str, session_id: str):
    row = load_in(conn, session_id, pet_id)
    if row is None:
        raise DrivingError("session_not_found", "没有这场考试或练习。")
    return row


def void_stale(storage, pet_id: str | None, now: datetime) -> int:
    """建立后一小时还没开始的考局作废，不计次。"""
    cutoff = iso(now - PREPARING_TTL)
    sql = "UPDATE web_school_sessions SET state = 'void', void_reason = 'not_started' WHERE state = 'preparing' AND created_at < ?"
    with storage.connect() as conn:
        if pet_id:
            return conn.execute(sql + " AND pet_id = ?", (cutoff, pet_id)).rowcount
        return conn.execute(sql, (cutoff,)).rowcount


def history(storage, user_id: str, pet_id: str, limit: int = 30) -> list[dict]:
    with storage.connect() as conn:
        rows = conn.execute("SELECT * FROM web_school_sessions WHERE pet_id = ? AND state IN ('settled', 'running') "
                            "ORDER BY created_at DESC LIMIT ?", (pet_id, limit)).fetchall()
    return [brief(r) for r in rows]


def input_view(row, item_index: int, new: list[dict]) -> dict:
    progress = json.loads(row["progress_json"])
    prog = progress["items"][item_index]
    deducted = sum(e["p"] for p in progress["items"] for e in p["snapshot"]["events"])
    return {"session_id": row["session_id"], "session_state": row["state"], "item_index": item_index, "current_item": row["item_index"],
            "item_status": prog["status"], "committed_tick": prog["snapshot"]["tick"], "new_events": new, "deducted": deducted,
            "snapshot": prog["snapshot"], "result": json.loads(row["result_json"]) if row["result_json"] else None}


def open_formal_in(conn: sqlite3.Connection, pet_id: str):
    return conn.execute("SELECT * FROM web_school_sessions WHERE pet_id = ? AND mode = 'formal' AND state IN ('preparing', 'running')", (pet_id,)).fetchone()


def save(conn: sqlite3.Connection, session_id: str, progress: dict, now: datetime, **fields) -> None:
    columns = {"progress_json": json.dumps(progress, ensure_ascii=False), "last_active_at": iso(now), **fields}
    assignments = ", ".join(f"{name} = ?" for name in columns)
    conn.execute(f"UPDATE web_school_sessions SET {assignments} WHERE session_id = ?", (*columns.values(), session_id))


def _dt(value: str | None) -> datetime | None:
    return parse_dt(value) if value else None


def brief(row) -> dict | None:
    if row is None:
        return None
    return {"session_id": row["session_id"], "subject": row["subject"], "mode": row["mode"], "item": row["item"], "attempt_kind": row["attempt_kind"],
            "state": row["state"], "passed": None if row["passed"] is None else bool(row["passed"]), "score": row["score"], "created_at": _dt(row["created_at"]),
            "settled_at": _dt(row["settled_at"])}


def question_view(question) -> dict:
    return {"question_id": question.question_id, "kind": question.kind, "scene": question.scene, "topic_title": topic_title(question), "prompt": question.prompt,
            "options": [{"option_id": oid, "label": label} for oid, label in question.options],
            "targets": [{"target_id": tid, "label": label} for tid, label in question.targets], "group": question.group, "group_title": question.group_title,
            "story": list(question.story)}


def view(row) -> dict:
    config, progress = json.loads(row["config_json"]), json.loads(row["progress_json"])
    title = META[row["subject"]]["title"]
    if row["item"]:
        title = f"{title} · {TITLES.get(row['item'], row['item'])}"
    out = {"session_id": row["session_id"], "subject": row["subject"], "title": title, "mode": row["mode"], "item": row["item"], "attempt_kind": row["attempt_kind"],
           "round_no": row["round_no"], "state": row["state"], "pass_score": META[row["subject"]]["pass_score"], "created_at": _dt(row["created_at"]),
           "begun_at": _dt(row["begun_at"]), "paused_at": _dt(row["paused_at"]), "settled_at": _dt(row["settled_at"]), "void_reason": row["void_reason"],
           "quiz": None, "drive": None, "result": json.loads(row["result_json"]) if row["result_json"] else None}
    if config["kind"] == "quiz":
        out["quiz"] = {"questions": [question_view(ALL[qid]) for qid in config["questions"]], "answers": progress["answers"],
                       "feedback": progress["feedback"] if row["mode"] == "practice" else {}}
    else:
        items = []
        for spec, prog in zip(config["items"], progress["items"]):
            snap = prog["snapshot"]
            items.append({"item": spec["item"], "title": TITLES[spec["item"]], "course": spec["course"], "status": prog["status"], "committed_tick": snap["tick"],
                          "events": prog["events"], "sim_events": snap["events"], "snapshot": snap})
        out["drive"] = {"items": items, "current_item": row["item_index"]}
    return out
