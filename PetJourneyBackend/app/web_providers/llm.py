"""网页用的对话模型客户端（OpenAI 兼容 /chat/completions）。只在服务端调用；密钥不进日志与响应。

- 请求的模型名与服务端实际返回的模型名分开记录（effective_model 只取响应里的值）；
- 每日上限、超时、HTTP 失败都抛 ChatUnavailable，由调用方显式降级（模板/规则），不改用其他付费供应商。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol
from urllib import error, request
from urllib.parse import urlparse

from .meter import ProviderMeter


class ChatUnavailable(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ChatResult:
    text: str
    requested_model: str
    effective_model: str | None
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class WebChat(Protocol):
    available: bool
    provider_label: str

    def complete(self, messages: list[dict[str, str]], *, max_tokens: int = 200, temperature: float = 0.7, json_mode: bool = False) -> ChatResult: ...


class NoChat:
    available = False
    provider_label = "未配置"

    def complete(self, messages, *, max_tokens=200, temperature=0.7, json_mode=False) -> ChatResult:
        raise ChatUnavailable("not_configured")


class OpenAICompatibleChat:
    available = True

    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: float, meter: ProviderMeter, provider_label: str = "DeepSeek") -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model = model
        self.timeout = timeout
        self.meter = meter
        self.provider_label = provider_label

    def complete(self, messages: list[dict[str, str]], *, max_tokens: int = 200, temperature: float = 0.7, json_mode: bool = False) -> ChatResult:
        if not self.meter.allow("llm"):
            raise ChatUnavailable("daily_cap")
        payload: dict[str, object] = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        flash = urlparse(self.base_url).hostname == "api.deepseek.com" and self.model == "deepseek-flash"
        if flash:
            # V4.1 默认开启思考；这些短回复/JSON 调用沿用非思考预算，避免预算耗在 reasoning_content。
            payload["thinking"] = {"type": "disabled"}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}"},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            self.meter.record("llm", False, f"http {exc.code}: {detail}")
            raise ChatUnavailable(f"http_{exc.code}") from exc
        except Exception as exc:  # noqa: BLE001 - 网络/超时/解析：统一降级
            self.meter.record("llm", False, f"{type(exc).__name__}: {exc}")
            raise ChatUnavailable("network") from exc
        latency = int((time.perf_counter() - started) * 1000)
        try:
            text = str(data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError) as exc:
            self.meter.record("llm", False, "malformed response")
            raise ChatUnavailable("malformed") from exc
        if flash and json_mode:
            try:
                if not isinstance(json.loads(text), dict):
                    raise ValueError("expected JSON object")
            except ValueError as exc:
                # 已调用成功但结构无效：如实失败，不清理异常标记来伪造 JSON，也不自动重发。
                self.meter.record("llm", False, "malformed JSON response")
                raise ChatUnavailable("malformed_json") from exc
        self.meter.record("llm", True)
        usage = data.get("usage") or {}
        return ChatResult(text=text, requested_model=self.model, effective_model=data.get("model"), latency_ms=latency,
                          prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"))
