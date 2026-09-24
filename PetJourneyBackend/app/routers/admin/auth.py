"""员工登录 / 退出 / 当前会话 / 二次验证入册 / 员工与角色管理。

没有任何"初始管理员可以从网页创建"的入口：第一个账号只能由
`python -m app.web_admin.bootstrap` 在服务器上创建（见那个模块的说明）。
密码重置也只走已登录的平台负责人，不提供邮件找回或万能恢复码。
"""

from __future__ import annotations

from fastapi import Depends, Request, Response

from ...schemas.admin import AdminLoginRequest, MfaActivateRequest, StaffCreateRequest, StaffRolesRequest, StaffStatusRequest
from ...web_admin import ADMIN_BACKEND_VERSION
from ...web_admin.errors import AdminAPIError, AdminErrorCode, request_id_of
from ...web_admin.identity import AdminPrincipal, StaffExists
from ...web_admin.permissions import Permission, WRITE_PERMISSIONS, role_catalog
from ._shared import (
    admin_of,
    admin_router,
    check_csrf,
    clear_session_cookies,
    context,
    needs,
    resolve_staff,
    set_session_cookies,
)

router = admin_router("auth")


def _staff_view(staff) -> dict:
    return {"staff_id": staff.staff_id, "username": staff.username, "display_name": staff.display_name,
            "status": staff.status, "mfa_enabled": staff.mfa_enabled, "roles": list(staff.roles),
            "version": staff.version, "created_at": staff.created_at, "last_login_at": staff.last_login_at,
            "permissions": sorted(p.value for p in staff.permissions),
            "write_permissions": sorted(p.value for p in staff.permissions if p in WRITE_PERMISSIONS)}


def _client_key(request: Request) -> str:
    return request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "unknown")


@router.get("/meta")
def meta(request: Request) -> dict:
    """未登录也能读：只给环境、版本与是否已初始化，不含任何业务或用户数据。"""
    services = getattr(request.app.state, "admin", None)
    settings = request.app.state.settings
    return {
        "admin_version": ADMIN_BACKEND_VERSION,
        "environment": getattr(settings, "web_environment", "dev"),
        "configured": bool(services and services.configured),
        "tables_ready": bool(services and services.tables_ready),
        "initialized": bool(services and services.tables_ready and services.identity.any_staff_exists()),
        "require_mfa": bool(services and services.settings.require_mfa),
        "roles": role_catalog(),
    }


@router.post("/auth/login")
def login(body: AdminLoginRequest, request: Request, response: Response) -> dict:
    services = admin_of(request)
    if not services.configured:
        raise AdminAPIError(AdminErrorCode.not_configured, "这个环境没有配置会话密钥，无法登录。", 503)
    try:
        staff = services.identity.authenticate(body.username, body.password, body.mfa_code, _client_key(request))
    except AdminAPIError as exc:
        services.audit.record(action="staff.login", status="denied", actor_username=body.username[:64],
                              outcome=exc.code.value, request_id=request_id_of(request))
        raise
    issued = services.identity.issue_session(staff.staff_id, client_hint=_client_key(request))
    set_session_cookies(response, services, issued)
    services.audit.record(action="staff.login", status="succeeded", actor_staff_id=staff.staff_id,
                          actor_username=staff.username, outcome="session_issued", request_id=request_id_of(request),
                          changes={"session": issued.session_id[:8] + "…", "roles": list(staff.roles)})  # 只留前缀：会话标识不进审计原文
    return {"staff": _staff_view(staff), "expires_at": issued.expires_at,
            "mfa_enrollment_required": services.settings.require_mfa and not staff.mfa_enabled}


@router.post("/auth/logout")
def logout(request: Request, response: Response) -> dict:
    services = admin_of(request)
    check_csrf(request)
    principal = resolve_staff(request)
    services.identity.revoke_session(principal.session_id, "logout")
    clear_session_cookies(response, services)
    services.audit.record(action="staff.logout", status="succeeded", actor_staff_id=principal.staff.staff_id,
                          actor_username=principal.staff.username, request_id=request_id_of(request))
    return {"ok": True}


@router.get("/auth/session")
def session(request: Request) -> dict:
    services = admin_of(request)
    principal = resolve_staff(request)
    return {"staff": _staff_view(principal.staff), "expires_at": principal.expires_at,
            "mfa_satisfied": principal.mfa_satisfied,
            "mfa_enrollment_required": services.settings.require_mfa and not principal.staff.mfa_enabled,
            "environment": getattr(request.app.state.settings, "web_environment", "dev"),
            "admin_version": ADMIN_BACKEND_VERSION}


@router.post("/auth/mfa/enroll")
def mfa_enroll(request: Request) -> dict:
    """入册只对自己：拿到密钥与 otpauth 链接。**密钥不进审计**，只记"开始入册"这件事。"""
    services = admin_of(request)
    check_csrf(request)
    principal = resolve_staff(request)
    secret, uri = services.identity.begin_mfa_enrollment(principal.staff.staff_id)
    services.audit.record(action="staff.mfa_enroll_started", status="succeeded", actor_staff_id=principal.staff.staff_id,
                          actor_username=principal.staff.username, request_id=request_id_of(request))
    return {"secret": secret, "otpauth_uri": uri,
            "note": "把密钥加进验证器应用，再用当前验证码激活。密钥只在这一次返回，不会再次显示，也不会进审计。"}


@router.post("/auth/mfa/activate")
def mfa_activate(body: MfaActivateRequest, request: Request) -> dict:
    services = admin_of(request)
    check_csrf(request)
    principal = resolve_staff(request)
    services.identity.activate_mfa(principal.staff.staff_id, body.code)
    services.audit.record(action="staff.mfa_activated", status="succeeded", actor_staff_id=principal.staff.staff_id,
                          actor_username=principal.staff.username, request_id=request_id_of(request))
    return {"mfa_enabled": True}


# ---- 员工与角色（平台负责人）----
@router.get("/staff")
def list_staff(request: Request, principal: AdminPrincipal = Depends(needs(Permission.STAFF_MANAGE))) -> dict:
    return {"staff": [_staff_view(item) for item in admin_of(request).identity.list_staff()], "roles": role_catalog()}


@router.post("/staff", status_code=201)
def create_staff(body: StaffCreateRequest, request: Request,
                 principal: AdminPrincipal = Depends(needs(Permission.STAFF_MANAGE, write=True))) -> dict:
    services = admin_of(request)
    ctx = context(request, principal)
    try:
        staff = services.identity.create_staff(body.username, body.password, body.display_name, body.roles,
                                               created_by=principal.staff.staff_id)
    except StaffExists as exc:
        raise AdminAPIError(AdminErrorCode.conflict, "这个员工名已经有人用了。", 409) from exc
    services.audit.record(action="staff.create", status="succeeded", actor_staff_id=principal.staff.staff_id,
                          actor_username=principal.staff.username, permission=Permission.STAFF_MANAGE.value,
                          target_kind="staff", target_id=staff.staff_id, operation_id=ctx.operation_id,
                          request_id=ctx.request_id, changes={"roles": list(staff.roles), "username": staff.username})
    return {"staff": _staff_view(staff)}


@router.put("/staff/{staff_id}/roles")
def set_roles(staff_id: str, body: StaffRolesRequest, request: Request,
              principal: AdminPrincipal = Depends(needs(Permission.STAFF_MANAGE, write=True))) -> dict:
    services = admin_of(request)
    ctx = context(request, principal)
    before = services.identity.staff(staff_id)
    if before is None:
        raise AdminAPIError.not_found("这位员工")
    staff = services.identity.set_roles(staff_id, body.roles, expected_version=body.expected_version,
                                        actor=principal.staff.staff_id)
    services.audit.record(action="staff.set_roles", status="succeeded", actor_staff_id=principal.staff.staff_id,
                          actor_username=principal.staff.username, permission=Permission.STAFF_MANAGE.value,
                          target_kind="staff", target_id=staff_id, operation_id=ctx.operation_id, request_id=ctx.request_id,
                          changes={"from": list(before.roles), "to": list(staff.roles)})
    return {"staff": _staff_view(staff), "note": "改角色会同时断开这位员工当前所有会话，撤权立即生效。"}


@router.put("/staff/{staff_id}/status")
def set_status(staff_id: str, body: StaffStatusRequest, request: Request,
               principal: AdminPrincipal = Depends(needs(Permission.STAFF_MANAGE, write=True))) -> dict:
    services = admin_of(request)
    ctx = context(request, principal)
    if staff_id == principal.staff.staff_id and body.status == "disabled":
        raise AdminAPIError(AdminErrorCode.conflict, "不能停用自己，避免把自己锁在外面。", 409)
    staff = services.identity.set_status(staff_id, body.status, expected_version=body.expected_version,
                                         actor=principal.staff.staff_id)
    services.audit.record(action="staff.set_status", status="succeeded", actor_staff_id=principal.staff.staff_id,
                          actor_username=principal.staff.username, permission=Permission.STAFF_MANAGE.value,
                          target_kind="staff", target_id=staff_id, reason=body.reason, operation_id=ctx.operation_id,
                          request_id=ctx.request_id, changes={"status": body.status})
    return {"staff": _staff_view(staff), "note": "停用会立刻撤销这位员工所有会话。"}
