"""意图判断层门面：开关、降级、判断 → 代码合并 → 提议。复用 OwnerIntentBrain 的调用位置思路：
网页通讯/接待在自己的入口调用本门面；旧 OwnerIntentBrain 与旧交互链路不在本轮修改（差异见契约 §8）。

- mode=off（默认）：不调用判断器，返回 None，业务保持原有明确控件/通用回应；
- mode=shadow：调用判断器，只返回评估用于脱敏指标，不改变回应或任何状态；
- mode=assist：只允许已验证场景使用信号调整**回应措辞**或提供可选控件，永不直接执行高影响动作。
判断器不可用/超时 → 显式降级（degraded_reason），不自动改用另一付费供应商，也不以旧关键词规则兜底高影响动作。
"""

from __future__ import annotations

import uuid

from ..schemas.web.intent import (
    ActionProposal,
    ActionProposalKind,
    DecisionEvidence,
    IntentAssessment,
    IntentContext,
    IntentLayerMode,
    IntentProvider,
    SignalKind,
    TemporalScope,
    UsageLimit,
)
from .judge import RULE_VERSION, IntentJudge, JudgeUnavailable, RuleIntentJudge, UnconnectedJudge


def build_judge(provider: IntentProvider, chat=None) -> IntentJudge:
    """rule：离线基线；configured_llm：已配置主模型（需供应商可用）；jev：未接入，调用即不可用。"""
    if provider is IntentProvider.rule:
        return RuleIntentJudge()
    if provider is IntentProvider.configured_llm and chat is not None and getattr(chat, "available", False):
        from .llm_judge import ConfiguredLLMJudge

        return ConfiguredLLMJudge(chat)
    return UnconnectedJudge(provider)


class IntentLayer:
    def __init__(self, mode: IntentLayerMode, provider: IntentProvider, judge: IntentJudge | None = None) -> None:
        self.mode = mode
        self.provider = provider
        self.judge = judge or build_judge(provider)

    def assess(self, context: IntentContext, text: str) -> IntentAssessment | None:
        if self.mode is IntentLayerMode.off:
            return None
        try:
            result = self.judge.judge(text, context.recent_context)
        except JudgeUnavailable as exc:
            return IntentAssessment(assessment_id=f"ia-{uuid.uuid4().hex[:10]}", signals=[], unknown=True, needs_clarification=True,
                                    evidence=DecisionEvidence(provider=self.provider, rule_version=RULE_VERSION, latency_ms=0, error=exc.reason,
                                                              degraded_reason="judge_unavailable"))
        kinds = {s.kind for s in result.signals}
        conflicts = []
        if SignalKind.share in kinds and SignalKind.constraint in kinds:
            conflicts.append("history_and_current_constraint_coexist")
        return IntentAssessment(
            assessment_id=f"ia-{uuid.uuid4().hex[:10]}", signals=result.signals, unknown=kinds == {SignalKind.unclear},
            needs_clarification=kinds == {SignalKind.unclear}, conflicts=conflicts,
            evidence=DecisionEvidence(provider=self.provider, effective_model=result.effective_model, rule_version=RULE_VERSION, latency_ms=result.latency_ms,
                                      confidence=result.confidence),
        )

    def propose(self, assessment: IntentAssessment | None) -> list[ActionProposal]:
        """把信号转成**提议**（代码规则）。不改旅程、不删记忆、不卖物资、不公开内容；需要时只提供控件或澄清。"""
        if assessment is None:
            return []
        if assessment.evidence.degraded_reason or assessment.needs_clarification:
            return [ActionProposal(proposal_id=f"ap-{uuid.uuid4().hex[:8]}", kind=ActionProposalKind.clarify, requires_confirmation=True,
                                   note="判断不可用或不明确：用明确控件/澄清问题代替自动动作")]
        proposals: list[ActionProposal] = []
        for signal in assessment.signals:
            pid = f"ap-{uuid.uuid4().hex[:8]}"
            if UsageLimit.do_not_relay in signal.usage_limits:
                proposals.append(ActionProposal(proposal_id=pid, kind=ActionProposalKind.record_candidate, target="owner_private", requires_confirmation=True,
                                                domain_check="private_segment_not_relayed", note=signal.span.text))
            elif signal.kind is SignalKind.missing:
                proposals.append(ActionProposal(proposal_id=pid, kind=ActionProposalKind.adjust_reply, target="missing", requires_confirmation=False,
                                                domain_check="route_change_not_implied_by_missing"))
            elif signal.kind is SignalKind.refuse and signal.target == "photo":
                proposals.append(ActionProposal(proposal_id=pid, kind=ActionProposalKind.offer_control, target="photo_preference", requires_confirmation=True,
                                                domain_check="no_photo_scheduled"))
            elif signal.kind is SignalKind.constraint:
                proposals.append(ActionProposal(proposal_id=pid, kind=ActionProposalKind.offer_control, target="no_outing_today", requires_confirmation=True,
                                                domain_check="journey_unchanged_until_confirmed"))
            elif signal.kind is SignalKind.wish and signal.temporal is TemporalScope.future_wish:
                proposals.append(ActionProposal(proposal_id=pid, kind=ActionProposalKind.record_candidate, target="wish", requires_confirmation=True,
                                                domain_check="wish_not_history"))
            elif signal.kind is SignalKind.share and signal.temporal is TemporalScope.past:
                proposals.append(ActionProposal(proposal_id=pid, kind=ActionProposalKind.record_candidate, target="habit_or_story", requires_confirmation=True,
                                                domain_check="history_not_current_state"))
        return proposals or [ActionProposal(proposal_id=f"ap-{uuid.uuid4().hex[:8]}", kind=ActionProposalKind.none, requires_confirmation=False)]

    def reply_style(self, context: IntentContext, text: str) -> str | None:
        """assist 模式下供通讯选择回应措辞；off/shadow 永远返回 None（不影响行为）。"""
        if self.mode is not IntentLayerMode.assist:
            if self.mode is IntentLayerMode.shadow:
                self.assess(context, text)  # 影子：只评估，不影响回应；原文不写日志
            return None
        assessment = self.assess(context, text)
        for proposal in self.propose(assessment):
            if proposal.kind is ActionProposalKind.adjust_reply and proposal.target == "missing":
                return "missing"
            if proposal.kind is ActionProposalKind.offer_control and proposal.target == "photo_preference":
                return "refuse_photo"
            if proposal.kind is ActionProposalKind.offer_control and proposal.target == "no_outing_today":
                return "no_outing_today"
        return None
