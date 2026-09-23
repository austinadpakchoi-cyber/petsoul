"""意图判断层六个离线用例（规则判断器为离线基线，不调用任何远端）：
拒绝拍照、想念不改路线、历史+当前约束并存、愿望不当历史、私密片段不转达、判断器不可用显式降级。"""

from __future__ import annotations

import unittest

from app.intent_layer import IntentLayer
from app.schemas.web.intent import (
    ActionProposalKind,
    IntentChannel,
    IntentContext,
    IntentLayerMode,
    IntentProvider,
    SignalKind,
    TemporalScope,
    UsageLimit,
)
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase

CTX = IntentContext(request_id="req-test", message_id="msg-test", channel=IntentChannel.communicator)


def layer(mode: IntentLayerMode = IntentLayerMode.assist, provider: IntentProvider = IntentProvider.rule) -> IntentLayer:
    return IntentLayer(mode, provider)


class IntentOfflineCases(unittest.TestCase):
    def assess(self, text: str):
        assessment = layer().assess(CTX, text)
        assert assessment is not None
        for signal in assessment.signals:
            self.assertEqual(text[signal.span.start:signal.span.end], signal.span.text, "片段下标必须能在原文中匹配")
            self.assertEqual(signal.source, "judge")
        return assessment, layer().propose(assessment)

    def test_1_refuse_photo_offers_control_only(self) -> None:
        assessment, proposals = self.assess("别再给我拍照了。")
        self.assertEqual([(s.kind, s.subject.value) for s in assessment.signals], [(SignalKind.refuse, "photo")])
        self.assertEqual(proposals[0].kind, ActionProposalKind.offer_control)
        self.assertTrue(proposals[0].requires_confirmation)
        self.assertEqual(proposals[0].domain_check, "no_photo_scheduled")

    def test_2_missing_does_not_change_route(self) -> None:
        assessment, proposals = self.assess("好想你呀。")
        kinds = {s.kind for s in assessment.signals}
        self.assertIn(SignalKind.missing, kinds)
        self.assertNotIn(SignalKind.constraint, kinds)
        self.assertEqual([(p.kind, p.domain_check) for p in proposals], [(ActionProposalKind.adjust_reply, "route_change_not_implied_by_missing")])

    def test_3_history_and_current_constraint_coexist(self) -> None:
        assessment, proposals = self.assess("它以前最喜欢去海边。今天别安排出门。")
        by_kind = {s.kind: s for s in assessment.signals}
        self.assertEqual(by_kind[SignalKind.share].temporal, TemporalScope.past)
        self.assertEqual(by_kind[SignalKind.constraint].temporal, TemporalScope.current_command)
        self.assertIn("history_and_current_constraint_coexist", assessment.conflicts)
        control = next(p for p in proposals if p.kind is ActionProposalKind.offer_control)
        self.assertEqual(control.domain_check, "journey_unchanged_until_confirmed")
        self.assertTrue(control.requires_confirmation)
        self.assertTrue(any(p.domain_check == "history_not_current_state" for p in proposals))

    def test_4_wish_is_not_history(self) -> None:
        assessment, proposals = self.assess("希望以后带它去看雪。")
        self.assertEqual([(s.kind, s.temporal) for s in assessment.signals], [(SignalKind.wish, TemporalScope.future_wish)])
        self.assertEqual(proposals[0].domain_check, "wish_not_history")
        self.assertTrue(proposals[0].requires_confirmation)

    def test_5_private_part_is_not_relayed(self) -> None:
        text = "它今天在阳台晒太阳。我那天没忍住哭了，这件事别告诉它。"
        assessment, proposals = self.assess(text)
        private = [s for s in assessment.signals if UsageLimit.do_not_relay in s.usage_limits]
        self.assertTrue(private)
        self.assertTrue(all("晒太阳" not in s.span.text for s in private), "只限制私密片段，不连带整句")
        self.assertTrue(all(p.target == "owner_private" and p.requires_confirmation for p in proposals if p.kind is ActionProposalKind.record_candidate
                            and p.domain_check == "private_segment_not_relayed"))

    def test_6_unavailable_judge_degrades_explicitly(self) -> None:
        for provider in (IntentProvider.jev, IntentProvider.configured_llm):
            unavailable = layer(provider=provider)
            assessment = unavailable.assess(CTX, "好想你呀。")
            self.assertEqual(assessment.evidence.degraded_reason, "judge_unavailable")
            self.assertIsNone(assessment.evidence.effective_model, "没有真实返回就不填模型")
            self.assertEqual([p.kind for p in unavailable.propose(assessment)], [ActionProposalKind.clarify])
            self.assertIsNone(unavailable.reply_style(CTX, "好想你呀。"))

    def test_off_and_shadow_never_change_behaviour(self) -> None:
        self.assertIsNone(layer(IntentLayerMode.off).assess(CTX, "好想你"))
        self.assertIsNone(layer(IntentLayerMode.off).reply_style(CTX, "好想你"))
        self.assertIsNone(layer(IntentLayerMode.shadow).reply_style(CTX, "好想你"))
        self.assertEqual(layer(IntentLayerMode.assist).reply_style(CTX, "好想你"), "missing")


class IntentThroughCommunicator(WebPlatformTestBase):
    """assist 模式经网页通讯：只改回应措辞，不改变旅程；默认 off 时回应与之前一致。"""

    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)

    def _send(self, text: str) -> tuple[str, dict]:
        owner = self.user(f"intent-{self.web.intent.mode.value}")
        owner.adopt_and_move_in("adopt-lan")
        owner.post(f"/communicator/{owner.pet_id}/messages", {"client_message_id": "intent-0001", "text": text})
        self.clock.advance(seconds=25)
        items = owner.get(f"/communicator/{owner.pet_id}/messages").json()["items"]
        return items[-1]["text"], owner.home()

    def test_default_off(self) -> None:
        reply, home = self._send("今天别安排出门。")
        self.assertNotIn("待在家附近", reply)
        self.assertIsNone(home["journey"])

    def test_assist_adjusts_wording_only(self) -> None:
        self.web.intent.mode = IntentLayerMode.assist
        reply, home = self._send("今天别安排出门。")
        self.assertIn("待在家附近", reply)
        self.assertIsNone(home["journey"], "意图层不直接改变旅程")
        self.assertEqual(home["presence"], "at_home")


if __name__ == "__main__":
    unittest.main()
