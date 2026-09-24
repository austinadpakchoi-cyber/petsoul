"""同行影音契约：作品/版本/许可能力、服务器播放锚点、控制租约与实际参与。

媒体会话有独立时钟，不驱动交通到达；图片生成 MediaJob 是另一实体，不在此处。
锚点公式（服务端与客户端共用语义）：
  playing:            position = clamp(anchor.position_ms + elapsed_server_ms × rate, 0, duration)
  paused/interrupted: position = anchor.position_ms
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from .common import DataOrigin, WebModel


class MediaKind(str, Enum):
    audio = "audio"
    video = "video"


class MediaAvailability(str, Enum):
    in_app_sync = "in_app_sync"
    external_link = "external_link"
    unavailable = "unavailable"


class LicenseStatus(str, Enum):
    self_generated_test = "self_generated_test"
    licensed = "licensed"
    pending = "pending"
    unknown = "unknown"


class MediaLicense(WebModel):
    status: LicenseStatus
    allows_in_app_playback: bool
    allows_sync: bool
    public_release_allowed: bool = False
    regions: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    note: str | None = None


class MediaAsset(WebModel):
    media_id: str
    kind: MediaKind
    title: str
    creator: str | None = None
    edition: str = Field(description="作品版本；版本不同不能标同步")
    duration_ms: int
    src_url: str | None = None
    poster_url: str | None = None
    external_url: str | None = None
    availability: MediaAvailability
    license: MediaLicense
    data_origin: DataOrigin


class MediaSessionState(str, Enum):
    playing = "playing"
    paused = "paused"
    ended = "ended"
    interrupted = "interrupted"


class ResumePolicy(str, Enum):
    pet_continues = "pet_continues"
    save_shared_progress = "save_shared_progress"
    stop = "stop"


class InterruptReason(str, Enum):
    arrival = "arrival"
    driving = "driving"
    content_unavailable = "content_unavailable"
    joint_pause = "joint_pause"


class MediaAnchor(WebModel):
    position_ms: int
    server_time: datetime
    playback_rate: float = 1.0


class ControlLease(WebModel):
    holder_device_id: str | None = None
    lease_expires_at: datetime | None = None


class CompanionSession(WebModel):
    session_id: str
    activity_id: str
    pet_id: str
    media: MediaAsset
    state: MediaSessionState
    anchor: MediaAnchor
    revision: int
    resume_policy: ResumePolicy
    control: ControlLease | None = None
    saved_progress_ms: int | None = None
    interrupt_reason: InterruptReason | None = None
    video_allowed: bool = Field(description="驾驶中为 false：服务端拒绝切换到视频")
    data_origin: DataOrigin


class ParticipationMode(str, Enum):
    not_joined = "not_joined"
    joining = "joining"
    synced = "synced"
    solo = "solo"
    buffering = "buffering"
    blocked = "blocked"
    failed = "failed"
    left = "left"


class Participation(WebModel):
    """只有 synced 且在允许偏差内、心跳未过期才累计 counted_ms；页面停留不等于陪伴。"""

    session_id: str
    device_id: str
    mode: ParticipationMode
    since: datetime
    last_heartbeat_at: datetime | None = None
    counted_ms: int = 0


class CompanionCommandKind(str, Enum):
    pause = "pause"
    resume = "resume"
    seek = "seek"
    restart = "restart"


class CompanionJoinRequest(WebModel):
    device_id: str
    mode: ParticipationMode = ParticipationMode.joining


class CompanionLeaveRequest(WebModel):
    device_id: str


class CompanionCommandRequest(WebModel):
    """需 Idempotency-Key；session_revision 过期返回 409 VERSION_CONFLICT。"""

    device_id: str
    command: CompanionCommandKind
    session_revision: int
    position_ms: int | None = None


class CompanionHeartbeatRequest(WebModel):
    device_id: str
    player_state: ParticipationMode
    position_ms: int
    media_edition: str
    client_time: datetime


__all__ = [
    "MediaKind",
    "MediaAvailability",
    "LicenseStatus",
    "MediaLicense",
    "MediaAsset",
    "MediaSessionState",
    "ResumePolicy",
    "InterruptReason",
    "MediaAnchor",
    "ControlLease",
    "CompanionSession",
    "ParticipationMode",
    "Participation",
    "CompanionCommandKind",
    "CompanionJoinRequest",
    "CompanionLeaveRequest",
    "CompanionCommandRequest",
    "CompanionHeartbeatRequest",
]
