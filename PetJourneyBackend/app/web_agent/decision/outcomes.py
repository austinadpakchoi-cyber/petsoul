"""决策结果：共享的 BrainProposal / DecisionFailure，外加每次模型与工具调用的记录（供预算结算）和审计信息。

DecisionFailure 用 runtime-internal 的 10 个码；更细的原因写在 detail 开头（例如 “private_text_echo: …”），用 reason_of 取出。
detail 里不写任何私人原文。
"""

from __future__ import annotations

from dataclasses import dataclass

from ...schemas.runtime_internal import BrainProposal, DecisionFailure, DecisionFailureCode, SettleOutcome

Code = DecisionFailureCode
RETRYABLE = {
    Code.disabled: False, Code.budget_denied: True, Code.timeout: True, Code.provider_error: True, Code.bad_output: False,
    Code.unknown_offer: False, Code.out_of_bounds: False, Code.stale_context: True, Code.revoked: False, Code.deadline_passed: True,
}


@dataclass(frozen=True)
class CallRecord:
    """一次调用：kind＝decision / repair / followup / tool；outcome 与预算结算一致（succeeded / failed / not_sent / unknown）。"""

    attempt: int
    kind: str
    outcome: SettleOutcome
    reason: str | None = None
    latency_ms: int | None = None
    requested_model: str | None = None
    effective_model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass(frozen=True)
class DecisionAudit:
    """审计用：同样的资料与版本得到同样的摘要；used_refs 是模型说用到的依据（都在上下文里）。不存原文。"""

    prompt_version: str
    context_digest: str
    used_refs: tuple[str, ...] = ()
    dropped: tuple[str, ...] = ()  # 构造上下文时二次过滤丢掉的条目（ref:原因）


@dataclass(frozen=True)
class DecisionResult:
    outcome: BrainProposal | DecisionFailure
    calls: tuple[CallRecord, ...] = ()
    audit: DecisionAudit | None = None

    @property
    def proposal(self) -> BrainProposal | None:
        return self.outcome if isinstance(self.outcome, BrainProposal) else None

    @property
    def failure(self) -> DecisionFailure | None:
        return self.outcome if isinstance(self.outcome, DecisionFailure) else None

    @property
    def model_calls(self) -> int:
        """真正发出去的模型调用次数（不含工具，不含没发出去的）。"""
        return sum(1 for call in self.calls if call.kind != "tool" and call.outcome != "not_sent")

    def settle_outcome(self) -> SettleOutcome:
        """整次操作的预算结算结果：有一次可能已被受理就是 unknown（不能盲目重试）；有成功就是 succeeded。"""
        outcomes = {call.outcome for call in self.calls if call.kind != "tool"}
        for outcome in ("unknown", "succeeded", "failed"):
            if outcome in outcomes:
                return outcome  # type: ignore[return-value]
        return "not_sent"


def failure(operation_id: str, code: DecisionFailureCode, reason: str, text: str = "", *, retryable: bool | None = None,
            retry_after_seconds: int | None = None) -> DecisionFailure:
    detail = f"{reason}: {text}" if text else reason
    return DecisionFailure(operation_id, code, RETRYABLE[code] if retryable is None else retryable, detail[:200], retry_after_seconds)


def reason_of(result: DecisionFailure) -> str:
    return result.detail.split(":", 1)[0]
