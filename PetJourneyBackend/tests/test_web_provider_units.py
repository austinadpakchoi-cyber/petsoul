"""意图模型判断器、调用计量上限、能力声明（不触网）。"""

from __future__ import annotations

import dataclasses
import json
import unittest

from app.intent_layer import IntentLayer
from app.intent_layer.judge import JudgeUnavailable
from app.intent_layer.llm_judge import ConfiguredLLMJudge
from app.routers.web import collect_capabilities
from app.schemas.web.intent import ActionProposalKind, IntentChannel, IntentContext, IntentLayerMode, IntentProvider, SignalKind
from app.web_providers import ChatUnavailable
from app.web_providers.llm import OpenAICompatibleChat
from app.web_providers.meter import ProviderMeter, set_provider_status
from web_base import WebPlatformTestBase
from web_provider_fakes import FakeChat


class IntentLLMJudgeTests(unittest.TestCase):
    def judge(self, reply: str) -> ConfiguredLLMJudge:
        return ConfiguredLLMJudge(FakeChat([reply]))

    def test_signals_must_quote_the_original_text(self) -> None:
        reply = json.dumps({"signals": [
            {"kind": "constraint", "subject": "journey", "temporal": "current_command", "span": "今天别安排出门", "usage_limits": []},
            {"kind": "share", "subject": "pet", "temporal": "past", "span": "改写过的依据", "usage_limits": []},
        ]}, ensure_ascii=False)
        result = self.judge(reply).judge("它以前最喜欢去海边。今天别安排出门。", [])
        self.assertEqual([s.kind for s in result.signals], [SignalKind.constraint], "依据不在原文里的信号被丢弃")
        span = result.signals[0].span
        self.assertEqual("它以前最喜欢去海边。今天别安排出门。"[span.start:span.end], "今天别安排出门")
        self.assertEqual(result.effective_model, "fake-effective")
        self.assertIsNone(result.confidence)

    def test_malformed_or_unavailable_degrades_to_clarify(self) -> None:
        with self.assertRaises(JudgeUnavailable):
            self.judge("不是 JSON").judge("好想你", [])
        layer = IntentLayer(IntentLayerMode.assist, IntentProvider.configured_llm, judge=ConfiguredLLMJudge(FakeChat(error=ChatUnavailable("timeout"))))
        assessment = layer.assess(IntentContext(request_id="r", message_id="m", channel=IntentChannel.communicator), "好想你")
        self.assertEqual(assessment.evidence.degraded_reason, "judge_unavailable")
        self.assertEqual([p.kind for p in layer.propose(assessment)], [ActionProposalKind.clarify])


class MeterAndCapabilityTests(WebPlatformTestBase):
    def test_daily_cap_blocks_before_any_request(self) -> None:
        meter = ProviderMeter(self.app.state.storage, {"llm": 1}, secrets=["sk-secret-value"])
        meter.record("llm", False, "http 401: bad key sk-secret-value")
        self.assertFalse(meter.allow("llm"))
        self.assertNotIn("sk-secret-value", str(meter.snapshot()) + str(__import__("app.web_providers.meter", fromlist=["x"]).provider_status("llm")))
        chat = OpenAICompatibleChat(base_url="http://127.0.0.1:9", api_key="sk-secret-value", model="m", timeout=1, meter=meter)
        with self.assertRaises(ChatUnavailable) as ctx:
            chat.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(ctx.exception.reason, "daily_cap")

    def test_capabilities_reflect_configuration_without_calling_providers(self) -> None:
        settings = dataclasses.replace(self.settings, **{"web_providers_enabled": True, "amap_api_key": "k", "google_maps_api_key": "g", "openai_api_key": "o",
                                                    "llm_provider": "openai", "image_provider_type": "volcengine", "doubao_api_key": "d"})
        set_provider_status("google", None)
        caps = {c.key: c.status.value for c in collect_capabilities(settings)}
        self.assertEqual((caps["map.amap"], caps["transport.routed_estimate"], caps["reception.model_conversation"], caps["adventure.hero_image"]),
                         ("available", "available", "available", "available"))
        self.assertEqual(caps["intent.layer"], "disabled", "意图层仍默认关闭")
        set_provider_status("google", "google: PERMISSION_DENIED The caller does not have permission")
        caps = {c.key: (c.status.value, c.note) for c in collect_capabilities(settings)}
        self.assertEqual(caps["map.google"][0], "not_configured")
        self.assertIn("计费", caps["map.google"][1])
        set_provider_status("google", None)
        off = {c.key: c.status.value for c in collect_capabilities(self.settings)}
        self.assertEqual(off["map.amap"], "not_configured", "总开关关闭时不声称可用")


if __name__ == "__main__":
    unittest.main()
