"""有限决策：在调用次数、预算预占与截止时间之内问模型，校验输出，得到带版本的 BrainProposal 或明确的 DecisionFailure。

- 家庭没有同意交给模型、没有预算预占（或被拒、过期、不属于这次操作）、模型未配置、剩余时间不够一次调用：一次都不调用，直接失败；
- 一次操作最多 max_model_calls 次（默认 2：首答 + 一次格式修复，或一次工具查询后的续问），并且不超过预占的额度；工具最多 max_tool_calls 次；
- 模型答完后再读一次版本：成员 / 用途授权变了 → revoked；DNA、活动、行程变了 → stale_context；运行归属换了 → stale_context（不可重试）；
- 这里不写库、不扣钱、不发消息、不换供应商。规则后备由集成窗口执行并标 rule_fallback，决策包只产出 composed_by=model 的提案。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from ...schemas.runtime_internal import (BrainProposal, BudgetDenied, BudgetReservation, Clock, DecisionContext, DecisionFailure,
                                         DecisionFailureCode)
from .context import BuiltContext, build_context, can_continue
from .outcomes import CallRecord, DecisionAudit, DecisionResult, failure
from .ports import CallLimits, ContextReader, DecisionRequest, ModelAdapter, ModelCallError, ToolPort, ToolSpec
from .prompt import PROMPT_VERSION, context_digest, render, repair_messages, tool_messages
from .validation import Choice, Invalid, ToolRequest, validate

Code = DecisionFailureCode
HARD_MAX_CALLS = 3
AUTH_FIELDS = ("membership_epoch", "privacy_epoch")
TOOL_UNAVAILABLE = "（这项资料现在查不到）"


def _permit_problem(context: DecisionContext, permit, now) -> DecisionFailure | None:
    op = context.operation_id
    if permit is None:
        return failure(op, Code.budget_denied, "no_reservation")
    if isinstance(permit, BudgetDenied):
        wait = int((permit.retry_after - now).total_seconds()) if permit.retry_after and permit.retry_after > now else None
        return failure(op, Code.budget_denied, "reservation_denied", f"{permit.scope}/{permit.reason}", retry_after_seconds=wait)
    if not isinstance(permit, BudgetReservation) or permit.operation_id != op:
        return failure(op, Code.budget_denied, "reservation_mismatch")
    if permit.status != "reserved" or permit.reserved_units < 1:
        return failure(op, Code.budget_denied, "reservation_not_active", permit.status)
    return None


def _recheck(context: DecisionContext, reader: ContextReader, now, offer) -> DecisionFailure | None:
    """模型想好之后、交出提案之前再核一次：受众、授权、运行归属、DNA / 活动 / 行程版本、选中行动依赖的版本、截止时间。"""
    op = context.operation_id
    try:
        current = reader.versions(context.pet_id)
        valid = reader.audience_valid(context.pet_id, context.audience_scope)
    except Exception as exc:  # noqa: BLE001 - 核不了就不交出提案
        return failure(op, Code.provider_error, "recheck_failed", type(exc).__name__)
    changed = context.versions.stale_fields(current)
    revoked = [name for name in changed if name in AUTH_FIELDS]
    if not valid or revoked:
        return failure(op, Code.revoked, "authority_changed", ",".join(revoked) or "audience")
    if "runtime_epoch" in changed:
        return failure(op, Code.stale_context, "runtime_superseded", retryable=False)
    if changed:
        return failure(op, Code.stale_context, "versions_changed", ",".join(changed))
    if offer is not None:
        outdated = offer.expected_versions.stale_fields(current)
        if outdated:
            return failure(op, Code.stale_context, "offer_outdated", ",".join(outdated))
    if now > context.deadline_at:
        return failure(op, Code.deadline_passed, "answered_late")
    return None


def decide(context: DecisionContext, model: ModelAdapter, limits: CallLimits = CallLimits(), *, permit: BudgetReservation | BudgetDenied | None,
           reader: ContextReader, clock: Clock, model_consent: bool = False, tools: ToolPort | None = None, tool_specs: tuple[ToolSpec, ...] = (),
           dropped: tuple[str, ...] = ()) -> DecisionResult:
    """model_consent：家庭已同意把共用 DNA 与生活事实交给模型（集成窗口按家庭的模型开关给出）。没有同意就一次都不调用。"""
    op = context.operation_id
    calls: list[CallRecord] = []

    def done(outcome: BrainProposal | DecisionFailure, prompt=None, used: tuple[str, ...] = ()) -> DecisionResult:
        audit = DecisionAudit(prompt.version if prompt else PROMPT_VERSION, context_digest(context), used, dropped)
        return DecisionResult(outcome, tuple(calls), audit)

    if context.purpose != "life_plan":
        return done(failure(op, Code.disabled, "unsupported_purpose", str(context.purpose)))
    if not model_consent:
        return done(failure(op, Code.disabled, "no_model_consent"))
    start = clock.now_utc()
    problem = _permit_problem(context, permit, start)
    if problem is not None:
        return done(problem)
    if not getattr(model, "available", False):
        return done(failure(op, Code.disabled, "model_disabled"))
    call_time = timedelta(seconds=max(0.0, float(getattr(model, "max_call_seconds", 30.0))))
    max_calls = max(1, min(limits.max_model_calls, permit.reserved_units, HARD_MAX_CALLS))
    room_for_two = max_calls >= 2 and start + 2 * call_time <= context.deadline_at
    specs = tuple(tool_specs) if tools is not None else ()
    prompt = render(context, tools=specs, tools_allowed=limits.max_tool_calls if room_for_two else 0)
    messages = list(prompt.messages)
    continuing = can_continue(context.current_activity, context.as_of)
    kind, tools_used, final_only = "decision", 0, False
    last: Invalid | ToolRequest | None = None
    for attempt in range(1, max_calls + 1):
        moment = clock.now_utc()
        if moment >= permit.expires_at:
            return done(failure(op, Code.budget_denied, "reservation_expired"), prompt)
        if moment + call_time > context.deadline_at:
            return done(failure(op, Code.deadline_passed, "not_enough_time"), prompt)
        try:
            reply = model.complete(messages, max_tokens=limits.max_output_tokens)
        except ModelCallError as exc:
            calls.append(CallRecord(attempt, kind, exc.outcome, exc.reason[:80]))
            reason = {Code.disabled: "model_disabled", Code.budget_denied: "provider_cap"}.get(exc.code, "provider_error")
            return done(failure(op, exc.code, reason, exc.reason), prompt)
        except Exception as exc:  # noqa: BLE001 - 适配器自身出错：可能已经发出请求，按 unknown 记
            calls.append(CallRecord(attempt, kind, "unknown", type(exc).__name__))
            return done(failure(op, Code.provider_error, "adapter_error", type(exc).__name__), prompt)
        calls.append(CallRecord(attempt, kind, "succeeded", None, reply.latency_ms, reply.requested_model, reply.effective_model,
                                reply.prompt_tokens, reply.completion_tokens))
        moment = clock.now_utc()
        if moment > context.deadline_at:
            return done(failure(op, Code.deadline_passed, "answered_late"), prompt)
        result = validate(reply.text, context, prompt, limits, moment, tools=specs, tools_left=limits.max_tool_calls - tools_used, final_only=final_only)
        if isinstance(result, Choice):
            offer = next((o for o in context.action_offers if o.offer_id == result.offer_id), None)
            problem = _recheck(context, reader, clock.now_utc(), offer)
            if problem is not None:
                return done(problem, prompt, result.used_refs)
            model_ref = f"{model.provider_label}:{reply.effective_model or reply.requested_model or 'unknown'}"
            proposal = BrainProposal(operation_id=op, source_versions=context.versions, composed_by="model", intent_summary=result.intent,
                                     selected_offer_id=result.offer_id, continue_current=result.offer_id is None, parameters=result.parameters,
                                     suggested_review_after_seconds=result.review_after_seconds, expression_request=None,
                                     memory_candidate_refs=result.remember_refs, model_ref=model_ref)
            return done(proposal, prompt, result.used_refs)
        last = result
        if isinstance(result, ToolRequest):
            answers: list[tuple[str, str, str]] = []
            for name, alias, target in result.calls:
                tools_used += 1
                try:
                    found = tools.call(name, target, pet_id=context.pet_id, audience=context.audience_scope)  # type: ignore[union-attr]
                    if not isinstance(found, str):
                        raise TypeError("tool result must be text")
                    answers.append((name, alias, found))
                    calls.append(CallRecord(attempt, "tool", "succeeded", name))
                except Exception as exc:  # noqa: BLE001 - 查不到（或端口返回了不是文字的东西）就如实告诉模型
                    answers.append((name, alias, TOOL_UNAVAILABLE))
                    calls.append(CallRecord(attempt, "tool", "failed", f"{name}:{type(exc).__name__}"))
            messages += tool_messages(reply.text, answers)
            kind, final_only = "followup", True
            continue
        if not result.repairable:
            return done(failure(op, result.code, result.reason, result.problem), prompt)
        messages += repair_messages(reply.text, result.problem, prompt, continuing)
        kind = "repair"
    if isinstance(last, Invalid):
        return done(failure(op, last.code, last.reason, last.problem), prompt)
    return done(failure(op, Code.bad_output, "no_call_left_after_tools"), prompt)


@dataclass
class Brain:
    """给集成窗口的门面：先构造上下文，再做有限决策。reader / model / clock / tools 都由装配时注入。"""

    reader: ContextReader
    model: ModelAdapter
    clock: Clock
    tools: ToolPort | None = None
    tool_specs: tuple[ToolSpec, ...] = ()

    def context(self, request: DecisionRequest) -> BuiltContext | DecisionFailure:
        return build_context(self.reader, request)

    def propose(self, request: DecisionRequest, permit: BudgetReservation | BudgetDenied | None, limits: CallLimits = CallLimits()) -> DecisionResult:
        built = build_context(self.reader, request)
        if isinstance(built, DecisionFailure):
            return DecisionResult(built)
        return decide(built.context, self.model, limits, permit=permit, reader=self.reader, clock=self.clock, model_consent=request.model_consent,
                      tools=self.tools, tool_specs=self.tool_specs, dropped=built.dropped)
