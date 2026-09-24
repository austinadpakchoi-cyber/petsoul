"""管理端路由共享件：会话解析、逐请求权限核查、CSRF 与来源校验、操作号、访问留痕。

默认拒绝：每个受保护的路由都必须显式声明它要哪条权限（`Depends(needs(Permission.X))`）。
没写权限的路由拿不到 principal，也就进不了任何数据——不存在"忘了加检查就变成公开接口"。
"""

from __future__ import annotations

import hmac
import re
from typing import Callable

from fastapi import APIRouter, Request, Response

from ...web_admin import AdminServices
from ...web_admin.commands import ActorContext
from ...web_admin.errors import ADMIN_API_PREFIX, AdminAPIError, AdminErrorCode, request_id_of
from ...web_admin.identity import AdminPrincipal
from ...web_admin.permissions import Permission

CSRF_HEADER = "X-Admin-CSRF-Token"
IDEMPOTENCY_HEADER = "Idempotency-Key"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_KEY_RE = re.compile(r"^[A-Za-z0-9_\-:.]{8,128}$")


def admin_router(tag: str) -> APIRouter:
    return APIRouter(prefix=ADMIN_API_PREFIX, tags=[f"admin:{tag}"])


def admin_of(request: Request) -> AdminServices:
    services = getattr(request.app.state, "admin", None)
    if services is None:
        raise AdminAPIError(AdminErrorCode.not_configured, "这个环境没有装配运营后台。", 503)
    if not services.tables_ready:
        raise AdminAPIError(AdminErrorCode.not_configured, "后台数据表尚未创建（迁移 1500/1510 未应用）。", 503,
                            details={"missing": "admin_* tables"})
    return services


def set_session_cookies(response: Response, services: AdminServices, issued) -> None:
    max_age = services.settings.session_ttl_seconds
    secure = services.settings.cookie_secure
    # host-only（不设 domain）：员工 cookie 不会被带到玩家站点。
    response.set_cookie(services.settings.cookie_name, issued.cookie_value, max_age=max_age, httponly=True,
                        secure=secure, samesite="strict", path="/")
    response.set_cookie(services.settings.csrf_cookie_name, issued.csrf_token, max_age=max_age, httponly=False,
                        secure=secure, samesite="strict", path="/")


def clear_session_cookies(response: Response, services: AdminServices) -> None:
    secure = services.settings.cookie_secure
    response.delete_cookie(services.settings.cookie_name, path="/", secure=secure, httponly=True, samesite="strict")
    response.delete_cookie(services.settings.csrf_cookie_name, path="/", secure=secure, samesite="strict")


def resolve_staff(request: Request) -> AdminPrincipal:
    cached = getattr(request.state, "admin_principal", None)
    if cached is not None:
        return cached
    services = admin_of(request)
    token = request.cookies.get(services.settings.cookie_name)
    if not token:
        raise AdminAPIError.auth_required()
    principal = services.identity.resolve(token)
    request.state.admin_principal = principal
    return principal


def check_csrf(request: Request) -> None:
    """写操作：双提交 cookie + 精确来源校验。两道都过才放行。"""
    if request.method not in UNSAFE_METHODS:
        return
    services = admin_of(request)
    cookie_value = request.cookies.get(services.settings.csrf_cookie_name, "")
    header_value = request.headers.get(CSRF_HEADER, "")
    if not cookie_value or not header_value or not hmac.compare_digest(cookie_value, header_value):
        raise AdminAPIError(AdminErrorCode.csrf_failed, "页面已过期，请刷新后重试。", 403)
    origin = request.headers.get("origin") or ""
    if origin and services.settings.allowed_origins and origin not in services.settings.allowed_origins:
        raise AdminAPIError(AdminErrorCode.csrf_failed, "请求来源不在允许清单内。", 403, details={"origin": origin})


def operation_id(request: Request) -> str:
    key = request.headers.get(IDEMPOTENCY_HEADER, "").strip()
    if not key:
        raise AdminAPIError(AdminErrorCode.idempotency_key_required, "写操作必须带 Idempotency-Key 请求头。", 400)
    if not _KEY_RE.match(key):
        raise AdminAPIError.validation("Idempotency-Key 格式不正确。", field="Idempotency-Key")
    return key


def needs(permission: Permission, *, write: bool = False) -> Callable[[Request], AdminPrincipal]:
    """逐请求核权。被拒绝也写审计（status=denied），这是"谁想干什么被挡下了"的证据。"""

    def dependency(request: Request) -> AdminPrincipal:
        services = admin_of(request)
        principal = resolve_staff(request)
        if write:
            check_csrf(request)
        if not principal.mfa_satisfied:
            raise AdminAPIError(AdminErrorCode.mfa_enrollment_required,
                                "本环境要求员工启用二次验证；请先完成入册再操作。", 403,
                                details={"reason": "mfa_enrollment_required"})
        if permission not in principal.staff.permissions:
            services.audit.record(action=f"denied:{request.method} {request.url.path}", status="denied",
                                  actor_staff_id=principal.staff.staff_id, actor_username=principal.staff.username,
                                  permission=permission.value, request_id=request_id_of(request),
                                  changes={"roles": list(principal.staff.roles)})
            raise AdminAPIError.forbidden(permission.value)
        return principal

    return dependency


def needs_any(*permissions: Permission) -> Callable[[Request], AdminPrincipal]:
    """几条读权限任一即可（例如待领养居民：客服与内容运营都要看）。仍然逐请求核、被拒绝也写审计。"""

    def dependency(request: Request) -> AdminPrincipal:
        services = admin_of(request)
        principal = resolve_staff(request)
        if not principal.mfa_satisfied:
            raise AdminAPIError(AdminErrorCode.mfa_enrollment_required,
                                "本环境要求员工启用二次验证；请先完成入册再操作。", 403,
                                details={"reason": "mfa_enrollment_required"})
        if not any(p in principal.staff.permissions for p in permissions):
            wanted = "|".join(p.value for p in permissions)
            services.audit.record(action=f"denied:{request.method} {request.url.path}", status="denied",
                                  actor_staff_id=principal.staff.staff_id, actor_username=principal.staff.username,
                                  permission=wanted, request_id=request_id_of(request),
                                  changes={"roles": list(principal.staff.roles)})
            raise AdminAPIError.forbidden(wanted)
        return principal

    return dependency


def signed_in(request: Request) -> AdminPrincipal:
    """只要求「已登录、且过了二次验证要求」、不要求具体权限的读接口用这个（词表、员工名字这类不含玩家数据的东西）。
    仍然默认拒绝：没有员工会话就 401，二次验证没过就 403。"""
    principal = resolve_staff(request)
    if not principal.mfa_satisfied:
        raise AdminAPIError(AdminErrorCode.mfa_enrollment_required,
                            "本环境要求员工启用二次验证；请先完成入册再操作。", 403,
                            details={"reason": "mfa_enrollment_required"})
    return principal


def context(request: Request, principal: AdminPrincipal) -> ActorContext:
    return ActorContext(principal=principal, request_id=request_id_of(request), operation_id=operation_id(request))


def trace_read(request: Request, principal: AdminPrincipal, permission: Permission, action: str,
               target_kind: str, target_id: str, **changes) -> None:
    """合法访问留痕：查看个人数据要留下谁在什么时候看了什么。它是审计写入，不是业务写入。"""
    admin_of(request).audit.record(action=action, status="allowed", actor_staff_id=principal.staff.staff_id,
                                   actor_username=principal.staff.username, permission=permission.value,
                                   target_kind=target_kind, target_id=target_id, request_id=request_id_of(request),
                                   changes=changes or None)
