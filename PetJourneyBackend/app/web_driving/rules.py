"""爪爪驾校的考试机会、冷却与解锁规则（服务端裁定；按宠物、按科目；时间一律用服务器时间）。

- 每一轮：首次考试＋一次补考（共 2 次正式考试机会）；
- 本轮两次都没通过：从第二次结算的时间起冷却 7×24 小时；冷却结束自动进入新一轮；
- 已通过的科目永久保留，不再消耗机会；正式考试按科目一 → 二 → 三 → 四依次解锁；练习随时可以。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..utils import iso, parse_dt
from .curriculum import COOLDOWN_HOURS, META, SUBJECTS

PREREQ = {"s1": None, "s2": "s1", "s3": "s2", "s4": "s3"}
ATTEMPTS_PER_ROUND = 2


@dataclass
class SubjectRow:
    pet_id: str
    subject: str
    user_id: str
    round_no: int = 1
    fails_in_round: int = 0
    cooldown_until: datetime | None = None
    cooldown_noted: int = 0
    passed_at: datetime | None = None
    passed_session_id: str | None = None
    passed_score: int | None = None
    practice_count: int = 0

    @classmethod
    def from_row(cls, row) -> "SubjectRow":
        return cls(row["pet_id"], row["subject"], row["user_id"], row["round_no"], row["fails_in_round"], parse_dt(row["cooldown_until"]) if row["cooldown_until"] else None,
                   row["cooldown_noted"], parse_dt(row["passed_at"]) if row["passed_at"] else None, row["passed_session_id"], row["passed_score"], row["practice_count"])

    def save(self, conn, now: datetime) -> None:
        conn.execute(
            "INSERT INTO web_school_subjects (pet_id, subject, user_id, round_no, fails_in_round, cooldown_until, cooldown_noted, passed_at, passed_session_id, passed_score, "
            "practice_count, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(pet_id, subject) DO UPDATE SET round_no = excluded.round_no, "
            "fails_in_round = excluded.fails_in_round, cooldown_until = excluded.cooldown_until, cooldown_noted = excluded.cooldown_noted, passed_at = excluded.passed_at, "
            "passed_session_id = excluded.passed_session_id, passed_score = excluded.passed_score, practice_count = excluded.practice_count, updated_at = excluded.updated_at",
            (self.pet_id, self.subject, self.user_id, self.round_no, self.fails_in_round, iso(self.cooldown_until) if self.cooldown_until else None, self.cooldown_noted,
             iso(self.passed_at) if self.passed_at else None, self.passed_session_id, self.passed_score, self.practice_count, iso(now)))


def rows_in(conn, pet_id: str) -> dict[str, SubjectRow]:
    return {r["subject"]: SubjectRow.from_row(r) for r in conn.execute("SELECT * FROM web_school_subjects WHERE pet_id = ?", (pet_id,)).fetchall()}


def rolled(row: SubjectRow, now: datetime) -> SubjectRow:
    """冷却已经结束：进入新一轮（重新获得首次考试＋一次补考）。"""
    if row.fails_in_round >= ATTEMPTS_PER_ROUND and row.cooldown_until is not None and now >= row.cooldown_until:
        return SubjectRow(row.pet_id, row.subject, row.user_id, row.round_no + 1, 0, None, 0, row.passed_at, row.passed_session_id, row.passed_score, row.practice_count)
    return row


def after_failure(row: SubjectRow, settled_at: datetime) -> SubjectRow:
    fails = row.fails_in_round + 1
    cooldown = settled_at + timedelta(hours=COOLDOWN_HOURS) if fails >= ATTEMPTS_PER_ROUND else None
    return SubjectRow(row.pet_id, row.subject, row.user_id, row.round_no, fails, cooldown, 0, row.passed_at, row.passed_session_id, row.passed_score, row.practice_count)


def state_of(subject: str, rows: dict[str, SubjectRow], open_subject: str | None, now: datetime, legacy: bool) -> dict:
    """一科的展示状态：passed / in_exam / cooldown / locked / available，以及本轮机会。"""
    user_row = rows.get(subject)
    row = rolled(user_row, now) if user_row else None
    round_no, fails = (row.round_no, row.fails_in_round) if row else (1, 0)
    info = {"subject": subject, "title": META[subject]["title"], "theme": META[subject]["theme"], "kind": META[subject]["kind"], "round_no": round_no,
            "attempts_used": fails, "attempts_left": ATTEMPTS_PER_ROUND - fails, "next_attempt": "first" if fails == 0 else "retake",
            "cooldown_until": None, "unlock_hint": None, "passed_at": row.passed_at if row else None, "passed_score": row.passed_score if row else None,
            "legacy": False, "practice_count": row.practice_count if row else 0}
    if legacy or (row and row.passed_at):
        return dict(info, state="passed", legacy=legacy and not (row and row.passed_at), attempts_left=0, next_attempt=None)
    if open_subject == subject:
        return dict(info, state="in_exam")
    if row and row.cooldown_until is not None and now < row.cooldown_until:
        return dict(info, state="cooldown", cooldown_until=row.cooldown_until, attempts_left=0, next_attempt=None)
    need = PREREQ[subject]
    if need and not (legacy or (rows.get(need) and rows[need].passed_at)):
        return dict(info, state="locked", unlock_hint=f"先通过{META[need]['title'].split('：')[0]}")
    return dict(info, state="available")


def all_passed(rows: dict[str, SubjectRow]) -> bool:
    return all(rows.get(s) is not None and rows[s].passed_at is not None for s in SUBJECTS)
