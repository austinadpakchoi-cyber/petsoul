"""接待服务实现（引导便笺模式）。草稿私有、24 小时可恢复；确认后草稿全文清除，只保留主人选择保存的叮嘱。

- 未确认候选只存在于草稿，不写旧 memories、不调用 update_pet_dna；
- 确认：draft_revision 必须匹配；(session, revision) 唯一，重复提交返回原确认；
- “不保存”的内容不进入任何长期记录；“只留在这里”只作为主人私有记录（target=keep_here，无任何宠物用途授权）；
- 更正生成新版本并 supersede 旧版本；撤回/删除先撤销授权（停止使用），再使待生成任务失效。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Callable

from ..schemas.web.common import DataOrigin
from ..schemas.web.home import HomeWelcome
from ..schemas.web.identity import OnboardingState, OnboardingStep
from ..schemas.web.reception import (
    CandidateKind,
    CandidateState,
    CandidateSubject,
    CareNote,
    CareNoteSlot,
    CleanupState,
    IntakeCandidate,
    IntakeConfirmationRequest,
    IntakeConfirmationResult,
    MemoryCorrectionAction,
    MemoryCorrectionRequest,
    MemoryCorrectionResult,
    MemoryGrant,
    MemoryProjection,
    MemoryPurpose,
    PersistState,
    ReceptionBranch,
    ReceptionHost,
    ReceptionMode,
    ReceptionSession,
    ReceptionStatus,
    ReceptionTurn,
    SaveTarget,
    TurnSpeaker,
)
from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from ..web_platform.runtime_epochs import bump_in
from ..web_platform.tasks import WebTaskQueue, supersede_pending_in_tx
from . import guided
from .policy import build_home_welcome, project_memory

DRAFT_TTL = timedelta(hours=24)
PRIVATE_ONLY = {CandidateKind.owner_private, CandidateKind.inference}


class ReceptionError(Exception):
    def __init__(self, reason: str, message: str, current: int | None = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.current = current


class WebReceptionService:
    def __init__(self, storage: JourneyStorage, tasks: WebTaskQueue) -> None:
        self.chat = None  # 主人选择“用模型回应”时使用；只生成接待员的回应，不写便笺
        self.storage = storage
        self.tasks = tasks
        self.pet_name_of: Callable[[str], str] = lambda pet_id: "TA"
        self.on_state: Callable[[str, str, bool], None] = lambda user_id, session_id, skipped: None
        self.onboarding_of: Callable[[str], OnboardingState] = lambda user_id: OnboardingState(step=OnboardingStep.reception_optional)

    def host(self, mode: ReceptionMode = ReceptionMode.guided_notes) -> ReceptionHost:
        disclosure = guided.HOST_DISCLOSURE
        if mode is ReceptionMode.model_conversation:
            disclosure = guided.MODEL_DISCLOSURE.format(provider=getattr(self.chat, "provider_label", "对话模型"))
        return ReceptionHost(host_id="host-reception", display_name=guided.HOST_NAME, role_label=guided.HOST_ROLE, avatar_url=None, is_ai=True, disclosure=disclosure)

    def model_available(self) -> bool:
        return self.chat is not None and bool(getattr(self.chat, "available", False))

    def _model_follow_up(self, session: ReceptionSession, turns: list[dict]) -> str | None:
        from ..web_communicator.persona import clean_reply  # 同一套输出清洗（无链接、不自称模型）

        try:
            result = self.chat.complete(guided.model_messages(session.branch, self.pet_name_of(session.pet_id), turns), max_tokens=120, temperature=0.7)
        except Exception:  # noqa: BLE001 - 不可用/超限/超时：回到固定引导
            return None
        return clean_reply(result.text)

    # ---- 草稿 ----
    def _row(self, session_id: str):
        with self.storage.connect() as conn:
            return conn.execute("SELECT * FROM web_reception_sessions WHERE session_id = ?", (session_id,)).fetchone()

    def _dto(self, row, now: datetime) -> ReceptionSession:
        status = ReceptionStatus(row["status"])
        turns = [ReceptionTurn(**t) for t in json.loads(row["turns_json"])]
        candidates = [IntakeCandidate(**c) for c in json.loads(row["candidates_json"])]
        if status in (ReceptionStatus.active, ReceptionStatus.awaiting_confirmation) and parse_dt(row["expires_at"]) <= now:
            self._purge(row["session_id"], ReceptionStatus.expired, now)
            status, turns, candidates = ReceptionStatus.expired, [], []
        return ReceptionSession(session_id=row["session_id"], pet_id=row["pet_id"], branch=ReceptionBranch(row["branch"]), mode=ReceptionMode(row["mode"]),
                                status=status, host=self.host(ReceptionMode(row["mode"])), turns=turns, candidates=candidates, draft_revision=row["draft_revision"],
                                draft_expires_at=parse_dt(row["expires_at"]), data_origin=DataOrigin.live)

    def _purge(self, session_id: str, status: ReceptionStatus, now: datetime) -> None:
        with self.storage.connect() as conn:
            conn.execute("UPDATE web_reception_sessions SET status = ?, turns_json = '[]', candidates_json = '[]', updated_at = ? WHERE session_id = ?",
                         (status.value, iso(now), session_id))

    def start(self, user_id: str, pet_id: str, branch: ReceptionBranch, now: datetime | None = None, use_model: bool = False) -> ReceptionSession:
        now = now or utcnow()
        with self.storage.connect() as conn:
            row = conn.execute(
                "SELECT * FROM web_reception_sessions WHERE user_id = ? AND pet_id = ? AND status IN ('active', 'awaiting_confirmation') "
                "AND expires_at > ? ORDER BY created_at DESC LIMIT 1", (user_id, pet_id, iso(now))).fetchone()
        if row is not None:
            return self._dto(row, now)
        session_id = f"rs-{uuid.uuid4().hex[:12]}"
        mode = ReceptionMode.model_conversation if use_model and self.model_available() else ReceptionMode.guided_notes
        opening = ReceptionTurn(turn_id="t1", seq=1, speaker=TurnSpeaker.host, text=guided.opening_line(branch, self.pet_name_of(pet_id)), created_at=now,
                                composed_by="guided")
        with self.storage.connect() as conn:
            conn.execute(
                "INSERT INTO web_reception_sessions (session_id, user_id, pet_id, branch, mode, status, draft_revision, turns_json, candidates_json, "
                "created_at, updated_at, expires_at) VALUES (?, ?, ?, ?, ?, 'active', 1, ?, '[]', ?, ?, ?)",
                (session_id, user_id, pet_id, branch.value, mode.value, json.dumps([opening.model_dump(mode="json")], ensure_ascii=False), iso(now), iso(now),
                 iso(now + DRAFT_TTL)),
            )
        self.on_state(user_id, session_id, False)
        return self.get(user_id, session_id, now)

    def get(self, user_id: str, session_id: str, now: datetime | None = None) -> ReceptionSession:
        row = self._row(session_id)
        if row is None or row["user_id"] != user_id:
            raise ReceptionError("not_found", "没有找到这次接待。")
        return self._dto(row, now or utcnow())

    def add_turn(self, user_id: str, session_id: str, text: str, expected_revision: int, now: datetime | None = None) -> ReceptionSession:
        now = now or utcnow()
        session = self.get(user_id, session_id, now)
        if session.status not in (ReceptionStatus.active, ReceptionStatus.awaiting_confirmation):
            raise ReceptionError("closed", "这次接待已经结束或过期，可以重新开始。")
        if session.draft_revision != expected_revision:
            raise ReceptionError("version_conflict", "便笺在别处更新过，请刷新。", session.draft_revision)
        turns = [t.model_dump(mode="json") for t in session.turns]
        candidates = [c.model_dump(mode="json") for c in session.candidates]
        owner_turn_id = f"t{len(turns) + 1}"
        turns.append(ReceptionTurn(turn_id=owner_turn_id, seq=len(turns) + 1, speaker=TurnSpeaker.owner, text=text, created_at=now).model_dump(mode="json"))
        for segment, kind, subject, slot, value in guided.suggestions_for(text, session.branch):
            candidates.append(IntakeCandidate(candidate_id=f"c-{uuid.uuid4().hex[:8]}", kind=kind, subject=subject, text=segment, source_turn_id=owner_turn_id,
                                              source_excerpt=segment, needs_clarification=kind is CandidateKind.inference, suggested_slot=slot,
                                              suggested_slot_value=value, state=CandidateState.unconfirmed).model_dump(mode="json"))
        owner_turns = sum(1 for t in turns if t["speaker"] == "owner")
        reply = self._model_follow_up(session, turns) if session.mode is ReceptionMode.model_conversation and self.model_available() else None
        turns.append(ReceptionTurn(turn_id=f"t{len(turns) + 1}", seq=len(turns) + 1, speaker=TurnSpeaker.host, text=reply or guided.follow_up(owner_turns - 1),
                                   created_at=now, composed_by="model" if reply else "guided").model_dump(mode="json"))
        with self.storage.connect() as conn:
            updated = conn.execute(
                "UPDATE web_reception_sessions SET turns_json = ?, candidates_json = ?, draft_revision = draft_revision + 1, status = 'awaiting_confirmation', "
                "updated_at = ? WHERE session_id = ? AND draft_revision = ?",
                (json.dumps(turns, ensure_ascii=False), json.dumps(candidates, ensure_ascii=False), iso(now), session_id, expected_revision),
            ).rowcount
        if updated != 1:
            raise ReceptionError("version_conflict", "便笺在别处更新过，请刷新。")
        return self.get(user_id, session_id, now)

    def skip(self, user_id: str, session_id: str, now: datetime | None = None) -> ReceptionSession:
        now = now or utcnow()
        self.get(user_id, session_id, now)
        self._purge(session_id, ReceptionStatus.skipped, now)
        self.on_state(user_id, session_id, True)
        return self.get(user_id, session_id, now)

    # ---- 确认 ----
    def confirm(self, user_id: str, request: IntakeConfirmationRequest, now: datetime | None = None) -> IntakeConfirmationResult:
        now = now or utcnow()
        with self.storage.connect() as conn:
            done = conn.execute("SELECT * FROM web_intake_confirmations WHERE session_id = ? AND draft_revision = ? AND user_id = ?",
                                (request.session_id, request.draft_revision, user_id)).fetchone()
        if done is not None:
            return self._result(user_id, done["confirmation_id"], request.session_id, request.draft_revision)
        session = self.get(user_id, request.session_id, now)
        if session.status not in (ReceptionStatus.active, ReceptionStatus.awaiting_confirmation):
            raise ReceptionError("closed", "这次接待已经结束或过期。")
        if session.draft_revision != request.draft_revision:
            raise ReceptionError("version_conflict", "便笺在别处更新过，请刷新后再确认。", session.draft_revision)
        by_id = {c.candidate_id: c for c in session.candidates}
        confirmation_id = f"cf-{uuid.uuid4().hex[:12]}"
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO web_intake_confirmations (confirmation_id, user_id, session_id, draft_revision, created_at) VALUES (?, ?, ?, ?, ?)",
                         (confirmation_id, user_id, request.session_id, request.draft_revision, iso(now)))
            for decision in request.decisions:
                candidate = by_id.get(decision.candidate_id)
                if candidate is None:
                    raise ReceptionError("unknown_candidate", "便笺里没有这一条。")
                if decision.target is SaveTarget.do_not_save:
                    continue
                if decision.target is SaveTarget.give_to_pet and candidate.kind in PRIVATE_ONLY:
                    raise ReceptionError("not_allowed", "心里话和推测不能交给 TA。")
                purposes = decision.purposes if decision.target is SaveTarget.give_to_pet else []
                note_id = f"cn-{uuid.uuid4().hex[:12]}"
                conn.execute(
                    "INSERT INTO web_care_notes (note_id, user_id, pet_id, kind, subject, text, target, purposes_json, slot, slot_value, version, confirmed_at, "
                    "supersedes_note_id, revoked_at, confirmation_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, NULL, NULL, ?)",
                    (note_id, user_id, session.pet_id, candidate.kind.value, candidate.subject.value, decision.text.strip(), decision.target.value,
                     json.dumps([p.value for p in purposes]), decision.slot.value if decision.slot else None, decision.slot_value, iso(now), confirmation_id),
                )
                for purpose in purposes:
                    conn.execute("INSERT INTO web_memory_grants (grant_id, note_id, note_version, purpose, user_id, pet_id, granted_at) VALUES (?, ?, 1, ?, ?, ?, ?)",
                                 (f"gr-{uuid.uuid4().hex[:12]}", note_id, purpose.value, user_id, session.pet_id, iso(now)))
            # 草稿全文清除：“不保存”的内容不留任何副本；保存下来的只有上面的叮嘱。
            conn.execute("UPDATE web_reception_sessions SET status = 'completed', turns_json = '[]', candidates_json = '[]', updated_at = ? WHERE session_id = ?",
                         (iso(now), request.session_id))
        self.on_state(user_id, request.session_id, False)
        return self._result(user_id, confirmation_id, request.session_id, request.draft_revision)

    def _result(self, user_id: str, confirmation_id: str, session_id: str, revision: int) -> IntakeConfirmationResult:
        notes = [n for n in self._notes(user_id) if self._confirmation_of(n.note_id) == confirmation_id]
        grants = [g for g in self._grants(user_id) if g.note_id in {n.note_id for n in notes}]
        return IntakeConfirmationResult(confirmation_id=confirmation_id, session_id=session_id, draft_revision=revision, persist_state=PersistState.persisted,
                                        notes=notes, grants=grants, onboarding=self.onboarding_of(user_id), data_origin=DataOrigin.live)

    def _confirmation_of(self, note_id: str) -> str | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT confirmation_id FROM web_care_notes WHERE note_id = ?", (note_id,)).fetchone()
        return row["confirmation_id"] if row else None

    # ---- 叮嘱与投影 ----
    def _notes(self, user_id: str, pet_id: str | None = None) -> list[CareNote]:
        query = "SELECT * FROM web_care_notes WHERE user_id = ?" + (" AND pet_id = ?" if pet_id else "") + " ORDER BY confirmed_at"
        with self.storage.connect() as conn:
            rows = conn.execute(query, (user_id, pet_id) if pet_id else (user_id,)).fetchall()
        return [CareNote(note_id=r["note_id"], pet_id=r["pet_id"], kind=CandidateKind(r["kind"]), subject=CandidateSubject(r["subject"]), text=r["text"],
                         target=SaveTarget(r["target"]), purposes=[MemoryPurpose(p) for p in json.loads(r["purposes_json"])],
                         slot=CareNoteSlot(r["slot"]) if r["slot"] else None, slot_value=r["slot_value"], version=r["version"],
                         confirmed_at=parse_dt(r["confirmed_at"]), supersedes_note_id=r["supersedes_note_id"],
                         revoked_at=parse_dt(r["revoked_at"]) if r["revoked_at"] else None) for r in rows]

    def _grants(self, user_id: str, pet_id: str | None = None) -> list[MemoryGrant]:
        query = "SELECT * FROM web_memory_grants WHERE user_id = ?" + (" AND pet_id = ?" if pet_id else "")
        with self.storage.connect() as conn:
            rows = conn.execute(query, (user_id, pet_id) if pet_id else (user_id,)).fetchall()
        return [MemoryGrant(grant_id=r["grant_id"], note_id=r["note_id"], note_version=r["note_version"], purpose=MemoryPurpose(r["purpose"]),
                            granted_at=parse_dt(r["granted_at"]), revoked_at=parse_dt(r["revoked_at"]) if r["revoked_at"] else None) for r in rows]

    def notes(self, user_id: str, pet_id: str) -> list[CareNote]:
        return self._notes(user_id, pet_id)

    def projection(self, user_id: str, pet_id: str, purpose: MemoryPurpose, now: datetime | None = None) -> MemoryProjection:
        """唯一的记忆读取出口：按 (user_id, pet_id) 取回后，再由 MemoryPolicy 在任何消费前过滤。"""
        return project_memory(pet_id=pet_id, purpose=purpose, notes=self._notes(user_id, pet_id), grants=self._grants(user_id, pet_id), now=now or utcnow())

    def home_welcome(self, user_id: str, pet_id: str) -> HomeWelcome | None:
        projection = self.projection(user_id, pet_id, MemoryPurpose.home_interaction)
        if not projection.items:
            return None
        with self.storage.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n, MAX(confirmation_id) AS c FROM web_intake_confirmations WHERE user_id = ?", (user_id,)).fetchone()
        return build_home_welcome(projection, projection_version=max(1, int(row["n"])), confirmation_id=row["c"])

    def correct(self, user_id: str, note_id: str, request: MemoryCorrectionRequest, now: datetime | None = None) -> MemoryCorrectionResult:
        now = now or utcnow()
        note = next((n for n in self._notes(user_id) if n.note_id == note_id), None)
        if note is None:
            raise ReceptionError("not_found", "没有找到这条叮嘱。")
        if note.revoked_at is not None:
            raise ReceptionError("revoked", "这条叮嘱已经撤回。")
        if note.version != request.expected_version:
            raise ReceptionError("version_conflict", "这条叮嘱刚更新过，请刷新。", note.version)
        new_note = None
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            # 1) 先停止使用：撤销旧版本全部授权
            conn.execute("UPDATE web_memory_grants SET revoked_at = ? WHERE note_id = ? AND revoked_at IS NULL", (iso(now), note_id))
            conn.execute("UPDATE web_care_notes SET revoked_at = ? WHERE note_id = ?", (iso(now), note_id))
            if request.action is MemoryCorrectionAction.erase:
                conn.execute("UPDATE web_care_notes SET text = '', slot_value = NULL WHERE note_id = ?", (note_id,))
            elif request.action is MemoryCorrectionAction.correct and request.new_text:
                new_id = f"cn-{uuid.uuid4().hex[:12]}"
                new_text = request.new_text.strip()
                slot_value = (request.new_slot_value or "").strip() or guided.rederive_slot_value(note.slot, new_text)
                conn.execute(
                    "INSERT INTO web_care_notes (note_id, user_id, pet_id, kind, subject, text, target, purposes_json, slot, slot_value, version, confirmed_at, "
                    "supersedes_note_id, revoked_at, confirmation_id) SELECT ?, user_id, pet_id, kind, subject, ?, target, purposes_json, slot, ?, version + 1, ?, "
                    "note_id, NULL, confirmation_id FROM web_care_notes WHERE note_id = ?",
                    (new_id, new_text, slot_value if note.slot else None, iso(now), note_id),
                )
                for purpose in note.purposes:
                    conn.execute("INSERT INTO web_memory_grants (grant_id, note_id, note_version, purpose, user_id, pet_id, granted_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                 (f"gr-{uuid.uuid4().hex[:12]}", new_id, note.version + 1, purpose.value, user_id, note.pet_id, iso(now)))
                new_note = new_id
            # 2) 同一个事务里使依赖这条叮嘱的待生成任务失效：停止使用与任务作废一起提交，不留“授权撤了、任务还在跑”的窗口
            affected = supersede_pending_in_tx(conn, f"reception:note:{note_id}:", "care note corrected or revoked", now=now)
            bump_in(conn, note.pet_id, "privacy_epoch", now)  # 授权变了：正在思考或还没发布的内容要按新版本复核
        created = next((n for n in self._notes(user_id) if n.note_id == new_note), None) if new_note else None
        return MemoryCorrectionResult(note_id=note_id, new_note=created,
                                      cleanup=CleanupState.cleanup_done if request.action is MemoryCorrectionAction.erase else CleanupState.usage_stopped,
                                      affected_task_ids=affected)
