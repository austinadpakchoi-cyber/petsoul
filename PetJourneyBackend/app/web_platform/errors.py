"""网页 API 统一错误：稳定 code + 可读 message + request_id，不泄露堆栈。

只作用于 ``/api/v1/web`` 前缀；旧 ``/api/v1`` 接口保持原有错误形态（iOS 兼容）。
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (
    http_exception_handler as default_http_exception_handler,
    request_validation_exception_handler as default_validation_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..schemas.web.common import (
    WEB_API_PREFIX,
    CapabilityStatus,
    WebError,
    WebErrorCode,
    WebErrorEnvelope,
)

logger = logging.getLogger("petsoul.web")

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{8,64}$")

_STATUS_TO_CODE = {
    400: WebErrorCode.validation_failed,
    401: WebErrorCode.auth_required,
    403: WebErrorCode.forbidden,
    404: WebErrorCode.not_found,
    405: WebErrorCode.not_found,
    409: WebErrorCode.conflict,
    422: WebErrorCode.validation_failed,
    429: WebErrorCode.rate_limited,
    501: WebErrorCode.capability_unavailable,
    502: WebErrorCode.upstream_unavailable,
    503: WebErrorCode.not_configured,
}


class WebAPIError(Exception):
    """网页路由抛出的业务错误；模块作者只用它表达失败，不自造错误 JSON。"""

    def __init__(
        self,
        code: WebErrorCode,
        message: str,
        status_code: int,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.details = details

    @classmethod
    def auth_required(cls) -> "WebAPIError":
        return cls(WebErrorCode.auth_required, "需要登录后才能继续。", 401)

    @classmethod
    def session_expired(cls) -> "WebAPIError":
        return cls(WebErrorCode.session_expired, "登录状态已过期，请重新登录。", 401)

    @classmethod
    def forbidden(cls, message: str = "没有权限访问这项内容。") -> "WebAPIError":
        return cls(WebErrorCode.forbidden, message, 403)

    @classmethod
    def not_found(cls, resource: str) -> "WebAPIError":
        return cls(WebErrorCode.not_found, f"没有找到{resource}。", 404, details={"resource": resource})

    @classmethod
    def version_conflict(cls, expected: int | None = None, current: int | None = None) -> "WebAPIError":
        return cls(
            WebErrorCode.version_conflict,
            "内容已在别处更新，请刷新后再试。",
            409,
            details={"expected": expected, "current": current},
        )

    @classmethod
    def capability_unavailable(
        cls,
        capability: str,
        status: CapabilityStatus = CapabilityStatus.not_implemented,
    ) -> "WebAPIError":
        http_status = 503 if status is CapabilityStatus.not_configured else 501
        code = WebErrorCode.not_configured if status is CapabilityStatus.not_configured else WebErrorCode.capability_unavailable
        return cls(
            code,
            "这项能力尚未接入。",
            http_status,
            details={"capability": capability, "status": status.value},
        )


def is_web_path(path: str) -> bool:
    return path == WEB_API_PREFIX or path.startswith(WEB_API_PREFIX + "/")


def request_id_of(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    if rid:
        return rid
    incoming = request.headers.get(REQUEST_ID_HEADER, "")
    rid = incoming if _REQUEST_ID_RE.match(incoming) else f"req_{uuid.uuid4().hex[:16]}"
    request.state.request_id = rid
    return rid


def error_response(
    request: Request,
    code: WebErrorCode,
    message: str,
    status_code: int,
    *,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    rid = request_id_of(request)
    envelope = WebErrorEnvelope(
        error=WebError(code=code, message=message, request_id=rid, retryable=retryable, details=details)
    )
    merged = {REQUEST_ID_HEADER: rid, **(headers or {})}
    return JSONResponse(envelope.model_dump(mode="json"), status_code=status_code, headers=merged)


def _sanitize_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    # 不回显 input：请求体可能含口令或私人倾诉。
    cleaned = []
    for item in exc.errors():
        cleaned.append({"loc": [str(part) for part in item.get("loc", ())], "type": item.get("type"), "msg": item.get("msg")})
    return cleaned


def install_error_handlers(app: FastAPI) -> None:
    @app.middleware("http")
    async def _web_request_id(request: Request, call_next):
        if not is_web_path(request.url.path):
            return await call_next(request)
        rid = request_id_of(request)
        response = await call_next(request)
        response.headers.setdefault(REQUEST_ID_HEADER, rid)
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(WebAPIError)
    async def _web_api_error(request: Request, exc: WebAPIError):
        return error_response(
            request, exc.code, exc.message, exc.status_code, retryable=exc.retryable, details=exc.details
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        if not is_web_path(request.url.path):
            return await default_http_exception_handler(request, exc)
        code = _STATUS_TO_CODE.get(exc.status_code, WebErrorCode.internal_error)
        message = "没有找到这个接口。" if exc.status_code in (404, 405) else "请求未能完成。"
        return error_response(request, code, message, exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        if not is_web_path(request.url.path):
            return await default_validation_handler(request, exc)
        return error_response(
            request,
            WebErrorCode.validation_failed,
            "请求内容不符合要求。",
            422,
            details={"errors": _sanitize_validation_errors(exc)},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        if not is_web_path(request.url.path):
            return PlainTextResponse("Internal Server Error", status_code=500)
        rid = request_id_of(request)
        logger.exception("web request failed request_id=%s path=%s", rid, request.url.path)
        return error_response(request, WebErrorCode.internal_error, "服务暂时出了点问题，请稍后再试。", 500, retryable=True)
