"""玩家侧读运营产物：平台公告、自己提交的举报的处理结果。

这两条路由（`GET /announcements`、`GET /reports/mine`）由运营后台窗口 adm1 建，
当时它在文件说明里写明「响应 DTO 还没进 `app/schemas/web/`（那是共享契约，归 I）」，
所以一直是 `response_model=None`——**契约里只有路由表一行，没有类型**。
后果是前端只能在自己的 feature 里定义本地类型，再从 `shared/services/types.ts` 反向引用它，
**层次是倒的**（6c2b 2026-09-24 报）。本文件补上这一段。

**枚举取值必须与实现保持一致，而这件事没有任何东西会主动提醒**：
`AnnouncementSeverity` 对应 `web_admin/content_types.py` 的 `ANNOUNCEMENT_SEVERITIES`，
`ReportOutcome` 对应 `web_admin/moderation.py` 的 `OUTCOMES` 的 code。
**两边都由 `tests/test_web_moderation_contract.py` 的双向不变量用例锁住**——
实现多一个码会红、契约多一个码也会红。不靠「这次核对过了」。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from .common import WebModel

__all__ = [
    "AnnouncementSeverity", "AnnouncementItem", "AnnouncementSource", "AnnouncementFeed",
    "ReportStatus", "ReportOutcome", "ReportOutcomeItem", "MyReports",
]


class AnnouncementSeverity(str, Enum):
    info = "info"
    notice = "notice"
    maintenance = "maintenance"


class AnnouncementSource(str, Enum):
    live = "live"                    # 读到的是运营后台已发布的那一版
    not_installed = "not_installed"  # 后台未装配：返回空列表，**不是「没有公告」而是「读不到」**


class AnnouncementItem(WebModel):
    item_id: str
    slug: str
    revision: int  # 证据：玩家读到的是哪一版
    title: str
    body: str
    severity: AnnouncementSeverity
    link: str | None = None
    image_asset_id: str | None = None
    image_url: str | None = None
    effective_at: datetime | None = None
    expires_at: datetime | None = None


class AnnouncementFeed(WebModel):
    announcements: list[AnnouncementItem] = []
    as_of: datetime
    source: AnnouncementSource


class ReportStatus(str, Enum):
    received = "received"  # 还没处理
    resolved = "resolved"  # 已有处理动作


class ReportOutcome(str, Enum):
    """举报人能看到的**结局**，只有四种。

    **不含**员工身份与内部判断原因——那是运营后台的内部信息，
    这条路由的文件说明里写明了这一条边界。
    """

    received = "received"
    content_removed = "content_removed"
    no_violation_found = "no_violation_found"
    content_restored = "content_restored"


class ReportOutcomeItem(WebModel):
    report_id: str
    target_kind: str
    target_id: str
    reason: str
    created_at: datetime
    status: ReportStatus
    outcome: ReportOutcome
    resolved_at: datetime | None = None
    message: str  # 固定措辞，由服务端给；前端不要自己按 outcome 拼文案


class MyReports(WebModel):
    reports: list[ReportOutcomeItem] = []
    note: str
