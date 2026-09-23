"""旅程领域错误（路由层翻译成稳定错误码）。"""

from __future__ import annotations


class JourneyError(Exception):
    def __init__(self, reason: str, message: str, **details) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.details = details
