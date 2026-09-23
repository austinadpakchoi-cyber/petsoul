"""爪爪驾校的领域错误：reason 是稳定的错误原因（路由翻译成 404 / 409 / 422），details 给前端需要的附加信息。"""

from __future__ import annotations


class DrivingError(Exception):
    def __init__(self, reason: str, message: str, **details) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.details = details
