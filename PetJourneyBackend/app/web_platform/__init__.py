"""网页平台共用设施（R0 框架窗口维护的共享入口）。

- errors：/api/v1/web 统一错误信封与 request_id；
- session：cookie（HttpOnly + CSRF）/ Bearer 统一主体解析；
- idempotency：Idempotency-Key 请求摘要绑定；
- migrations：网页新表的显式编号迁移（自动发现）；
- tasks：可恢复任务记录与受控单步执行器；
- legacy_guard：旧 /api/v1 接口的可选访问策略。

组合根 main.py 只调用 ``install_web_platform``；模块作者不改本包，只在自己的
路由/领域目录中使用这些原语。
"""

from __future__ import annotations

from fastapi import FastAPI, Request

from ..config import Settings
from ..storage import JourneyStorage
from .errors import WebAPIError, install_error_handlers
from .idempotency import IdempotencyStore, require_idempotency_key
from .legacy_guard import install_legacy_guard
from .migrations import apply_web_migrations
from .session import WebPrincipal, optional_principal, require_csrf, require_principal
from .tasks import WebTaskQueue

WEB_BACKEND_VERSION = "web-mvp-0.4.5"  # 与契约版本同步递增，便于区分本地与公网部署


def install_web_platform(app: FastAPI, *, storage: JourneyStorage, settings: Settings) -> None:
    if getattr(settings, "sqlite_wal", False):
        with storage.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")  # 数据库文件级设置，持久生效；API 与任务进程并发读写更顺畅
    app.state.web_applied_migrations = apply_web_migrations(storage)
    app.state.web_idempotency = IdempotencyStore(storage)
    app.state.web_tasks = WebTaskQueue(storage)
    install_error_handlers(app)
    install_legacy_guard(app)


def get_idempotency_store(request: Request) -> IdempotencyStore:
    return request.app.state.web_idempotency


def get_task_queue(request: Request) -> WebTaskQueue:
    return request.app.state.web_tasks


__all__ = [
    "WEB_BACKEND_VERSION",
    "WebAPIError",
    "WebPrincipal",
    "IdempotencyStore",
    "WebTaskQueue",
    "install_web_platform",
    "get_idempotency_store",
    "get_task_queue",
    "optional_principal",
    "require_principal",
    "require_csrf",
    "require_idempotency_key",
]
