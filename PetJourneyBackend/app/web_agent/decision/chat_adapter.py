"""正式模型适配：复用已有的对话模型客户端（web_providers.llm.WebChat，当前为 DeepSeek 的 OpenAI 兼容接口）。

不另起供应商、不加重试、不读密钥；要求 JSON 输出。客户端的“不可用”原因映射成决策失败，并标明这次调用在预算结算里算什么：
- not_configured → disabled（没发出去）；daily_cap → budget_denied（没发出去）；
- http_xxx → provider_error（对方拒绝，failed）；network（含超时）与 malformed → provider_error（可能已被受理，unknown，不能当作没花钱立即重试）。
"""

from __future__ import annotations

from ...schemas.runtime_internal import DecisionFailureCode
from ...web_providers.llm import ChatUnavailable
from .ports import ModelCallError, ModelReply

DEFAULT_TIMEOUT = 30.0


class ChatModelAdapter:
    def __init__(self, chat, *, temperature: float = 0.3, margin_seconds: float = 2.0) -> None:
        self.chat = chat
        self.temperature = temperature
        self.margin_seconds = margin_seconds

    @property
    def available(self) -> bool:
        return bool(getattr(self.chat, "available", False))

    @property
    def provider_label(self) -> str:
        return str(getattr(self.chat, "provider_label", "未配置"))

    @property
    def max_call_seconds(self) -> float:
        """客户端自带的请求超时加一点余量：剩余时间不够这么久就不发起调用。"""
        return float(getattr(self.chat, "timeout", DEFAULT_TIMEOUT)) + self.margin_seconds

    def complete(self, messages: list[dict[str, str]], *, max_tokens: int) -> ModelReply:
        try:
            result = self.chat.complete(list(messages), max_tokens=max_tokens, temperature=self.temperature, json_mode=True)
        except ChatUnavailable as exc:
            reason = exc.reason
            if reason == "not_configured":
                raise ModelCallError(DecisionFailureCode.disabled, "not_sent", reason) from exc
            if reason == "daily_cap":
                raise ModelCallError(DecisionFailureCode.budget_denied, "not_sent", reason) from exc
            outcome = "failed" if reason.startswith("http_") else "unknown"
            raise ModelCallError(DecisionFailureCode.provider_error, outcome, reason) from exc
        return ModelReply(text=result.text, requested_model=result.requested_model, effective_model=result.effective_model,
                          latency_ms=result.latency_ms, prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens)
