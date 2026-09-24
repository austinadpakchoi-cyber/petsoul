"""旧 /api/v1 接口的统一访问策略（可选启用），防止“只保护新网页入口、旧入口绕过”。

2026-09-23（运营后台窗口 adm1 追加）：`/api/v1/admin` 与 `/api/v1/web` 一样被排除在本守卫之外。
它是新增的员工后台，自己带独立会话、CSRF、来源校验与逐请求权限；不排除的话 policy=closed
会把它整个 404 掉。这一改只加了一个前缀判断，旧接口的策略语义没有任何变化。

现状（HEAD 980feab 只读核对）：除 /api/v1/me 与 claim_pet 外，旧的宠物级接口
（DNA、通讯、记忆、经济、旅行、轨迹等）都不校验调用者；/api/v1/scheduler/tick
可匿名推进世界；/media 静态目录全量公开上传文件。

策略 ``PETJOURNEY_LEGACY_API_POLICY``：
- ``open``（默认，保持现有 iOS/测试行为，**不可用于公开网页部署**）；
- ``owner_bearer``：旧接口需有效 Bearer；宠物级路径还须是该宠物主人；
  管理/调试接口需 X-PetJourney-Admin-Token；
- ``closed``：只保留健康检查与 Apple 登录，其余旧 /api/v1 一律 404（纯网页部署）。
/media 私有化由媒体/身份模块另行实现，本守卫不处理（见 WEB-CONTRACT 已知缺口）。
"""

from __future__ import annotations

import hmac
import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..auth import AuthError

LEGACY_PREFIX = "/api/v1/"
WEB_PREFIX = "/api/v1/web"
# 平台运营后台（/api/v1/admin）不是旧接口：它有自己的员工会话、CSRF 与逐请求权限。
# 不排除的话，policy=closed 的纯网页部署会把整个后台 404 掉（那正是推荐给公网的策略）。
ADMIN_PREFIX = "/api/v1/admin"

PUBLIC_PATHS = frozenset({"/api/v1/auth/apple"})
BEARER_SELF_PATHS = frozenset({"/api/v1/me", "/api/v1/me/claim_pet", "/api/v1/push/register", "/api/v1/push/unregister"})
ADMIN_PATTERNS = (
    re.compile(r"^/api/v1/scheduler/"),
    re.compile(r"^/api/v1/demo/"),
    re.compile(r"^/api/v1/[a-z_]+/config$"),
    re.compile(r"^/api/v1/google/config$"),
    re.compile(r"^/api/v1/pets/[^/]+/traces"),
)
PET_SCOPED_PATTERNS = (
    re.compile(r"^/api/v1/pets/(?P<pet_id>[^/]+)(?:/|$)"),
    re.compile(r"^/api/v1/(?:pet_dna|agent_status|day_plan)/(?P<pet_id>[^/]+)$"),
)
VALID_POLICIES = ("open", "owner_bearer", "closed")


def _deny(status: int, detail: str) -> JSONResponse:
    # 保持旧接口的 {"detail": ...} 错误形态，iOS 客户端解析不变。
    return JSONResponse({"detail": detail}, status_code=status)


def evaluate_legacy_request(request: Request) -> JSONResponse | None:
    """返回 None 表示放行；否则返回拒绝响应。只对旧 /api/v1（非 web）路径生效。"""
    path = request.url.path
    exempt = (WEB_PREFIX, ADMIN_PREFIX)
    if not path.startswith(LEGACY_PREFIX) or any(path == prefix or path.startswith(prefix + "/") for prefix in exempt):
        return None
    state = request.app.state
    policy = state.settings.legacy_api_policy
    if policy == "open" or path in PUBLIC_PATHS:
        return None
    if policy == "closed":
        return _deny(404, "Not Found")

    if any(pattern.match(path) for pattern in ADMIN_PATTERNS):
        token = request.headers.get("X-PetJourney-Admin-Token", "")
        expected = state.settings.economy_admin_token or ""
        if not expected or not hmac.compare_digest(token, expected):
            return _deny(403, "admin token required")
        return None

    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return _deny(401, "missing bearer token")
    try:
        user_id = state.auth_service.decode_session_token(authorization.split(" ", 1)[1].strip())
    except AuthError:
        return _deny(401, "invalid session token")
    if path in BEARER_SELF_PATHS:
        return None

    for pattern in PET_SCOPED_PATTERNS:
        match = pattern.match(path)
        if match:
            pet = state.storage.get_pet(match.group("pet_id"))
            # 不存在与不属于调用者返回同一 404，避免通过 ID 枚举宠物。
            if pet is None or pet.owner_user_id != user_id:
                return _deny(404, "Pet not found")
            return None
    # 其余旧接口（create_pet、feedback、geo 代理等）：需登录；更细的资源校验由对应模块补齐。
    return None


def install_legacy_guard(app: FastAPI) -> None:
    policy = app.state.settings.legacy_api_policy
    if policy not in VALID_POLICIES:
        raise RuntimeError(f"PETJOURNEY_LEGACY_API_POLICY 只能是 {VALID_POLICIES}，当前 {policy!r}")

    @app.middleware("http")
    async def _legacy_guard(request: Request, call_next):
        denied = evaluate_legacy_request(request)
        if denied is not None:
            return denied
        return await call_next(request)
