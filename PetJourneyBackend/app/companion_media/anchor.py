"""同行影音的锚点、控制租约与参与计量纯函数。媒体时钟独立，不驱动交通抵达。"""

from __future__ import annotations

from datetime import datetime

from ..schemas.web.companion_media import (
    ControlLease,
    MediaAnchor,
    MediaKind,
    MediaSessionState,
    ParticipationMode,
)
from ..schemas.web.transport import TravellerRole

# 待测目标，不是已达成承诺（TRANSPORT-COMPANION-SYSTEM §8）。
SYNC_TOLERANCE_MS = {MediaKind.audio: 1_000, MediaKind.video: 2_000}
HEARTBEAT_MAX_AGE_S = 30


def position_at(anchor: MediaAnchor, state: MediaSessionState, duration_ms: int, now: datetime) -> int:
    if state is not MediaSessionState.playing:
        return max(0, min(anchor.position_ms, duration_ms))
    elapsed_ms = (now - anchor.server_time).total_seconds() * 1000
    return int(max(0, min(anchor.position_ms + elapsed_ms * anchor.playback_rate, duration_ms)))


def video_allowed(role: TravellerRole) -> bool:
    """宠物驾驶时只允许音频；乘客、步行停车或停驻时可看视频。"""
    return role is not TravellerRole.driver


def lease_allows(lease: ControlLease | None, device_id: str, now: datetime) -> bool:
    if lease is None or lease.holder_device_id is None or lease.lease_expires_at is None:
        return True
    if lease.lease_expires_at <= now:
        return True
    return lease.holder_device_id == device_id


def participation_counts(
    mode: ParticipationMode,
    kind: MediaKind,
    drift_ms: int,
    heartbeat_age_s: float,
) -> bool:
    """只有 synced、偏差在容忍内且心跳未过期才累计陪伴时长。"""
    if mode is not ParticipationMode.synced:
        return False
    if heartbeat_age_s > HEARTBEAT_MAX_AGE_S:
        return False
    return abs(drift_ms) <= SYNC_TOLERANCE_MS[kind]
