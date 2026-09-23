"""同行影音会话：读取、加入、共同控制（revision + 控制租约 + 幂等）、心跳参与、离开。与图片生成 MediaJob 无关。"""

from __future__ import annotations

from fastapi import Depends, Request

from ...companion_media.sessions import MediaError
from ...schemas.web.common import Capability, CapabilityStatus, WebErrorCode
from ...schemas.web.companion_media import (
    CompanionCommandRequest,
    CompanionHeartbeatRequest,
    CompanionJoinRequest,
    CompanionLeaveRequest,
    CompanionSession,
    Participation,
)
from ...web_platform import WebAPIError, WebPrincipal, require_csrf, require_idempotency_key, require_principal
from ._shared import cap, idempotent, web_of, web_router

router = web_router("companion_media")


def capabilities(settings) -> list[Capability]:
    return [
        cap("companion_media.session", "companion_media", CapabilityStatus.available),
        cap("companion_media.sync", "companion_media", CapabilityStatus.available, "服务器锚点对齐 + 实际播放判定；真机后台/锁屏未验证"),
        cap("companion_media.licensed_catalog", "companion_media", CapabilityStatus.not_implemented, "只有自制测试素材；无已授权公开作品清单"),
    ]


def _translate(exc: MediaError) -> WebAPIError:
    if exc.reason == "not_found":
        return WebAPIError.not_found("这个同行会话")
    if exc.reason == "version_conflict":
        return WebAPIError.version_conflict(current=exc.current_revision)
    if exc.reason == "lease_held":
        return WebAPIError(WebErrorCode.control_lease_held, exc.message, 409)
    return WebAPIError(WebErrorCode.conflict, exc.message, 409, details={"reason": exc.reason})


@router.get("/media/sessions/{session_id}", response_model=CompanionSession)
def get_media_session(session_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> CompanionSession:
    try:
        return web_of(request).media.session(principal.user_id, session_id)
    except MediaError as exc:
        raise _translate(exc) from exc


@router.post("/media/sessions/{session_id}/join", response_model=Participation, dependencies=[Depends(require_csrf)])
def join_media_session(session_id: str, body: CompanionJoinRequest, request: Request, principal: WebPrincipal = Depends(require_principal)) -> Participation:
    try:
        return web_of(request).media.join(principal.user_id, session_id, body.device_id)
    except MediaError as exc:
        raise _translate(exc) from exc


@router.post("/media/sessions/{session_id}/commands", response_model=CompanionSession, dependencies=[Depends(require_csrf)])
def command_media_session(session_id: str, body: CompanionCommandRequest, request: Request, principal: WebPrincipal = Depends(require_principal),
                          idempotency_key: str = Depends(require_idempotency_key)) -> CompanionSession:
    def handler() -> CompanionSession:
        try:
            return web_of(request).media.command(principal.user_id, session_id, body)
        except MediaError as exc:
            raise _translate(exc) from exc

    return idempotent(request, principal, f"media.command:{session_id}", idempotency_key, body.model_dump(mode="json"), CompanionSession, handler)


@router.post("/media/sessions/{session_id}/heartbeat", response_model=Participation, dependencies=[Depends(require_csrf)])
def heartbeat_media_session(session_id: str, body: CompanionHeartbeatRequest, request: Request, principal: WebPrincipal = Depends(require_principal)) -> Participation:
    try:
        return web_of(request).media.heartbeat(principal.user_id, session_id, body)
    except MediaError as exc:
        raise _translate(exc) from exc


@router.post("/media/sessions/{session_id}/leave", response_model=Participation, dependencies=[Depends(require_csrf)])
def leave_media_session(session_id: str, body: CompanionLeaveRequest, request: Request, principal: WebPrincipal = Depends(require_principal)) -> Participation:
    try:
        return web_of(request).media.leave(principal.user_id, session_id, body.device_id)
    except MediaError as exc:
        raise _translate(exc) from exc
