"""已配置主模型（OpenAI 兼容对话模型）作为意图判断器。

- 只做“判断”：输出结构化信号，不生成回复、不执行动作；执行与否仍由 IntentLayer 的代码规则与主人确认决定；
- 每个信号必须引用原文片段，片段在原文中找不到就丢弃（不接受模型改写后的“依据”）；
- 输出不是合法 JSON、超时、超限都抛 JudgeUnavailable，IntentLayer 显式降级为澄清；
- confidence 不使用（对话模型不给可校准的概率），effective_model 取服务端真实返回值。
"""

from __future__ import annotations

import json

from ..schemas.web.intent import IntentProvider, IntentSignal, SignalKind, SignalSubject, SpanRef, TemporalScope, UsageLimit
from .judge import JudgeResult, JudgeUnavailable

PROMPT_VERSION = "intent-llm-q1"

SYSTEM = f"""你是意图判断器，分析宠物主人发给宠物或接待员的一句中文。只输出 JSON，不要解释。
格式：{{"signals": [{{"kind": ..., "subject": ..., "temporal": ..., "target": 字符串或 null, "negated": 布尔, "quoted": 布尔, "span": "原文中的连续片段", "usage_limits": [...]}}]}}
kind 取值：{", ".join(k.value for k in SignalKind)}。
subject 取值：{", ".join(s.value for s in SignalSubject)}。
temporal 取值：{", ".join(t.value for t in TemporalScope)}。
usage_limits 取值：{", ".join(u.value for u in UsageLimit)}。
判断要点：
- 过去的经历/习惯是 share+past；以后/希望/想带它去 是 wish+future_wish，不是过去；
- 想念是 missing，不代表要改行程；
- “今天别出门/别安排”这类当前要求是 constraint+current_command；带“如果…就…”的条件句用 hypothetical；
- “别告诉它/只留在这里/别转达”是 privacy_limit，usage_limits 含 do_not_relay 与 do_not_publish，span 只覆盖私密的那部分；
- 拒绝拍照 refuse+photo；拒绝某个地方 refuse+place；“别记了/删掉那条”是 revoke；
- 引号里转述别人的话 quoted=true；
- 一句话可以有多个信号；没有任何意图时输出 {{"signals": [{{"kind": "unclear", "subject": "unknown", "temporal": "unknown", "target": null, "negated": false, "quoted": false, "span": 全句, "usage_limits": []}}]}}。
span 必须逐字复制原文，不能改写。"""


def _enum(cls, value, default):
    try:
        return cls(value)
    except (ValueError, TypeError):
        return default


class ConfiguredLLMJudge:
    provider = IntentProvider.configured_llm

    def __init__(self, chat) -> None:  # chat: web_providers.WebChat
        self.chat = chat

    def judge(self, text: str, recent_context: list[str]) -> JudgeResult:
        if self.chat is None or not getattr(self.chat, "available", False):
            raise JudgeUnavailable("configured_llm_not_configured")
        messages = [{"role": "system", "content": SYSTEM}]
        if recent_context:
            messages.append({"role": "user", "content": "（上文，仅供理解指代，不要对它输出信号）" + " / ".join(c[:120] for c in recent_context[-3:])})
        messages.append({"role": "user", "content": text})
        try:
            result = self.chat.complete(messages, max_tokens=500, temperature=0, json_mode=True)
        except Exception as exc:  # noqa: BLE001 - ChatUnavailable 等
            raise JudgeUnavailable(getattr(exc, "reason", "llm_unavailable")) from exc
        try:
            payload = json.loads(result.text)
            raw_signals = payload["signals"]
            assert isinstance(raw_signals, list)
        except (ValueError, KeyError, TypeError, AssertionError) as exc:
            raise JudgeUnavailable("malformed_output") from exc
        signals: list[IntentSignal] = []
        for raw in raw_signals:
            if not isinstance(raw, dict):
                continue
            span_text = str(raw.get("span") or "").strip()
            start = text.find(span_text) if span_text else -1
            if start < 0:
                continue  # 依据片段不在原文里：丢弃
            limits = [u for u in (_enum(UsageLimit, v, None) for v in raw.get("usage_limits") or []) if u is not None]
            signals.append(IntentSignal(
                kind=_enum(SignalKind, raw.get("kind"), SignalKind.unclear),
                subject=_enum(SignalSubject, raw.get("subject"), SignalSubject.unknown),
                target=str(raw["target"]) if raw.get("target") else None,
                temporal=_enum(TemporalScope, raw.get("temporal"), TemporalScope.unknown),
                negated=bool(raw.get("negated")),
                quoted=bool(raw.get("quoted")),
                span=SpanRef(start=start, end=start + len(span_text), text=span_text),
                usage_limits=limits,
                source="judge",
            ))
        if not signals:
            signals.append(IntentSignal(kind=SignalKind.unclear, subject=SignalSubject.unknown, temporal=TemporalScope.unknown,
                                        span=SpanRef(start=0, end=len(text), text=text), source="judge"))
        return JudgeResult(signals=signals, latency_ms=result.latency_ms, effective_model=result.effective_model, confidence=None)
