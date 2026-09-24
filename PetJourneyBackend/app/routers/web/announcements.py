"""玩家侧读取平台公告（/api/v1/web/announcements）。

这是运营后台发布闭环的**消费端**：它读的就是 `admin_content_items.live_revision` 指向的那一版，
和后台"玩家现在读到什么"用的是同一个函数（`AdminContent.live_announcements`），不是另算一遍。

纯读：不推进世界、不调模型、不写任何业务表。没有已发布内容时返回空列表——空就是空，不造占位公告。

归属说明（如实记）：本文件由运营后台窗口 adm1 新增，当前由 `install_admin_platform` 挂载，
尚未登记进 `app/routers/web/__init__.py` 的 `WEB_ROUTER_MODULES`（那是共享入口，归 I）。
响应 DTO 由 I 按本文件的返回构造补进了共享契约（`app/schemas/web/moderation.py` 的 `AnnouncementFeed`，2026-09-24），
这里挂上 `response_model`；取值与实现的一致性由 `tests/test_web_moderation_contract.py` 双向锁住。
"""

from __future__ import annotations

from fastapi import Depends, Request

from ...schemas.web.common import Capability, CapabilityStatus
from ...schemas.web.moderation import AnnouncementFeed
from ...utils import utcnow
from ...web_platform import WebAPIError, WebPrincipal, optional_principal
from ._shared import cap, web_router

router = web_router("announcements")


def capabilities(settings) -> list[Capability]:
    return [cap("platform.announcements", "web_admin", CapabilityStatus.available,
                "运营后台发布的平台公告；玩家端通讯器读取（顶部细条与全部公告页），按已发布版本号消费"),
            cap("platform.public_assets", "web_admin", CapabilityStatus.available,
                "运营素材库里标为公开的图片；内部素材与已下架素材一律 404")]


# response_model=None：响应 DTO 还没进 `app/schemas/web/`（那是共享契约，归 I），
# 不声明 response_model，契约生成器就只多一行路由、不会去引用一个它不认识的类型。
@router.get("/assets/{asset_id}", response_model=None)
def public_asset(asset_id: str, request: Request):
    """公开素材的**唯一**玩家侧入口。

    只给 `usage_scope='public'` 且 `status='active'` 的素材；内部素材、已下架素材一律当不存在（404），
    不区分"没有"和"不给你看"。文件路径由素材服务解析并校验落在素材根目录内，rel_path 做不成穿越。
    """
    from fastapi.responses import FileResponse

    admin = getattr(request.app.state, "admin", None)
    if admin is None:
        raise WebAPIError.not_found("这个素材")
    if admin.assets.public_asset(asset_id) is None:
        raise WebAPIError.not_found("这个素材")
    found = admin.assets.file_path(asset_id)
    if found is None:
        raise WebAPIError.not_found("这个素材")
    path, content_type = found
    return FileResponse(path, media_type=content_type,
                        headers={"Cache-Control": "public, max-age=600", "X-Content-Type-Options": "nosniff"})


@router.get("/announcements", response_model=AnnouncementFeed)
def announcements(request: Request, principal: WebPrincipal | None = Depends(optional_principal)) -> dict:
    """已生效、未过期的公告。未登录只看到 audience=all 的；登录后还能看到 audience=signed_in 的。"""
    admin = getattr(request.app.state, "admin", None)
    if admin is None:
        return {"announcements": [], "as_of": utcnow(), "source": "not_installed"}
    items = admin.content.live_announcements(signed_in=principal is not None)
    return {
        "announcements": [
            {
                "item_id": item["item_id"],
                "slug": item["slug"],
                "revision": item["revision"],  # 证据：玩家读到的是哪一版
                "title": item["title"],
                "body": item["body"],
                "severity": item["severity"],
                "link": item["link"],
                "image_asset_id": item["image_asset_id"],
                "image_url": item["image_url"],
                "effective_at": item["effective_at"],
                "expires_at": item["expires_at"],
            }
            for item in items
        ],
        "as_of": utcnow(),
        "source": "live",
    }
