"""有限决策（工作包 C）：假模型只能在规则给出的可行行动里选；坏结构、未知行动、过期、撤权、预算拒绝、超时都有明确结果；
提案带来源版本，不写库、不扣钱、不发消息。正式适配器复用已有对话模型客户端（用 web_provider_fakes 的假客户端，不联网、不产生付费调用）。"""

from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

from app.schemas.runtime_internal import (ActionKind, ActivityRef, AudienceScope, BudgetDenied, DecisionContext, DecisionFailureCode, ParamBound,
                                          Versions)
from app.web_agent.decision import (Brain, BuiltContext, CallLimits, ChatModelAdapter, DecisionRequest, DecisionResult, DnaSnapshot,
                                    ModelCallError, Record, ToolSpec, build_context, decide, destination_key_of, offers_from_options, reason_of)
from app.web_agent.decision.testing import ManualClock, MemoryReader, ScriptedModel, reservation_for
from app.web_providers.llm import ChatUnavailable, NoChat
from web_provider_fakes import FakeChat

UTC = timezone.utc
HK = timezone(timedelta(hours=8))
NOW = datetime(2026, 9, 23, 2, 0, tzinfo=UTC)
HOUSEHOLD = AudienceScope("household", household_id="hh-1")
MOM = AudienceScope("private", household_id="hh-1", user_id="u-mom")
VERSIONS = Versions(runtime_epoch=1, activity_epoch=1, dna_version=3, privacy_epoch=1, membership_epoch=1)
NOTE_TEXT = "它最喜欢去海边看渔船回港"
Code = DecisionFailureCode
OPTIONS = [
    SimpleNamespace(destination_key="local:stroll", title="在家附近走走", summary="不花钱，出门透透气。", fee=0, total_minutes=64, available=True, affordable=True),
    SimpleNamespace(destination_key="work:fishing_port", title="去渔港帮忙收网", summary="干 3 小时活，工钱存进银行卡。", fee=0, total_minutes=200,
                    available=True, affordable=True),
    SimpleNamespace(destination_key="macau_ferry", title="坐船去澳门", summary="按官网船期出发的一日行。", fee=40, total_minutes=600, available=True,
                    affordable=True, reference_note="运营方船期"),
]
TOOL_SPECS = (ToolSpec("offer_detail", "查看这项行动的具体行程", "offer"),)
DEFAULT = object()


def answer(**fields) -> str:
    return json.dumps(fields, ensure_ascii=False)


def make_offers(expected: Versions = VERSIONS):
    return offers_from_options(OPTIONS, pet_id="pet-1", as_of=NOW, expected_versions=expected, income_of=lambda key: 28 if key.startswith("work:") else 0)


def make_reader(personality: str = "慢热，恋家", **kwargs) -> MemoryReader:
    base = dict(
        version_state=VERSIONS,
        dna=DnaSnapshot(fields={"personality": (personality,), "habits": ("午后在窗台晒太阳",)}, confirmed=True),
        memory_records=[Record("note:cn-a", "owner_report", NOTE_TEXT, MOM, "habit", ("travel_preference",))],
        observation_records=[Record("event:jn-1:home", "world_event", "昨天收工回到家：去渔港帮忙收网", HOUSEHOLD, "home", observed_at=NOW - timedelta(hours=16))],
        local=NOW.astimezone(HK), balance=52,
    )
    base.update(kwargs)
    return MemoryReader(**base)


def make_context(reader: MemoryReader, *, deadline: timedelta = timedelta(seconds=60), offer_list=None) -> DecisionContext:
    result = build_context(reader, DecisionRequest(operation_id="op-1", pet_id="pet-1", purpose="life_plan", audience=HOUSEHOLD, as_of=NOW,
                                                   deadline_at=NOW + deadline, offers=make_offers() if offer_list is None else offer_list))
    assert isinstance(result, BuiltContext), result
    return result.context


def run(reader: MemoryReader, model, *, clock: ManualClock | None = None, limits: CallLimits = CallLimits(), grant=DEFAULT,
        context: DecisionContext | None = None, tools=None) -> DecisionResult:
    context = context or make_context(reader)
    permit = reservation_for("op-1", now=NOW) if grant is DEFAULT else grant
    return decide(context, model, limits, permit=permit, reader=reader, clock=clock or ManualClock(NOW), model_consent=True, tools=tools,
                  tool_specs=TOOL_SPECS if tools is not None else ())


def bumped(**changes):
    """思考期间改掉读取端口的版本（模拟家人被移除、撤回授权、DNA 更正……）。"""
    return lambda reader: setattr(reader, "version_state", replace(reader.version_state, **changes))


class ProposalTests(unittest.TestCase):
    def test_model_choice_becomes_a_versioned_proposal_without_side_effects(self) -> None:
        reader = make_reader()
        context = make_context(reader)
        model = ScriptedModel(answer(choice="o2", intent="先去渔港打工，攒点钱", review_after_minutes=240, uses=["e3", "d1", "o2"], remember=["e3"]))
        result = decide(context, model, permit=reservation_for("op-1", now=NOW), reader=reader, clock=ManualClock(NOW), model_consent=True)
        proposal = result.proposal
        self.assertEqual((proposal.composed_by, proposal.model_ref, proposal.continue_current), ("model", "scripted:scripted-1", False))
        chosen = {o.offer_id: o for o in context.action_offers}[proposal.selected_offer_id]
        self.assertEqual((chosen.action_kind, destination_key_of(chosen), chosen.income_bounds), (ActionKind.work, "work:fishing_port", (28, 28)))
        self.assertEqual((proposal.source_versions, proposal.suggested_review_after_seconds), (VERSIONS, 240 * 60))
        self.assertEqual((proposal.memory_candidate_refs, proposal.expression_request), (("event:jn-1:home",), None))
        self.assertEqual(result.audit.used_refs, ("event:jn-1:home", "dna:personality@3", f"offer:{chosen.offer_id}"))
        self.assertTrue(result.audit.prompt_version.startswith("life-plan") and result.audit.context_digest)
        self.assertEqual(([(c.kind, c.outcome) for c in result.calls], result.model_calls, result.settle_outcome()), ([("decision", "succeeded")], 1, "succeeded"))
        # 只有读取（读取端口本身没有写方法）；交出提案前重新核对了版本与受众；行动本身不变
        self.assertEqual(reader.calls[-2:], ["versions", "audience_valid"])
        self.assertEqual(context.action_offers, make_context(make_reader()).action_offers)

    def test_stay_home_local_activity_and_travel_are_all_possible(self) -> None:
        for choice, kind in (("continue", None), ("o1", ActionKind.local_activity), ("o3", ActionKind.travel)):
            with self.subTest(choice=choice):
                context = make_context(make_reader())
                proposal = run(make_reader(), ScriptedModel(answer(choice=choice, intent="就这么定了")), context=context).proposal
                self.assertEqual(proposal.continue_current, kind is None)
                self.assertEqual({o.offer_id: o.action_kind for o in context.action_offers}.get(proposal.selected_offer_id), kind)

    def test_dna_reaches_the_model_and_changes_the_choice(self) -> None:
        by_dna = lambda messages: (answer(choice="o3", intent="想去远一点的地方看看") if "爱冒险" in messages[-1]["content"]  # noqa: E731
                                   else answer(choice="continue", intent="今天就在家待着"))
        bold = run(make_reader("好奇，爱冒险"), ScriptedModel(by_dna))
        shy = run(make_reader("恋家，胆小"), ScriptedModel(by_dna))
        self.assertIsNotNone(bold.proposal.selected_offer_id)
        self.assertTrue(shy.proposal.continue_current)
        self.assertNotEqual(bold.audit.context_digest, shy.audit.context_digest)

    def test_bounded_parameters_follow_the_offer(self) -> None:
        bounds = {"pace": ParamBound(choices=("slow", "normal")), "stay_minutes": ParamBound(minimum=30, maximum=120)}
        offers = tuple(replace(o, bounded_parameters=bounds) if o.source_ref == "destination:local:stroll" else o for o in make_offers())
        context = make_context(make_reader(), offer_list=offers)
        ok = run(make_reader(), ScriptedModel(answer(choice="o1", intent="慢慢走一圈", parameters={"pace": "slow", "stay_minutes": 60})), context=context)
        self.assertEqual(ok.proposal.parameters, {"pace": "slow", "stay_minutes": 60})
        for params in ({"pace": "fast"}, {"stay_minutes": 200}, {"stay_minutes": "60"}, {"mood": "happy"}):
            with self.subTest(params=params):
                bad = run(make_reader(), ScriptedModel(answer(choice="o1", intent="走走", parameters=params)), context=context, limits=CallLimits(max_model_calls=1))
                self.assertEqual((bad.failure.code, reason_of(bad.failure)), (Code.out_of_bounds, "parameter_out_of_bounds"))


class RepairAndRejectionTests(unittest.TestCase):
    def test_repairs_stay_within_the_call_limit(self) -> None:
        model = ScriptedModel("我想去散步！", answer(choice="o1", intent="出去透透气"))
        result = run(make_reader(), model)
        self.assertEqual([(c.kind, c.outcome) for c in result.calls], [("decision", "succeeded"), ("repair", "succeeded")])
        self.assertIn("不是一个合法的 JSON 对象", model.calls[1][-1]["content"])
        twice = run(make_reader(), ScriptedModel("乱码", "还是乱码"))
        self.assertEqual((twice.failure.code, reason_of(twice.failure), twice.model_calls, twice.failure.retryable), (Code.bad_output, "invalid_json", 2, False))
        once = run(make_reader(), ScriptedModel("乱码", answer(choice="o1", intent="出去")), limits=CallLimits(max_model_calls=1))
        self.assertEqual((once.failure.code, once.model_calls), (Code.bad_output, 1))
        units = ScriptedModel("乱码", answer(choice="o1", intent="出去"))
        self.assertEqual(run(make_reader(), units, grant=reservation_for("op-1", now=NOW, units=1)).model_calls, 1)
        # 照抄家人叮嘱原话的意图可以修复一次；修复提示里不再重复原话
        echo = ScriptedModel(answer(choice="o3", intent=f"因为{NOTE_TEXT}"), answer(choice="o3", intent="想去看看海"))
        self.assertEqual(run(make_reader(), echo).proposal.intent_summary, "想去看看海")
        self.assertIn("照抄了家人的叮嘱原话", echo.calls[1][-1]["content"])
        self.assertNotIn(NOTE_TEXT, echo.calls[1][-1]["content"])

    def test_each_rejection_has_an_explicit_code(self) -> None:
        cases = [
            (answer(choice="o9", intent="去一个新地方"), Code.unknown_offer, "unknown_offer"),
            (answer(choice="o2", intent="去打工", wage=100), Code.out_of_bounds, "fabricated_value"),
            (answer(choice="o1", intent="慢慢走", parameters={"pace": "slow"}), Code.out_of_bounds, "parameter_out_of_bounds"),
            (answer(choice="o1", intent="出去走走", uses=["x7"]), Code.bad_output, "unknown_reference"),
            (answer(choice="o3", intent=f"因为{NOTE_TEXT}"), Code.bad_output, "private_text_echo"),
            (answer(choice="o1", intent="出去走走", mood="开心"), Code.bad_output, "schema_violation"),
            (answer(choice="o1", intent="走" * 61), Code.bad_output, "schema_violation"),
            (answer(tools=[{"name": "offer_detail", "arg": "o3"}]), Code.bad_output, "tool_not_allowed"),
        ]
        for text, code, reason in cases:
            with self.subTest(reason=reason):
                result = run(make_reader(), ScriptedModel(text), limits=CallLimits(max_model_calls=1))
                self.assertEqual((result.failure.code, reason_of(result.failure), result.model_calls), (code, reason, 1))
                self.assertNotIn(NOTE_TEXT, result.failure.detail)
        ended = make_reader(activity_ref=ActivityRef("work", "journey:jn-2", ends_at=NOW - timedelta(minutes=1)))
        result = run(ended, ScriptedModel(answer(choice="continue", intent="不动")), limits=CallLimits(max_model_calls=1))
        self.assertEqual((result.failure.code, reason_of(result.failure)), (Code.unknown_offer, "continue_not_allowed"))

    def test_offer_that_expires_while_thinking_is_rejected(self) -> None:
        clock = ManualClock(NOW)
        model = ScriptedModel(answer(choice="o2", intent="去打工"), on_call=lambda n: clock.advance(minutes=11))
        result = run(make_reader(), model, clock=clock, context=make_context(make_reader(), deadline=timedelta(minutes=30)),
                     grant=reservation_for("op-1", now=NOW, minutes=30))
        self.assertEqual((result.failure.code, reason_of(result.failure), result.failure.retryable, result.model_calls),
                         (Code.stale_context, "offer_expired", True, 1))


class GateTests(unittest.TestCase):
    def test_budget_model_and_provider_gates(self) -> None:
        cases = [
            (None, "no_reservation", None),
            (BudgetDenied("op-1", "household", "limit_reached", retry_after=NOW + timedelta(hours=1)), "reservation_denied", 3600),
            (reservation_for("op-other", now=NOW), "reservation_mismatch", None),
            (reservation_for("op-1", now=NOW, units=0), "reservation_not_active", None),
            (reservation_for("op-1", now=NOW, status="released"), "reservation_not_active", None),
            (reservation_for("op-1", now=NOW, minutes=0), "reservation_expired", None),
        ]
        for grant, reason, retry_after in cases:
            with self.subTest(reason=reason):
                model = ScriptedModel(answer(choice="o1", intent="出去"))
                result = run(make_reader(), model, grant=grant)
                self.assertEqual((result.failure.code, reason_of(result.failure), result.failure.retry_after_seconds, len(model.calls), result.settle_outcome()),
                                 (Code.budget_denied, reason, retry_after, 0, "not_sent"))
        off = ScriptedModel(answer(choice="o1", intent="出去"), available=False)
        disabled = run(make_reader(), off)
        self.assertEqual((disabled.failure.code, reason_of(disabled.failure), disabled.failure.retryable, len(off.calls)), (Code.disabled, "model_disabled", False, 0))
        # 家庭没有同意把共用资料交给模型（默认）：有预算也一次都不调用
        silent = ScriptedModel(answer(choice="o1", intent="出去"))
        reader = make_reader()
        no_consent = decide(make_context(reader), silent, permit=reservation_for("op-1", now=NOW), reader=reader, clock=ManualClock(NOW))
        self.assertEqual((no_consent.failure.code, reason_of(no_consent.failure), len(silent.calls)), (Code.disabled, "no_model_consent", 0))
        request = DecisionRequest(operation_id="op-1", pet_id="pet-1", purpose="life_plan", audience=HOUSEHOLD, as_of=NOW,
                                  deadline_at=NOW + timedelta(seconds=60), offers=make_offers())
        facade = Brain(reader=make_reader(), model=silent, clock=ManualClock(NOW)).propose(request, reservation_for("op-1", now=NOW))
        self.assertEqual((reason_of(facade.failure), len(silent.calls)), ("no_model_consent", 0))
        # 供应商自己的日上限（没发出去）与“可能已被受理”的失败，都如实交给预算结算
        capped = run(make_reader(), ScriptedModel(ModelCallError(Code.budget_denied, "not_sent", "daily_cap")))
        self.assertEqual((capped.failure.code, reason_of(capped.failure), capped.settle_outcome(), capped.model_calls), (Code.budget_denied, "provider_cap", "not_sent", 0))
        lost = run(make_reader(), ScriptedModel(ModelCallError(Code.provider_error, "unknown", "network")))
        self.assertEqual((lost.failure.code, lost.failure.retryable, lost.settle_outcome()), (Code.provider_error, True, "unknown"))
        broken = run(make_reader(), ScriptedModel(RuntimeError("adapter bug")))
        self.assertEqual((reason_of(broken.failure), broken.settle_outcome()), ("adapter_error", "unknown"))

    def test_deadline_bounds_every_call(self) -> None:
        tight = ScriptedModel(answer(choice="o1", intent="出去"))
        result = run(make_reader(), tight, context=make_context(make_reader(), deadline=timedelta(seconds=3)))
        self.assertEqual((result.failure.code, reason_of(result.failure), len(tight.calls)), (Code.deadline_passed, "not_enough_time", 0))
        clock = ManualClock(NOW)
        slow = ScriptedModel(answer(choice="o1", intent="出去"), on_call=lambda n: clock.advance(seconds=61))
        late = run(make_reader(), slow, clock=clock)
        self.assertEqual((late.failure.code, reason_of(late.failure), late.settle_outcome()), (Code.deadline_passed, "answered_late", "succeeded"))
        clock = ManualClock(NOW)
        no_room = ScriptedModel("乱码", answer(choice="o1", intent="出去"), on_call=lambda n: clock.advance(seconds=4))
        cut = run(make_reader(), no_room, clock=clock, context=make_context(make_reader(), deadline=timedelta(seconds=8)))
        self.assertEqual((cut.failure.code, reason_of(cut.failure), len(no_room.calls)), (Code.deadline_passed, "not_enough_time", 1))


class WorldChangeTests(unittest.TestCase):
    def test_revoked_authority_or_changed_facts_invalidate_the_thought(self) -> None:
        expected = [
            (bumped(membership_epoch=2), Code.revoked, "authority_changed", False),
            (bumped(privacy_epoch=2), Code.revoked, "authority_changed", False),
            (lambda reader: setattr(reader, "valid", False), Code.revoked, "authority_changed", False),
            (bumped(dna_version=4), Code.stale_context, "versions_changed", True),
            (bumped(activity_epoch=2), Code.stale_context, "versions_changed", True),
            (bumped(runtime_epoch=2), Code.stale_context, "runtime_superseded", False),
        ]
        for mutate, code, reason, retryable in expected:
            with self.subTest(reason=reason, code=code.value):
                reader = make_reader()
                model = ScriptedModel(answer(choice="o2", intent="去打工"), on_call=lambda n, reader=reader, mutate=mutate: mutate(reader))
                result = run(reader, model, context=make_context(reader))
                self.assertIsNone(result.proposal)
                self.assertEqual((result.failure.code, reason_of(result.failure), result.failure.retryable, result.settle_outcome()),
                                 (code, reason, retryable, "succeeded"))

    def test_offer_depending_on_an_old_itinerary_is_rejected(self) -> None:
        reader = make_reader(version_state=replace(VERSIONS, itinerary_version=6))
        context = make_context(reader, offer_list=make_offers(expected=replace(VERSIONS, itinerary_version=5)))
        result = run(reader, ScriptedModel(answer(choice="o3", intent="去澳门")), context=context)
        self.assertEqual((result.failure.code, result.failure.detail), (Code.stale_context, "offer_outdated: itinerary_version"))


class ToolTests(unittest.TestCase):
    def test_one_bounded_tool_round_then_a_decision(self) -> None:
        for broken in (False, True):
            with self.subTest(tool_fails=broken):
                reader, tools = make_reader(), mock.Mock()
                tools.call.side_effect = LookupError("no plan") if broken else None
                tools.call.return_value = "09:00 上环开船，10:00 到澳门外港，傍晚回程"
                context = make_context(reader)
                model = ScriptedModel(answer(tools=[{"name": "offer_detail", "arg": "o3"}]), answer(choice="o3", intent="九点坐船去澳门"))
                result = run(reader, model, context=context, tools=tools)
                self.assertEqual({o.offer_id: o.action_kind for o in context.action_offers}[result.proposal.selected_offer_id], ActionKind.travel)
                self.assertEqual(tools.call.call_args, mock.call("offer_detail", context.action_offers[2].offer_id, pet_id="pet-1", audience=HOUSEHOLD))
                self.assertEqual([(c.kind, c.outcome) for c in result.calls],
                                 [("decision", "succeeded"), ("tool", "failed" if broken else "succeeded"), ("followup", "succeeded")])
                self.assertEqual(result.model_calls, 2)
                self.assertIn("查不到" if broken else "10:00 到澳门外港", model.calls[1][-1]["content"])

    def test_tool_limits_and_bad_requests(self) -> None:
        four = answer(tools=[{"name": "offer_detail", "arg": f"o{i}"} for i in (1, 2, 3, 1)])
        cases = [(four, Code.bad_output, "tool_not_allowed"), (answer(tools=[{"name": "search_web", "arg": "o1"}]), Code.bad_output, "tool_not_allowed"),
                 (answer(tools=[{"name": "offer_detail", "arg": "o9"}]), Code.unknown_offer, "unknown_offer")]
        for text, code, reason in cases:
            with self.subTest(text=text):
                tools, model = mock.Mock(), ScriptedModel(text, text)  # 工具已提供（两次调用放得下），两次都不合格
                result = run(make_reader(), model, tools=tools)
                self.assertEqual((result.failure.code, reason_of(result.failure), result.model_calls, tools.call.call_count), (code, reason, 2, 0))
                self.assertIn("可用工具", model.calls[0][0]["content"])
        again = ScriptedModel(answer(tools=[{"name": "offer_detail", "arg": "o3"}]), answer(tools=[{"name": "offer_detail", "arg": "o2"}]))
        result = run(make_reader(), again, tools=mock.Mock(**{"call.return_value": "09:00 开船"}))
        self.assertEqual((result.failure.code, reason_of(result.failure), result.model_calls), (Code.bad_output, "tool_not_allowed", 2))
        # 端口返回的不是文字：按查不到处理，不让决策崩掉
        odd = ScriptedModel(answer(tools=[{"name": "offer_detail", "arg": "o3"}]), answer(choice="o1", intent="那就附近走走"))
        result = run(make_reader(), odd, tools=mock.Mock())
        self.assertIsNotNone(result.proposal)
        self.assertIn(("tool", "failed"), [(c.kind, c.outcome) for c in result.calls])
        # 只剩一次调用时不提供工具：查完就没法再问了
        single = ScriptedModel(answer(choice="o1", intent="出去"))
        run(make_reader(), single, tools=mock.Mock(), grant=reservation_for("op-1", now=NOW, units=1))
        self.assertNotIn("可用工具", single.calls[0][0]["content"])


class ChatAdapterTests(unittest.TestCase):
    def test_existing_client_is_reused_with_json_mode(self) -> None:
        chat = FakeChat(replies=[answer(choice="o2", intent="去渔港打工")])
        chat.timeout = 20.0
        request = DecisionRequest(operation_id="op-1", pet_id="pet-1", purpose="life_plan", audience=HOUSEHOLD, as_of=NOW,
                                  deadline_at=NOW + timedelta(seconds=60), offers=make_offers(), model_consent=True)
        with mock.patch.object(chat, "complete", wraps=chat.complete) as spy:
            result = Brain(reader=make_reader(), model=ChatModelAdapter(chat), clock=ManualClock(NOW)).propose(request, reservation_for("op-1", now=NOW))
        self.assertEqual((result.proposal.model_ref, result.calls[0].effective_model), ("测试模型:fake-effective", "fake-effective"))
        self.assertTrue(spy.call_args.kwargs["json_mode"])
        self.assertEqual([m["role"] for m in chat.calls[0]], ["system", "user"])
        self.assertEqual(ChatModelAdapter(chat).max_call_seconds, 22.0)
        refused = Brain(reader=make_reader(valid=False), model=ChatModelAdapter(chat), clock=ManualClock(NOW)).propose(request, reservation_for("op-1", now=NOW))
        self.assertEqual((refused.failure.code, refused.calls, len(chat.calls)), (Code.revoked, (), 1))

    def test_client_failures_map_to_decision_failures(self) -> None:
        expected = {"not_configured": (Code.disabled, "not_sent", "model_disabled"), "daily_cap": (Code.budget_denied, "not_sent", "provider_cap"),
                    "http_429": (Code.provider_error, "failed", "provider_error"), "network": (Code.provider_error, "unknown", "provider_error"),
                    "malformed": (Code.provider_error, "unknown", "provider_error")}
        for client_reason, (code, outcome, reason) in expected.items():
            with self.subTest(reason=client_reason):
                with self.assertRaises(ModelCallError) as caught:
                    ChatModelAdapter(FakeChat(error=ChatUnavailable(client_reason))).complete([{"role": "user", "content": "x"}], max_tokens=10)
                self.assertEqual((caught.exception.code, caught.exception.outcome), (code, outcome))
                result = run(make_reader(), ChatModelAdapter(FakeChat(error=ChatUnavailable(client_reason))))
                self.assertEqual((result.failure.code, reason_of(result.failure), [c.outcome for c in result.calls]), (code, reason, [outcome]))
        unconfigured = run(make_reader(), ChatModelAdapter(NoChat()))
        self.assertEqual((unconfigured.failure.code, unconfigured.calls), (Code.disabled, ()))


if __name__ == "__main__":
    unittest.main()
