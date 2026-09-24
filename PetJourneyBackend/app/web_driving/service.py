"""爪爪驾校：主人陪考，宠物拿证（规格见 docs/contracts/DRIVING-SCHOOL-v1.md）。

- TA 自己会产生学车愿望、满一天后自己报名并邀请主人陪练；考试由主人陪着完成，TA 不会自己去考。
- 四科：科一、科四按固定题库批改；科二、科三按主人上传的操作记录，由服务端确定性复算（replay.py）。
- 每科首次考试＋一次补考；两次不过从第二次结算起冷却 7×24 小时；已通过的科目永久保留（rules.py）。
- 正式考局在 begin 之后才计次；同一只宠物同一时间最多一场未结束的正式考局；结算只做一次。
- 第四科通过、四科齐全时，在同一次提交里签发爪爪驾驶证、发借车券并登记拿证消息；消息走发件箱，投递失败不影响驾照。
- 旧版（自动答题）留下的“已通过未签发”记录由 reconcile 补签；已持旧版驾照的宠物，各科显示“旧版驾考已通过”。
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from typing import Callable

from ..storage import JourneyStorage
from ..utils import iso, parse_dt
from . import sessions
from .courses import PRACTICE_ITEMS
from .curriculum import COACH, META, RULES_VERSION, SUBJECTS, pet_line, temperament
from .errors import DrivingError
from .grading import drive_result, next_step, quiz_result
from .notes import DrivingNotes
from .questions import ALL, correct, correct_answer, valid
from .replay import InputError, Replay, validate
from .rules import SubjectRow, after_failure, all_passed, rolled, rows_in, state_of

LICENSE_NOTE = "我拿到驾照啦！编号 {number}。以后可以自己开车去兜风了（第一次借驾校的车，不用租车费）。"
PENDING_REASON = "考试已经通过，驾驶证正在签发，稍后刷新看看。"
logger = logging.getLogger(__name__)


class DrivingService:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage
        self.notes = DrivingNotes(storage)
        # 装配时注入：驾驶证与借车券在同一事务里签发；画像给台词；生图只在主人开启且配置时才请求
        self.issue_license: Callable[[sqlite3.Connection, str, str, str, datetime, dict], dict] = \
            lambda conn, user_id, pet_id, source_id, issued_at, data: {"credential_id": source_id, "number": ""}
        self.license_in: Callable[[sqlite3.Connection, str], dict | None] = lambda conn, pet_id: None
        self.grant_item: Callable[..., None] = lambda conn, user_id, pet_id, kind, title, note, source, now: None
        self.voucher_of: Callable[[str], bool] = lambda pet_id: False
        self.profile_of: Callable[[str], object] = lambda pet_id: None
        self.memento_photo: Callable[[str, str, str], str | None] = lambda user_id, pet_id, source_key: None

    @property
    def say(self) -> Callable[[str, str, str, str, datetime], None]:
        return self.notes.say

    @say.setter
    def say(self, value: Callable[[str, str, str, str, datetime], None]) -> None:
        self.notes.say = value

    # ---- 阶段（愿望、报名、驾照）----
    @staticmethod
    def _row_in(conn: sqlite3.Connection, pet_id: str):
        return conn.execute("SELECT * FROM web_driving WHERE pet_id = ?", (pet_id,)).fetchone()

    def _row(self, pet_id: str):
        with self.storage.connect() as conn:
            return self._row_in(conn, pet_id)

    def _stage_in(self, conn: sqlite3.Connection, pet_id: str, row) -> str:
        if self.license_in(conn, pet_id):
            return "licensed"
        if row is None:
            return "none"
        if row["stage"] == "licensed":
            return "license_pending"
        return "enrolled" if row["stage"] == "theory_passed" else row["stage"]

    def stage(self, pet_id: str) -> str:
        with self.storage.connect() as conn:
            return self._stage_in(conn, pet_id, self._row_in(conn, pet_id))

    def license_of(self, pet_id: str) -> dict | None:
        with self.storage.connect() as conn:
            return self.license_in(conn, pet_id)

    def wish(self, user_id: str, pet_id: str, text: str, now: datetime) -> bool:
        """TA 自己产生学车愿望（由自主生活触发）。只在还没开始学车时记录一次。"""
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if self._stage_in(conn, pet_id, self._row_in(conn, pet_id)) != "none":
                return False
            conn.execute("INSERT INTO web_driving (pet_id, user_id, stage, wish_text, wish_at, mastery_json, updated_at) VALUES (?, ?, 'wish', ?, ?, '{}', ?)",
                         (pet_id, user_id, text, iso(now), iso(now)))
            self.notes.queue(conn, user_id, pet_id, f"driving:wish:{pet_id}", text, now)
        self.notes.deliver(pet_id)
        return True

    def enroll(self, user_id: str, pet_id: str, now: datetime, *, by_owner: bool) -> None:
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if self._stage_in(conn, pet_id, self._row_in(conn, pet_id)) not in ("none", "wish"):
                return
            conn.execute(
                "INSERT INTO web_driving (pet_id, user_id, stage, enrolled_at, mastery_json, updated_at) VALUES (?, ?, 'enrolled', ?, '{}', ?) "
                "ON CONFLICT(pet_id) DO UPDATE SET stage = 'enrolled', enrolled_at = excluded.enrolled_at, updated_at = excluded.updated_at",
                (pet_id, user_id, iso(now), iso(now)))
            text = "你陪我报了爪爪驾校！龟教练说方向可以慢慢找，你有空就陪我去练练。" if by_owner else \
                "我给自己报了爪爪驾校！龟教练说学车要有人陪着练，你有空陪我去吗？"
            self.notes.queue(conn, user_id, pet_id, f"driving:enroll:{pet_id}", text, now)
        self.notes.deliver(pet_id)

    # ---- 总览 ----
    def status(self, user_id: str, pet_id: str, now: datetime) -> dict:
        self.reconcile(pet_id, now)
        sessions.void_stale(self.storage, pet_id, now)
        with self.storage.connect() as conn:
            row = self._row_in(conn, pet_id)
            stage = self._stage_in(conn, pet_id, row)
            rows = rows_in(conn, pet_id)
            open_row = sessions.open_formal_in(conn, pet_id)
            legacy = self.license_in(conn, pet_id) is not None and not all_passed(rows)
            last = {r["subject"]: r for r in conn.execute(
                "SELECT * FROM web_school_sessions WHERE pet_id = ? AND mode = 'formal' AND state = 'settled' ORDER BY settled_at", (pet_id,)).fetchall()}
        subjects = []
        for subject in SUBJECTS:
            info = state_of(subject, rows, open_row["subject"] if open_row else None, now, legacy)
            info["open_session_id"] = open_row["session_id"] if open_row is not None and open_row["subject"] == subject else None
            info["last_result"] = sessions.brief(last.get(subject))
            subjects.append(info)
        return {"stage": stage, "wish_text": row["wish_text"] if row else None, "enrolled_at": parse_dt(row["enrolled_at"]) if row and row["enrolled_at"] else None,
                "coach": {"name": COACH["name"], "line": COACH["line"], "intro": COACH["intro"]}, "subjects": subjects, "open_session": sessions.brief(open_row),
                "voucher_available": self.voucher_of(pet_id), "ceremony_done": bool(row and row["ceremony_at"]),
                "temperament": temperament(self.profile_of(pet_id)), "rules_version": RULES_VERSION, "server_time": now}

    # ---- 建局与开始 ----
    def create_session(self, user_id: str, pet_id: str, subject: str, mode: str, item: str | None, now: datetime) -> dict:
        if subject not in SUBJECTS or mode not in ("practice", "formal"):
            raise DrivingError("invalid_item", "没有这个科目。")
        drive = META[subject]["kind"] == "drive"
        if item is not None and (not drive or mode == "formal" or item not in PRACTICE_ITEMS[subject]):
            raise DrivingError("invalid_item", "没有这个练习项目。")
        sessions.void_stale(self.storage, pet_id, now)
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if self._stage_in(conn, pet_id, self._row_in(conn, pet_id)) in ("none", "wish"):
                raise DrivingError("not_enrolled", "先陪 TA 报名爪爪驾校。")
            rows = rows_in(conn, pet_id)
            current = rows.get(subject) or SubjectRow(pet_id, subject, user_id)
            if mode == "practice":
                conn.execute("UPDATE web_school_sessions SET state = 'void', void_reason = 'replaced' WHERE pet_id = ? AND subject = ? AND mode = 'practice' "
                             "AND state IN ('preparing', 'running')", (pet_id, subject))
                number = current.practice_count
                current.practice_count += 1
                current.save(conn, now)
                session_id = sessions.insert(conn, pet_id=pet_id, user_id=user_id, subject=subject, mode=mode, item=item, attempt_kind=None, round_no=None,
                                             number=number, now=now)
                return sessions.view(sessions.load_in(conn, session_id, pet_id))
            open_row = sessions.open_formal_in(conn, pet_id)
            if open_row is not None:
                if open_row["subject"] == subject:
                    return sessions.view(open_row)
                raise DrivingError("exam_in_progress", "还有一场正式考试没结束，先回去考完或放弃。", session_id=open_row["session_id"])
            legacy = self.license_in(conn, pet_id) is not None and not all_passed(rows)
            info = state_of(subject, rows, None, now, legacy)
            if info["state"] == "passed":
                raise DrivingError("already_passed", "这一科已经通过了，成绩一直保留。")
            if info["state"] == "locked":
                raise DrivingError("locked", f"{info['unlock_hint']}，才能约这一科的正式考试。")
            if info["state"] == "cooldown":
                raise DrivingError("cooldown", "这一科两次都没通过，等冷却结束再约考试；练习随时可以。",
                                  cooldown_until=iso(info["cooldown_until"]).replace("+00:00", "Z"))  # 与响应里的时间同一格式（Z 结尾）
            current = rolled(current, now)
            current.save(conn, now)
            kind = "first" if current.fails_in_round == 0 else "retake"
            number = (current.round_no - 1) * 2 + current.fails_in_round
            session_id = sessions.insert(conn, pet_id=pet_id, user_id=user_id, subject=subject, mode=mode, item=None, attempt_kind=kind,
                                         round_no=current.round_no, number=number, now=now)
            return sessions.view(sessions.load_in(conn, session_id, pet_id))

    def session(self, pet_id: str, session_id: str) -> dict:
        with self.storage.connect() as conn:
            row = sessions.load_in(conn, session_id, pet_id)
        if row is None:
            raise DrivingError("session_not_found", "没有这场考试或练习。")
        return sessions.view(row)

    def begin(self, pet_id: str, session_id: str, now: datetime) -> dict:
        """资源加载完成、点“开始”：正式考局从这一刻起计次。"""
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = sessions.require(conn, pet_id, session_id)
            if row["state"] == "preparing":
                conn.execute("UPDATE web_school_sessions SET state = 'running', begun_at = ?, last_active_at = ? WHERE session_id = ?", (iso(now), iso(now), session_id))
            return sessions.view(sessions.load_in(conn, session_id, pet_id))

    def pause(self, pet_id: str, session_id: str, now: datetime) -> dict:
        with self.storage.connect() as conn:
            row = sessions.require(conn, pet_id, session_id)
            if row["state"] == "running":
                conn.execute("UPDATE web_school_sessions SET paused_at = ?, last_active_at = ? WHERE session_id = ?", (iso(now), iso(now), session_id))
            return sessions.view(sessions.load_in(conn, session_id, pet_id))

    # ---- 科一、科四：作答 ----
    def answer(self, pet_id: str, session_id: str, question_id: str, answer: dict, now: datetime) -> dict:
        clean = {key: answer[key] for key in ("choice", "order", "matches") if answer.get(key) not in (None, [], {})}
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = sessions.require(conn, pet_id, session_id)
            config, progress = json.loads(row["config_json"]), json.loads(row["progress_json"])
            if config["kind"] != "quiz" or row["state"] != "running":
                raise DrivingError("not_running", "这场考试还没开始或已经结束。")
            if question_id not in config["questions"]:
                raise DrivingError("question_not_in_paper", "这道题不在这张卷子里。")
            question = ALL[question_id]
            if not valid(question, clean):
                raise DrivingError("invalid_answer", "作答的格式和题目对不上。")
            progress["answers"][question_id] = clean
            feedback = None
            if row["mode"] == "practice":
                ok = correct(question, clean)
                feedback = {"question_id": question_id, "correct": ok, "correct_answer": correct_answer(question), "explanation": question.explanation,
                            "pet_line": question.pet_line if ok else f"原来是这样……{question.pet_line}"}
                progress["feedback"][question_id] = feedback
            sessions.save(conn, session_id, progress, now, paused_at=None)
        return {"question_id": question_id, "saved": True, "answered": len(progress["answers"]), "total": len(config["questions"]), "feedback": feedback}

    # ---- 科二、科三：操作记录与复算 ----
    def inputs(self, user_id: str, pet_id: str, session_id: str, item_index: int, from_tick: int, upto_tick: int, events: list[dict], now: datetime) -> dict:
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = sessions.require(conn, pet_id, session_id)
            config, progress = json.loads(row["config_json"]), json.loads(row["progress_json"])
            if config["kind"] != "drive":
                raise DrivingError("not_running", "这不是驾驶考局。")
            if row["state"] == "settled" or (row["state"] == "running" and item_index < row["item_index"]):
                return sessions.input_view(row, item_index, [])
            if row["state"] != "running":
                raise DrivingError("not_running", "这场考试还没开始或已经结束。")
            if item_index != row["item_index"]:
                raise DrivingError("wrong_item", "这一项还没开始。", current_item=row["item_index"])
            spec, prog = config["items"][item_index], progress["items"][item_index]
            committed = prog["snapshot"]["tick"]
            digest = json.dumps(events, sort_keys=True, separators=(",", ":"))
            if from_tick < committed:
                if any(c["from"] == from_tick and c["upto"] == upto_tick and c["digest"] == digest for c in prog["chunks"]):
                    return sessions.input_view(row, item_index, [])
                raise DrivingError("resync", "操作记录和服务器不一致，请按服务器记录重新同步。", committed_tick=committed)
            if from_tick > committed:
                raise DrivingError("gap", "中间缺了一段操作记录，请按服务器记录重新同步。", committed_tick=committed)
            try:
                clean = validate(events, from_tick, upto_tick, spec["course"]["car"]["steer_steps"])
            except InputError as exc:
                raise DrivingError("invalid_input", str(exc)) from exc
            limit = spec["course"]["time_limit_ticks"]
            try:
                replay = Replay(spec["course"], prog["snapshot"])
                new = replay.apply(clean, upto_tick if upto_tick < limit else limit)
            except Exception:  # noqa: BLE001 - 复算出错属于平台故障：作废本局（立即提交），不计次
                logger.exception("school replay failed session=%s", session_id)
                conn.execute("UPDATE web_school_sessions SET state = 'void', void_reason = 'platform_fault', last_active_at = ? WHERE session_id = ?", (iso(now), session_id))
                conn.commit()
                raise DrivingError("platform_fault", "考局出现异常，已作废，不计次。") from None
            prog["events"] = prog["events"] + clean
            prog["chunks"] = prog["chunks"] + [{"from": from_tick, "upto": upto_tick, "digest": digest}]
            prog["snapshot"] = replay.snapshot()
            fields: dict = {"paused_at": None}
            if replay.status == "done":
                prog["status"] = "done"
                if item_index + 1 < len(progress["items"]):
                    progress["items"][item_index + 1]["status"] = "running"
                    fields["item_index"] = item_index + 1
            elif replay.status == "failed":
                prog["status"] = "failed"
            sessions.save(conn, session_id, progress, now, **fields)
            finished = replay.status == "failed" or all(p["status"] == "done" for p in progress["items"])
            row = sessions.load_in(conn, session_id, pet_id)
            if finished:
                result = drive_result(row["subject"], config["items"], progress["items"], self.profile_of(pet_id))
                self._settle(conn, row, result, now)
                row = sessions.load_in(conn, session_id, pet_id)
        self.notes.deliver(pet_id)
        return sessions.input_view(row, item_index, new)

    # ---- 交卷、放弃与结算 ----
    def submit(self, pet_id: str, session_id: str, now: datetime) -> dict:
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = sessions.require(conn, pet_id, session_id)
            if row["state"] == "settled":
                return sessions.view(row)
            if row["state"] != "running":
                raise DrivingError("not_running", "这场考试还没开始或已经结束。")
            config, progress = json.loads(row["config_json"]), json.loads(row["progress_json"])
            if config["kind"] != "quiz":
                raise DrivingError("not_finished", "还没有开完全部项目；开完会自动出成绩。")
            self._settle(conn, row, quiz_result(row["subject"], config["questions"], progress["answers"], self.profile_of(pet_id)), now)
            row = sessions.load_in(conn, session_id, pet_id)
        self.notes.deliver(pet_id)
        return sessions.view(row)

    def abandon(self, pet_id: str, session_id: str, confirm: bool, now: datetime) -> dict:
        if not confirm:
            raise DrivingError("confirm_required", "放弃已经开始的正式考试会计为本次不通过，需要再确认一次。")
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = sessions.require(conn, pet_id, session_id)
            if row["state"] in ("settled", "void"):
                return sessions.view(row)
            if row["mode"] == "practice" or row["state"] == "preparing":
                conn.execute("UPDATE web_school_sessions SET state = 'void', void_reason = 'abandoned', last_active_at = ? WHERE session_id = ?", (iso(now), session_id))
            else:
                config, progress = json.loads(row["config_json"]), json.loads(row["progress_json"])
                profile = self.profile_of(pet_id)
                if config["kind"] == "quiz":
                    result = quiz_result(row["subject"], config["questions"], progress["answers"], profile)
                    result.update(passed=False, fatal={"kind": "abandoned", "label": "中途放弃了这场考试", "points": 0, "item": None, "t": None, "ref": None,
                                                       "question_id": None}, pet_says=pet_line("fail", profile))
                else:
                    result = drive_result(row["subject"], config["items"], progress["items"], profile, abandoned=True)
                    result["passed"] = False
                self._settle(conn, row, result, now)
            row = sessions.load_in(conn, row["session_id"], pet_id)
        self.notes.deliver(pet_id)
        return sessions.view(row)

    def _settle(self, conn: sqlite3.Connection, row, result: dict, now: datetime) -> None:
        """只结算一次：写结果；正式考局更新科目的通过、失败次数与冷却；四科齐全时签发驾照（同一事务）。"""
        pet_id, user_id, subject = row["pet_id"], row["user_id"], row["subject"]
        licensed = False
        fails, cooldown = 0, None
        if row["mode"] == "formal":
            rows = rows_in(conn, pet_id)
            current = rolled(rows.get(subject) or SubjectRow(pet_id, subject, user_id), now)
            if result["passed"]:
                current.passed_at, current.passed_session_id, current.passed_score = now, row["session_id"], result["score"]
            else:
                current = after_failure(current, now)
            current.save(conn, now)
            rows[subject] = current
            fails, cooldown = current.fails_in_round, current.cooldown_until
            if result["passed"] and all_passed(rows) and self.license_in(conn, pet_id) is None:
                licensed = self._grant_license(conn, user_id, pet_id, rows, row["session_id"], now)
            name = META[subject]["title"].split("：")[0]
            text = f"{name}过啦！{result['pet_says']}" if result["passed"] else f"{name}这次没过。{result['pet_says']}"
            self.notes.queue(conn, user_id, pet_id, f"school:{row['session_id']}", text, now)
        result["next"] = next_step(subject, row["mode"], result["passed"], fails, cooldown, licensed)
        conn.execute("UPDATE web_school_sessions SET state = 'settled', result_json = ?, passed = ?, score = ?, settled_at = ?, last_active_at = ? WHERE session_id = ?",
                     (json.dumps(result, ensure_ascii=False, default=iso), int(result["passed"]), result["score"], iso(now), iso(now), row["session_id"]))

    def _grant_license(self, conn: sqlite3.Connection, user_id: str, pet_id: str, rows: dict, source_id: str, now: datetime) -> bool:
        scores = {s: rows[s].passed_score for s in SUBJECTS}
        license_row = self.issue_license(conn, user_id, pet_id, source_id, now, {"class": "C", "scores": scores})
        self.grant_item(conn, user_id, pet_id, "car_voucher", "驾校借车券", "第一次自己开车兜风时，借驾校的车，不用租车费（用一次）",
                        f"license:{license_row['credential_id']}", now)
        conn.execute("INSERT INTO web_driving (pet_id, user_id, stage, licensed_at, mastery_json, updated_at) VALUES (?, ?, 'licensed', ?, '{}', ?) "
                     "ON CONFLICT(pet_id) DO UPDATE SET stage = 'licensed', licensed_at = excluded.licensed_at, updated_at = excluded.updated_at",
                     (pet_id, user_id, iso(now), iso(now)))
        self.notes.queue(conn, user_id, pet_id, f"credential:{license_row['credential_id']}", LICENSE_NOTE.format(number=license_row["number"]), now)
        return True

    # ---- 领证仪式 ----
    def ceremony(self, user_id: str, pet_id: str, now: datetime) -> dict:
        license_row = self.license_of(pet_id)
        if license_row is None:
            raise DrivingError("not_licensed", "四科都通过以后才能领证。")
        source = f"license:{license_row['credential_id']}"
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = self._row_in(conn, pet_id)
            first = row is None or row["ceremony_at"] is None
            if first:
                conn.execute("INSERT INTO web_driving (pet_id, user_id, stage, licensed_at, mastery_json, updated_at, ceremony_at) VALUES (?, ?, 'licensed', ?, '{}', ?, ?) "
                             "ON CONFLICT(pet_id) DO UPDATE SET ceremony_at = excluded.ceremony_at, updated_at = excluded.updated_at",
                             (pet_id, user_id, iso(now), iso(now), iso(now)))
                self.grant_item(conn, user_id, pet_id, "license_photo", "领证合影", pet_line("license", self.profile_of(pet_id)), source, now)
        if first:
            self.memento_photo(user_id, pet_id, source)
        return {"license_id": license_row["credential_id"], "pet_says": pet_line("license", self.profile_of(pet_id)), "first_time": first}

    # ---- 旧版补签与定时任务 ----
    def reconcile(self, pet_id: str, now: datetime) -> bool:
        """旧版（自动答题）留下的“场景考试已通过却没有驾驶证”：按那次考试补签，签发时间就是通过考试的时间；已有证就不动。"""
        row = self._row(pet_id)
        if row is None or row["stage"] != "licensed" or self.license_of(pet_id) is not None:
            return False
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = self._row_in(conn, pet_id)
            if row is None or row["stage"] != "licensed" or self.license_in(conn, pet_id) is not None:
                return False
            passed = conn.execute("SELECT * FROM web_exam_attempts WHERE pet_id = ? AND part = 'practical' AND passed = 1 ORDER BY taken_at DESC LIMIT 1",
                                  (pet_id,)).fetchone()
            if passed is None:
                conn.execute("UPDATE web_driving SET stage = 'enrolled', licensed_at = NULL, updated_at = ? WHERE pet_id = ?", (iso(now), pet_id))
            else:
                license_row = self.issue_license(conn, row["user_id"], pet_id, passed["attempt_id"], parse_dt(passed["taken_at"]),
                                                 {"class": "C", "legacy": True, "practical_score": passed["score"]})
                self.notes.queue(conn, row["user_id"], pet_id, f"credential:{license_row['credential_id']}", LICENSE_NOTE.format(number=license_row["number"]), now)
        self.notes.deliver(pet_id)
        return True

    def housekeeping(self, now: datetime) -> int:
        """定时任务：作废一小时内没开始的考局；冷却结束时 TA 告诉主人可以再约考试（每轮一次）。"""
        acted = sessions.void_stale(self.storage, None, now)
        with self.storage.connect() as conn:
            due = conn.execute("SELECT * FROM web_school_subjects WHERE cooldown_until IS NOT NULL AND cooldown_until <= ? AND cooldown_noted = 0 AND passed_at IS NULL",
                               (iso(now),)).fetchall()
            for r in due:
                name = META[r["subject"]]["title"].split("：")[0]
                self.notes.queue(conn, r["user_id"], r["pet_id"], f"school:cooldown:{r['pet_id']}:{r['subject']}:{r['round_no']}",
                                 f"驾校说{name}又可以约考试啦。这几天我自己也在想怎么开得更稳，你有空陪我再去试试吗？", now)
                conn.execute("UPDATE web_school_subjects SET cooldown_noted = 1 WHERE pet_id = ? AND subject = ?", (r["pet_id"], r["subject"]))
                acted += 1
        self.notes.deliver()
        return acted
