"""CompanionMedia 服务边界（R0 只定义接口；实现由用户分配的同行影音模块窗口完成）。

实现要求（见 TRANSPORT-COMPANION-SYSTEM.md §7–§9）：
- 三份状态分开：宠物活动（TravelActivity，交通模块）/ 媒体会话 / 主人参与；
- 服务器只保存合法作品引用与锚点，不替虚拟宠物拉流；
- 控制命令校验 用户/宠物/会话/revision/控制租约/幂等键；旧 revision → VERSION_CONFLICT；
- 驾驶阶段拒绝视频（DRIVING_BLOCKS_VIDEO）；抵达事件中断会话并保存进度，不等播放器回调；
- 外链作品 availability=external_link，永不标同步；
- 与图片生成 MediaJob 是不同实体；
- 迁移编号区间 0800–0899。
"""

from __future__ import annotations

from typing import Protocol

from ..schemas.web.companion_media import (
    CompanionCommandRequest,
    CompanionHeartbeatRequest,
    CompanionJoinRequest,
    CompanionSession,
    Participation,
)


class CompanionMediaService(Protocol):
    def get_session(self, user_id: str, session_id: str) -> CompanionSession: ...

    def join(self, user_id: str, session_id: str, request: CompanionJoinRequest) -> Participation: ...

    def command(
        self, user_id: str, session_id: str, request: CompanionCommandRequest, idempotency_key: str
    ) -> CompanionSession: ...

    def heartbeat(self, user_id: str, session_id: str, request: CompanionHeartbeatRequest) -> Participation: ...

    def leave(self, user_id: str, session_id: str, device_id: str) -> Participation: ...
