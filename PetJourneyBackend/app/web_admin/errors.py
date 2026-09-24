"""管理端错误：稳定 code + 可读说明 + request_id，形态与 `/api/v1/web` 一致，但**不共用异常类型**。

为什么单独一份：`web_platform.errors.install_error_handlers` 里的处理器只认 `/api/v1/web` 前缀，
其余路径交回 FastAPI 默认处理器 —— 默认的 422 处理器会把 **input 原样回显**，那意味着管理端登录
请求体里的口令可能进到响应里。所以管理端自己装一套：只接管 `/api/v1/admin`，其余原样委托给
安装前就已经存在的那个处理器（在 `install_admin_errors` 里捕获，不覆盖玩家侧行为）。
"""

from __future__ import annotations

import logging
import uuid
from enum import Enum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

ADMIN_API_PREFIX = "/api/v1/admin"
REQUEST_ID_HEADER = "X-Request-ID"
logger = logging.getLogger("petsoul.admin")


class AdminErrorCode(str, Enum):
    auth_required = "AUTH_REQUIRED"
    session_expired = "SESSION_EXPIRED"
    csrf_failed = "CSRF_FAILED"
    invalid_credentials = "INVALID_CREDENTIALS"
    mfa_required = "MFA_REQUIRED"
    mfa_enrollment_required = "MFA_ENROLLMENT_REQUIRED"
    forbidden = "FORBIDDEN"
    not_found = "NOT_FOUND"
    validation_failed = "VALIDATION_FAILED"
    conflict = "CONFLICT"
    version_conflict = "VERSION_CONFLICT"
    idempotency_key_required = "IDEMPOTENCY_KEY_REQUIRED"
    idempotency_key_reused = "IDEMPOTENCY_KEY_REUSED"
    not_recoverable = "NOT_RECOVERABLE"
    rate_limited = "RATE_LIMITED"
    not_configured = "NOT_CONFIGURED"
    internal_error = "INTERNAL_ERROR"


_STATUS_TO_CODE = {
    400: AdminErrorCode.validation_failed,
    401: AdminErrorCode.auth_required,
    403: AdminErrorCode.forbidden,
    404: AdminErrorCode.not_found,
    405: AdminErrorCode.not_found,
    409: AdminErrorCode.conflict,
    422: AdminErrorCode.validation_failed,
    429: AdminErrorCode.rate_limited,
    503: AdminErrorCode.not_configured,
}


class AdminAPIError(Exception):
    def __init__(self, code: AdminErrorCode, message: str, status_code: int, *, retryable: bool = False,
                 details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.details = details

    @classmethod
    def auth_required(cls) -> "AdminAPIError":
        return cls(AdminErrorCode.auth_required, "需要员工登录。", 401)

    @classmethod
    def session_expired(cls) -> "AdminAPIError":
        return cls(AdminErrorCode.session_expired, "员工登录状态已失效，请重新登录。", 401)

    @classmethod
    def forbidden(cls, permission: str, message: str = "当前角色没有这项权限。") -> "AdminAPIError":
        return cls(AdminErrorCode.forbidden, message, 403, details={"required_permission": permission})

    @classmethod
    def not_found(cls, resource: str) -> "AdminAPIError":
        return cls(AdminErrorCode.not_found, f"没有找到{resource}。", 404, details={"resource": resource})

    @classmethod
    def version_conflict(cls, expected: int | None, current: int | None) -> "AdminAPIError":
        return cls(AdminErrorCode.version_conflict, "这条记录已在别处更新，请刷新后再试。", 409,
                   details={"expected_version": expected, "current_version": current})

    @classmethod
    def validation(cls, message: str, **details: Any) -> "AdminAPIError":
        return cls(AdminErrorCode.validation_failed, message, 422, details=details or None)


def is_admin_path(path: str) -> bool:
    return path == ADMIN_API_PREFIX or path.startswith(ADMIN_API_PREFIX + "/")


def request_id_of(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    if rid:
        return rid
    rid = f"adm_{uuid.uuid4().hex[:16]}"
    request.state.request_id = rid
    return rid


def error_response(request: Request, code: AdminErrorCode, message: str, status_code: int, *,
                   retryable: bool = False, details: dict[str, Any] | None = None) -> JSONResponse:
    rid = request_id_of(request)
    body = {"error": {"code": code.value, "message": message, "request_id": rid, "retryable": retryable, "details": details}}
    return JSONResponse(body, status_code=status_code, headers={REQUEST_ID_HEADER: rid, "Cache-Control": "no-store"})


def install_admin_errors(app: FastAPI) -> None:
    """只接管 /api/v1/admin；其余一律回到安装本函数之前就已注册的处理器。"""
    previous_http = app.exception_handlers.get(StarletteHTTPException)
    previous_validation = app.exception_handlers.get(RequestValidationError)
    previous_unhandled = app.exception_handlers.get(Exception)

    async def _delegate(previous, request: Request, exc):
        if previous is None:
            raise exc
        result = previous(request, exc)
        return await result if hasattr(result, "__await__") else result

    @app.exception_handler(AdminAPIError)
    async def _admin_error(request: Request, exc: AdminAPIError):
        return error_response(request, exc.code, exc.message, exc.status_code, retryable=exc.retryable, details=exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        if not is_admin_path(request.url.path):
            return await _delegate(previous_http, request, exc)
        code = _STATUS_TO_CODE.get(exc.status_code, AdminErrorCode.internal_error)
        message = "没有找到这个接口。" if exc.status_code in (404, 405) else "请求未能完成。"
        return error_response(request, code, message, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        if not is_admin_path(request.url.path):
            return await _delegate(previous_validation, request, exc)
        # 不回显 input：登录请求体里有口令。
        cleaned = [{"loc": [str(part) for part in item.get("loc", ())], "type": item.get("type"), "msg": item.get("msg")}
                   for item in exc.errors()]
        return error_response(request, AdminErrorCode.validation_failed, "请求内容不符合要求。", 422, details={"errors": cleaned})

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        if not is_admin_path(request.url.path):
            return await _delegate(previous_unhandled, request, exc)
        rid = request_id_of(request)
        logger.exception("admin request failed request_id=%s path=%s", rid, request.url.path)
        return error_response(request, AdminErrorCode.internal_error, "后台服务出了点问题，请稍后再试。", 500, retryable=True)
