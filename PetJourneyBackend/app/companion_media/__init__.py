"""同行影音领域（R0：服务边界 + 锚点/租约/参与纯函数；会话实现待用户分配）。"""

from .anchor import (
    HEARTBEAT_MAX_AGE_S,
    SYNC_TOLERANCE_MS,
    lease_allows,
    participation_counts,
    position_at,
    video_allowed,
)
from .service import CompanionMediaService

__all__ = [
    "HEARTBEAT_MAX_AGE_S",
    "SYNC_TOLERANCE_MS",
    "CompanionMediaService",
    "lease_allows",
    "participation_counts",
    "position_at",
    "video_allowed",
]
