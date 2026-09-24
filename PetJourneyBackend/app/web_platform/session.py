"""统一会话入口：网页 HttpOnly cookie（写操作 CSRF 双提交）+ 旧 iOS Bearer 兼容。

R0 只提供解析/签发/清除原语与 FastAPI 依赖；注册、登录、口令哈希与会话吊销
由身份模块实现（见 MODULE-MAP identity）。没有任何开发用假登录。
"""

from __future__ import annotations

import hmac
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import jwt
from fastapi import Request, Response

from ..auth import AuthError
from ..schemas.web.common import AuthMethod, WebErrorCode
from .errors import WebAPIError

SESSION_COOKIE = "petsoul_session"
CSRF_COOKIE = "petsoul_csrf"
CSRF_HEADER = "X-CSRF-Token"
WEB_SESSION_ISSUER = "petsoul-web"
WEB_SESSION_TYPE = "web_session"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# 身份模块可注册吊销检查（例如 web_sessions 表的 revoked_at）；返回 True 表示会话仍有效。
SessionRevocationCheck = Callable[[str, str], bool]


@dataclass(frozen=True, slots=True)
class WebPrincipal:
    user_id: str
    auth_method: AuthMethod
    session_id: str | None = None
    expires_at: datetime | None = None

    @property
    def uses_cookie(self) -> bool:
        return self.auth_method is AuthMethod.web_password


@dataclass(frozen=True, slots=True)
class IssuedWebSession:
    token: str
    session_id: str
    csrf_token: str
    expires_at: datetime


def issue_web_session(secret: str, user_id: str, ttl_seconds: int) -> IssuedWebSession:
    now = int(time.time())
    session_id = f"ws_{uuid.uuid4().hex}"
    exp = now + ttl_seconds
    token = jwt.encode(
        {"sub": user_id, "sid": session_id, "typ": WEB_SESSION_TYPE, "iss": WEB_SESSION_ISSUER, "iat": now, "exp": exp},
        secret,
        algorithm="HS256",
    )
    return IssuedWebSession(
        token=token,
        session_id=session_id,
        csrf_token=secrets.token_urlsafe(24),
        expires_at=datetime.fromtimestamp(exp, tz=timezone.utc),
    )


def set_session_cookies(response: Response, issued: IssuedWebSession, *, secure: bool) -> None:
    max_age = max(0, int(issued.expires_at.timestamp() - time.time()))
    response.set_cookie(
        SESSION_COOKIE, issued.token, max_age=max_age, httponly=True, secure=secure, samesite="lax", path="/"
    )
    # CSRF cookie 需被前端读取后回填请求头，因此不设 HttpOnly。
    response.set_cookie(
        CSRF_COOKIE, issued.csrf_token, max_age=max_age, httponly=False, secure=secure, samesite="lax", path="/"
    )


def clear_session_cookies(response: Response, *, secure: bool) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", secure=secure, httponly=True, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=secure, samesite="lax")


def _decode_cookie(secret: str, token: str) -> WebPrincipal:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"], issuer=WEB_SESSION_ISSUER)
    except jwt.PyJWTError as exc:
        raise WebAPIError.session_expired() from exc
    if payload.get("typ") != WEB_SESSION_TYPE or not payload.get("sub"):
        raise WebAPIError.session_expired()
    return WebPrincipal(
        user_id=str(payload["sub"]),
        auth_method=AuthMethod.web_password,
        session_id=payload.get("sid"),
        expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc),
    )


def resolve_principal(request: Request) -> WebPrincipal | None:
    """无凭据返回 None；有凭据但无效/过期抛 SESSION_EXPIRED（不静默降级成匿名）。"""
    cached = getattr(request.state, "web_principal", None)
    if cached is not None:
        return cached
    state = request.app.state
    settings = state.settings
    principal: WebPrincipal | None = None

    authorization = request.headers.get("authorization", "")
    cookie_token = request.cookies.get(SESSION_COOKIE)
    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            user_id = state.auth_service.decode_session_token(token)
        except AuthError as exc:
            raise WebAPIError.session_expired() from exc
        principal = WebPrincipal(user_id=user_id, auth_method=AuthMethod.apple_bearer)
    elif cookie_token:
        if not settings.auth_secret:
            raise WebAPIError.session_expired()
        principal = _decode_cookie(settings.auth_secret, cookie_token)
        check: SessionRevocationCheck | None = getattr(state, "web_session_revocation_check", None)
        if check is not None and principal.session_id and not check(principal.user_id, principal.session_id):
            raise WebAPIError.session_expired()

    if principal is not None and state.storage.get_user(principal.user_id) is None:
        raise WebAPIError.session_expired()
    request.state.web_principal = principal
    return principal


def optional_principal(request: Request) -> WebPrincipal | None:
    return resolve_principal(request)


def require_principal(request: Request) -> WebPrincipal:
    principal = resolve_principal(request)
    if principal is None:
        raise WebAPIError.auth_required()
    return principal


def require_csrf(request: Request) -> None:
    """cookie 会话的写操作必须带与 cookie 一致的 X-CSRF-Token；Bearer 客户端不受 CSRF 影响。"""
    if request.method not in UNSAFE_METHODS:
        return
    principal = resolve_principal(request)
    if principal is None or not principal.uses_cookie:
        return
    cookie_value = request.cookies.get(CSRF_COOKIE, "")
    header_value = request.headers.get(CSRF_HEADER, "")
    if not cookie_value or not header_value or not hmac.compare_digest(cookie_value, header_value):
        raise WebAPIError(WebErrorCode.csrf_failed, "页面已过期，请刷新后再试。", 403)

