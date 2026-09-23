"""判断器实现。

RuleIntentJudge：本地确定性规则，**只作为离线对照基线**与开发样例，不是高影响动作的安全后备；
它不调用任何远端服务。ConfiguredLLMJudge / JevJudge：R0 未接入（不装 SDK、不发请求），
调用即返回“不可用”，由 IntentLayer 显式降级。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Protocol

from ..schemas.web.intent import IntentProvider, IntentSignal, SignalKind, SignalSubject, SpanRef, TemporalScope, UsageLimit

RULE_VERSION = "intent-rules-r0-1"

SENTENCE = re.compile(r"[^。！？!?；;\n]+[。！？!?；;]?")
NEGATION = re.compile(r"(不要|别|不想|不用|不必|没有|不去)")
MISSING = re.compile(r"(想你|想它|想他|想她|想念|好想)")
PAST = re.compile(r"(以前|小时候|曾经|那时候|那年|过去)")
WISH = re.compile(r"(希望|以后|将来|有一天|想带|想去|想让)")
NOW_CONSTRAINT = re.compile(r"(今天|这周|现在|今晚|这几天|最近).{0,6}(别|不要|不用)|(别|不要)(安排|出门|去)")
PRIVACY = re.compile(r"(别|不要|不用)(告诉|跟|和|对)(它|他|她|TA)(说|讲)?|别转达|不要转达|只留(在)?这里|这件事别")
REFUSE_PHOTO = re.compile(r"(不要|别|不想)(再)?(给我)?(拍照|拍了|发照片|照片)")
REFUSE_PLACE = re.compile(r"(那家|这家|那个地方)[^。！？]{0,6}(不想去|别去|不要去)")
OWNER_FEELING = re.compile(r"(我|自己)[^。！？]{0,6}(哭|难过|内疚|自责|怪我)")
QUOTED = re.compile(r"[“\"「].+[”\"」]")


class JudgeUnavailable(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class JudgeResult:
    signals: list[IntentSignal]
    latency_ms: int
    effective_model: str | None
    confidence: float | None


class IntentJudge(Protocol):
    provider: IntentProvider

    def judge(self, text: str, recent_context: list[str]) -> JudgeResult: ...


class RuleIntentJudge:
    provider = IntentProvider.rule

    def judge(self, text: str, recent_context: list[str]) -> JudgeResult:
        started = time.perf_counter()
        signals: list[IntentSignal] = []
        for match in SENTENCE.finditer(text):
            segment = match.group(0).strip()
            if not segment:
                continue
            start = text.find(segment, match.start())
            span = SpanRef(start=start, end=start + len(segment), text=segment)
            quoted = bool(QUOTED.search(segment))
            negated = bool(NEGATION.search(segment))

            def add(kind: SignalKind, subject: SignalSubject, temporal: TemporalScope, target: str | None = None, limits: list[UsageLimit] | None = None) -> None:
                signals.append(IntentSignal(kind=kind, subject=subject, target=target, temporal=temporal, negated=negated, quoted=quoted, span=span,
                                            usage_limits=limits or [], source="judge"))

            if PRIVACY.search(segment):
                subject = SignalSubject.owner if OWNER_FEELING.search(segment) else SignalSubject.unknown
                add(SignalKind.privacy_limit, subject, TemporalScope.current_command, limits=[UsageLimit.do_not_relay, UsageLimit.do_not_publish])
                if OWNER_FEELING.search(segment):
                    add(SignalKind.share, SignalSubject.owner, TemporalScope.past, limits=[UsageLimit.do_not_relay, UsageLimit.do_not_publish])
                continue
            if REFUSE_PHOTO.search(segment):
                add(SignalKind.refuse, SignalSubject.photo, TemporalScope.current_command, target="photo")
                continue
            if REFUSE_PLACE.search(segment):
                add(SignalKind.refuse, SignalSubject.place, TemporalScope.current_command, target="named_place")
                continue
            if MISSING.search(segment):
                add(SignalKind.missing, SignalSubject.pet, TemporalScope.ongoing)
            if NOW_CONSTRAINT.search(segment):
                add(SignalKind.constraint, SignalSubject.journey, TemporalScope.current_command, target="no_outing_today")
            if PAST.search(segment):
                add(SignalKind.share, SignalSubject.pet, TemporalScope.past)
            elif WISH.search(segment) and not MISSING.search(segment):
                add(SignalKind.wish, SignalSubject.pet, TemporalScope.future_wish)
        if not signals:
            signals.append(IntentSignal(kind=SignalKind.unclear, subject=SignalSubject.unknown, temporal=TemporalScope.unknown,
                                        span=SpanRef(start=0, end=len(text), text=text), source="judge"))
        return JudgeResult(signals=signals, latency_ms=int((time.perf_counter() - started) * 1000), effective_model=None, confidence=None)


class UnconnectedJudge:
    """configured_llm / jev 的占位：未配置、未授权调用前一律不可用，不静默改用其他付费供应商。"""

    def __init__(self, provider: IntentProvider) -> None:
        self.provider = provider

    def judge(self, text: str, recent_context: list[str]) -> JudgeResult:
        raise JudgeUnavailable(f"{self.provider.value}_not_configured")
