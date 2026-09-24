"""同行影音会话服务：锚点（服务器时间）、共同控制（revision + 控制租约 + 幂等由路由层保证）、到站中断保存、
主人实际参与计量。媒体时钟独立，不影响交通到达。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from ..schemas.web.common import DataOrigin
from ..schemas.web.companion_media import (
    CompanionCommandKind,
    CompanionCommandRequest,
    CompanionHeartbeatRequest,
    CompanionSession,
    ControlLease,
    InterruptReason,
    MediaAnchor,
    MediaSessionState,
    Participation,
    ParticipationMode,
    ResumePolicy,
)
from ..schemas.web.companion_media import MediaKind
from ..schemas.web.transport import TravellerRole
from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from .anchor import HEARTBEAT_MAX_AGE_S, lease_allows, participation_counts, position_at, video_allowed
from .schedule import LegWindow, ScheduledActivity, activity_by_index

LEASE_SECONDS = 60


class MediaError(Exception):
    def __init__(self, reason: str, message: str, current_revision: int | None = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.current_revision = current_revision


@dataclass(frozen=True)
class LegContext:
    window: LegWindow
    user_id: str
    pet_id: str
    quiet: bool


LegLookup = Callable[[str], LegContext | None]


def parse_session_id(session_id: str) -> tuple[str, int] | None:
    if not session_id.startswith("ms-") or "-" not in session_id[3:]:
        return None
    leg_id, _, index = session_id[3:].rpartition("-")
    return (leg_id, int(index)) if index.isdigit() else None


class WebCompanionMedia:
    def __init__(self, storage: JourneyStorage, leg_lookup: LegLookup) -> None:
        self.storage = storage
        self.leg_lookup = leg_lookup
        # 家庭成员都能陪 TA 一起听/看（装配时注入成员关系）；没注入时只有发起旅程的那位
        self.can_view_pet: Callable[[str, str], bool] | None = None

    # ---- 会话 ----
    def _resolve(self, user_id: str, session_id: str) -> tuple[LegContext, ScheduledActivity]:
        parsed = parse_session_id(session_id)
        ctx = self.leg_lookup(parsed[0]) if parsed else None
        allowed = ctx is not None and (self.can_view_pet(user_id, ctx.pet_id) if self.can_view_pet else ctx.user_id == user_id)
        if parsed is None or not allowed:
            raise MediaError("not_found", "没有找到这个同行会话。")
        activity = activity_by_index(ctx.window, parsed[1], ctx.quiet)
        if activity is None or activity.media is None or activity.session_id != session_id:
            raise MediaError("not_found", "没有找到这个同行会话。")
        return ctx, activity

    def _row(self, session_id: str):
        with self.storage.connect() as conn:
            return conn.execute("SELECT * FROM web_media_sessions WHERE session_id = ?", (session_id,)).fetchone()

    def session(self, user_id: str, session_id: str, now: datetime | None = None) -> CompanionSession:
        now = now or utcnow()
        ctx, activity = self._resolve(user_id, session_id)
        if now < activity.starts_at:
            raise MediaError("not_started", "这段还没开始。")
        return self._effective(ctx, activity, self._row(session_id), now)

    def _effective(self, ctx: LegContext, activity: ScheduledActivity, row, now: datetime) -> CompanionSession:
        media = activity.media
        assert media is not None
        duration = media.duration_ms
        if row is not None:
            state = MediaSessionState(row["state"])
            anchor = MediaAnchor(position_ms=row["anchor_position_ms"], server_time=parse_dt(row["anchor_server_time"]), playback_rate=row["playback_rate"])
            revision = row["revision"]
            lease = ControlLease(holder_device_id=row["lease_device"], lease_expires_at=parse_dt(row["lease_expires_at"]) if row["lease_expires_at"] else None)
        else:
            state, revision, lease = MediaSessionState.playing, 1, None
            anchor = MediaAnchor(position_ms=0, server_time=activity.starts_at, playback_rate=1.0)
        saved = None
        reason = InterruptReason.joint_pause if state is MediaSessionState.paused else None
        leg_end = ctx.window.ends_at
        if state in (MediaSessionState.playing, MediaSessionState.paused):
            end_at = min(now, leg_end)
            pos = position_at(anchor, state, duration, end_at)
            natural_done = state is MediaSessionState.playing and anchor.server_time + timedelta(milliseconds=(duration - anchor.position_ms) / max(anchor.playback_rate, 0.01)) <= end_at
            if natural_done:
                state, anchor, reason = MediaSessionState.ended, MediaAnchor(position_ms=duration, server_time=end_at), None
            elif now >= leg_end:
                # 到站优先于媒体：中断并保存进度，不等待播放器回调。
                state, anchor, saved, reason = MediaSessionState.interrupted, MediaAnchor(position_ms=pos, server_time=leg_end), pos, InterruptReason.arrival
        return CompanionSession(
            session_id=activity.session_id or "",
            activity_id=activity.activity_id,
            pet_id=ctx.pet_id,
            media=media,
            state=state,
            anchor=anchor,
            revision=revision,
            resume_policy=ResumePolicy.save_shared_progress if media.kind is MediaKind.video else ResumePolicy.pet_continues,
            control=lease,
            saved_progress_ms=saved,
            interrupt_reason=reason,
            video_allowed=video_allowed(TravellerRole(ctx.window.role)),
            data_origin=DataOrigin.live,
        )

    def command(self, user_id: str, session_id: str, request: CompanionCommandRequest, now: datetime | None = None) -> CompanionSession:
        now = now or utcnow()
        ctx, activity = self._resolve(user_id, session_id)
        current = self._effective(ctx, activity, self._row(session_id), now)
        if current.revision != request.session_revision:
            raise MediaError("version_conflict", "会话已被更新，请刷新后再试。", current.revision)
        if current.state in (MediaSessionState.interrupted, MediaSessionState.ended):
            raise MediaError("finished", "这一段已经到站或播完了。")
        if not lease_allows(current.control, request.device_id, now):
            raise MediaError("lease_held", "另一台设备正在控制播放。")
        duration = current.media.duration_ms
        position = position_at(current.anchor, current.state, duration, now)
        if request.command is CompanionCommandKind.pause:
            state, position_ms = MediaSessionState.paused, position
        elif request.command is CompanionCommandKind.resume:
            state, position_ms = MediaSessionState.playing, position
        elif request.command is CompanionCommandKind.seek:
            state, position_ms = current.state, max(0, min(request.position_ms or 0, duration - 1))
        else:
            state, position_ms = MediaSessionState.playing, 0
        with self.storage.connect() as conn:
            conn.execute(
                "INSERT INTO web_media_sessions (session_id, user_id, pet_id, leg_id, activity_index, state, anchor_position_ms, anchor_server_time, "
                "playback_rate, revision, lease_device, lease_expires_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1.0, ?, ?, ?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET state = excluded.state, anchor_position_ms = excluded.anchor_position_ms, "
                "anchor_server_time = excluded.anchor_server_time, revision = excluded.revision, lease_device = excluded.lease_device, "
                "lease_expires_at = excluded.lease_expires_at, updated_at = excluded.updated_at WHERE web_media_sessions.revision = ?",
                (session_id, user_id, ctx.pet_id, ctx.window.leg_id, activity.index, state.value, position_ms, iso(now), current.revision + 1,
                 request.device_id, iso(now + timedelta(seconds=LEASE_SECONDS)), iso(now), current.revision),
            )
        return self.session(user_id, session_id, now)

    # ---- 参与 ----
    def _participation(self, session_id: str, device_id: str):
        with self.storage.connect() as conn:
            return conn.execute("SELECT * FROM web_media_participation WHERE session_id = ? AND device_id = ?", (session_id, device_id)).fetchone()

    def _save_participation(self, session_id: str, user_id: str, device_id: str, mode: ParticipationMode, since: datetime, beat: datetime | None, counted: int) -> Participation:
        with self.storage.connect() as conn:
            conn.execute(
                "INSERT INTO web_media_participation (session_id, user_id, device_id, mode, since, last_heartbeat_at, counted_ms) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(session_id, device_id) DO UPDATE SET mode = excluded.mode, last_heartbeat_at = excluded.last_heartbeat_at, counted_ms = excluded.counted_ms",
                (session_id, user_id, device_id, mode.value, iso(since), iso(beat) if beat else None, counted),
            )
        return Participation(session_id=session_id, device_id=device_id, mode=mode, since=since, last_heartbeat_at=beat, counted_ms=counted)

    def join(self, user_id: str, session_id: str, device_id: str, now: datetime | None = None) -> Participation:
        now = now or utcnow()
        self._resolve(user_id, session_id)
        row = self._participation(session_id, device_id)
        return self._save_participation(session_id, user_id, device_id, ParticipationMode.joining, parse_dt(row["since"]) if row else now, None, row["counted_ms"] if row else 0)

    def heartbeat(self, user_id: str, session_id: str, request: CompanionHeartbeatRequest, now: datetime | None = None) -> Participation:
        now = now or utcnow()
        ctx, activity = self._resolve(user_id, session_id)
        session = self._effective(ctx, activity, self._row(session_id), now)
        row = self._participation(session_id, request.device_id)
        counted = row["counted_ms"] if row else 0
        last = parse_dt(row["last_heartbeat_at"]) if row and row["last_heartbeat_at"] else None
        drift = request.position_ms - position_at(session.anchor, session.state, session.media.duration_ms, now)
        if last is not None and request.media_edition == session.media.edition and session.state is MediaSessionState.playing:
            age = (now - last).total_seconds()
            if participation_counts(request.player_state, session.media.kind, drift, age):
                counted += int(min(age, HEARTBEAT_MAX_AGE_S) * 1000)
        since = parse_dt(row["since"]) if row else now
        return self._save_participation(session_id, user_id, request.device_id, request.player_state, since, now, counted)

    def leave(self, user_id: str, session_id: str, device_id: str, now: datetime | None = None) -> Participation:
        now = now or utcnow()
        self._resolve(user_id, session_id)
        row = self._participation(session_id, device_id)
        return self._save_participation(session_id, user_id, device_id, ParticipationMode.left, parse_dt(row["since"]) if row else now,
                                        parse_dt(row["last_heartbeat_at"]) if row and row["last_heartbeat_at"] else None, row["counted_ms"] if row else 0)

    def counted_for_legs(self, user_id: str, leg_ids: list[str]) -> list[tuple[str, int]]:
        """某段旅程里实际同行（按有界心跳累计）的会话与时长，用于生成共同回忆。"""
        if not leg_ids:
            return []
        with self.storage.connect() as conn:
            rows = conn.execute(
                "SELECT session_id, MAX(counted_ms) AS counted FROM web_media_participation WHERE user_id = ? GROUP BY session_id", (user_id,)
            ).fetchall()
        result = []
        for row in rows:
            parsed = parse_session_id(row["session_id"])
            if parsed and parsed[0] in leg_ids and row["counted"] > 0:
                result.append((row["session_id"], int(row["counted"])))
        return result

    def session_state_override(self, session_id: str) -> str | None:
        row = self._row(session_id)
        return row["state"] if row else None
