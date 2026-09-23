"""决策上下文（工作包 C）：先授权再取资料，按受众与用途二次过滤；全家共用 DNA、每位家人的叮嘱、真实发生的事、
之前的打算（模型推断）分开记，并保留来源、可见范围与 ref；越权条目丢弃且不留原文。纯内存测试，不读库、不联网。"""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.schemas.runtime_internal import ActionKind, ActivityRef, AudienceScope, DecisionContext, DecisionFailure, DecisionFailureCode, Versions
from app.schemas.web.pets import PetDNA
from app.web_agent.decision import (BuiltContext, DecisionRequest, DnaSnapshot, Record, ServiceContextReader, build_context, destination_key_of,
                                    dna_snapshot, offers_from_options, reason_of)
from app.web_agent.decision.prompt import context_digest, render
from app.web_agent.decision.testing import MemoryReader
from app.web_pets.dna import DNARecord

UTC = timezone.utc
HK = timezone(timedelta(hours=8))
NOW = datetime(2026, 9, 23, 2, 0, tzinfo=UTC)  # 香港 10:00
HOUSEHOLD = AudienceScope("household", household_id="hh-1")
MOM = AudienceScope("private", household_id="hh-1", user_id="u-mom")
PUBLIC = AudienceScope("public")
VERSIONS = Versions(runtime_epoch=1, activity_epoch=1, dna_version=3, privacy_epoch=1, membership_epoch=1)
Code = DecisionFailureCode

OPTIONS = [
    SimpleNamespace(destination_key="local:stroll", title="在家附近走走", summary="不花钱，出门透透气。", fee=0, total_minutes=64, available=True, affordable=True),
    SimpleNamespace(destination_key="work:fishing_port", title="去渔港帮忙收网", summary="干 3 小时活，工钱存进银行卡。", fee=0, total_minutes=200,
                    available=True, affordable=True),
    SimpleNamespace(destination_key="local:city_trip", title="进城逛逛", summary="打车去城里逛一逛。", fee=30, total_minutes=140, available=True, affordable=False),
    SimpleNamespace(destination_key="macau_ferry", title="坐船去澳门", summary="按官网船期出发的一日行。", fee=40, total_minutes=600, available=False,
                    affordable=True, reference_note="运营方船期"),
]


def offers(as_of: datetime = NOW):
    return offers_from_options(OPTIONS, pet_id="pet-1", as_of=as_of, expected_versions=VERSIONS, income_of=lambda key: 28 if key.startswith("work:") else 0)


def request(audience: AudienceScope = HOUSEHOLD, offer_list=None, purpose: str = "life_plan") -> DecisionRequest:
    return DecisionRequest(operation_id="op-1", pet_id="pet-1", purpose=purpose, audience=audience, as_of=NOW, deadline_at=NOW + timedelta(seconds=30),
                           offers=offers() if offer_list is None else offer_list)


def note(ref: str, text: str, *, purposes=("travel_preference",), scope=MOM, kind="habit", model_ok=True, source="owner_report") -> Record:
    return Record(ref=ref, source=source, text=text, scope=scope, kind=kind, purposes=purposes, model_ok=model_ok)


def event(ref: str, text: str, *, scope=HOUSEHOLD, source="world_event") -> Record:
    return Record(ref=ref, source=source, text=text, scope=scope, kind="home", observed_at=NOW - timedelta(hours=3))


def reader(**kwargs) -> MemoryReader:
    dna = DnaSnapshot(fields={"personality": ("慢热，恋家",), "habits": ("午后在窗台晒太阳",), "owner_title": ("妈妈",),
                              "shared_memories": ("我们的暗号是咪咪",), "voice_style": ("慢吞吞",)}, confirmed=True)
    base = dict(version_state=VERSIONS, dna=dna, local=NOW.astimezone(HK))
    base.update(kwargs)
    return MemoryReader(**base)


def built(source: MemoryReader, req: DecisionRequest | None = None) -> BuiltContext:
    result = build_context(source, req or request())
    assert isinstance(result, BuiltContext), result
    return result


class HouseholdContextTests(unittest.TestCase):
    def test_keeps_only_life_material_with_source_scope_and_ref(self) -> None:
        travel = note("note:cn-a", "它最喜欢去海边看渔船回港")
        chat_only = note("note:cn-b", "它怕打雷时会钻进被子里", purposes=("private_chat",))
        no_consent = note("note:cn-c", "哥哥交代它爱去书店闻纸味", scope=AudienceScope("private", household_id="hh-1", user_id="u-bro"), model_ok=False)
        private_kind = note("note:cn-d", "我很后悔那天没有陪着它", kind="owner_private")
        inferred = note("note:cn-e", "它可能喜欢热闹", scope=HOUSEHOLD, kind="inference")
        elsewhere = note("note:cn-f", "别人家的叮嘱", scope=AudienceScope("private", household_id="hh-2", user_id="u-x"))
        source = reader(memory_records=[travel, chat_only, no_consent, private_kind, inferred, elsewhere])
        result = built(source)
        context = result.context
        # DNA：名字、物种，加上过日子相关的共用栏目；称呼、小暗号、说话方式不进
        self.assertEqual(set(context.permitted_dna), {"name", "species", "personality", "habits"})
        self.assertEqual((context.permitted_dna["name"], context.permitted_dna["personality"]), ("测试伙伴", ("慢热，恋家",)))
        for name in ("owner_title", "shared_memories", "voice_style"):
            self.assertIn(f"dna:{name}:not_for_life_plan", result.dropped)
        # 叮嘱：只有允许用于出行偏好、且本人同意交给模型的那一条；它的范围仍是这位家人私有
        self.assertEqual([(f.ref, f.source, f.scope) for f in context.memory_refs], [("note:cn-a", "owner_report", MOM)])
        for ref, reason in (("cn-b", "purpose_not_granted"), ("cn-c", "member_model_consent"), ("cn-d", "never_projected"),
                            ("cn-e", "never_projected"), ("cn-f", "other_household")):
            self.assertIn(f"note:{ref}:{reason}", result.dropped)
        joined = " ".join(result.dropped)
        for secret in (chat_only.text, no_consent.text, private_kind.text, elsewhere.text, "咪咪", "妈妈"):
            self.assertNotIn(secret, joined)
        # 只向读取端口要生活类用途；此刻的钟点与余额是事实，放在观察最前面
        self.assertIn("memory_items:household:home_interaction,travel_preference", source.calls)
        self.assertEqual(context.versions, VERSIONS)
        self.assertEqual([(f.ref, f.source, f.text) for f in context.observations[:2]],
                         [("clock:pet-1", "world_event", "你那边现在是 10:00"), ("wallet:pet-1", "world_event", "银行卡余额 20 星币")])

    def test_other_household_private_memories_and_thoughts_are_not_observations(self) -> None:
        records = [
            event("event:jn-1:home", "昨天收工回到家：去渔港帮忙收网"),
            event("event:other", "别的家庭发生的事", scope=AudienceScope("household", household_id="hh-2")),
            event("collection:cm-1", "和妈妈一起听歌的回忆", scope=MOM),
            event("ref:ferry", "官网船期：上环 09:00 开往澳门", scope=PUBLIC, source="external_reference"),
            event("thought:pp-1", "它大概想去看海", source="model_interpretation"),
        ]
        result = built(reader(observation_records=records))
        self.assertEqual([f.ref for f in result.context.observations[2:]], ["event:jn-1:home", "ref:ferry"])
        for ref, reason in (("event:other", "scope_not_allowed"), ("collection:cm-1", "scope_not_allowed"), ("thought:pp-1", "source_not_allowed")):
            self.assertIn(f"{ref}:{reason}", result.dropped)

    def test_prior_plans_stay_marked_as_thoughts(self) -> None:
        plans = [Record("plan:pp-1", "model_interpretation", "攒够钱去看海", HOUSEHOLD, "plan"),
                 Record("suggestion:hh-1", "owner_report", "有家人建议：去渔港帮忙", HOUSEHOLD, "suggestion", deadline_at=NOW + timedelta(hours=5))]
        context = built(reader(commitment_records=plans)).context
        self.assertEqual([(f.ref, f.source) for f in context.commitments], [("plan:pp-1", "model_interpretation"), ("suggestion:hh-1", "owner_report")])
        self.assertFalse(any("攒够钱" in str(v) for v in context.permitted_dna.values()))
        text = render(context).messages[1]["content"]
        self.assertIn("攒够钱去看海（之前的想法，不是已经发生的事）", text)
        self.assertIn("有家人建议：去渔港帮忙（5 小时之内）", text)


class AudienceTests(unittest.TestCase):
    def test_resident_context_has_no_family_material(self) -> None:
        source = reader(memory_records=[note("note:cn-a", "它最喜欢去海边看渔船回港")],
                        commitment_records=[Record("suggestion:hh", "owner_report", "家人建议：去渔港帮忙", HOUSEHOLD, "suggestion"),
                                            Record("promise:p1", "world_event", "答应过邻居一起散步", PUBLIC, "promise")],
                        observation_records=[event("event:pub-1", "在驿站门口晒太阳", scope=PUBLIC)])
        result = built(source, request(PUBLIC))
        context = result.context
        self.assertEqual(context.memory_refs, ())
        self.assertIn("note:cn-a:no_household", result.dropped)
        self.assertEqual([c.ref for c in context.commitments], ["promise:p1"])
        self.assertIn("suggestion:hh:scope_not_allowed", result.dropped)
        self.assertEqual([o.ref for o in context.observations[2:]], ["event:pub-1"])
        self.assertTrue(all(o.scope == PUBLIC for o in context.observations[:2]))

    def test_invalid_or_unsupported_requests_are_explicit(self) -> None:
        cases = [
            (reader(valid=False), request(), Code.revoked, "audience_invalid"),
            (reader(), request(MOM), Code.disabled, "unsupported_audience"),
            (reader(), request(purpose="private_reply"), Code.disabled, "unsupported_purpose"),
            (reader(brief=None), request(), Code.revoked, "pet_not_found"),
        ]
        for source, req, code, reason in cases:
            with self.subTest(reason=reason):
                result = build_context(source, req)
                self.assertIsInstance(result, DecisionFailure)
                self.assertEqual((result.code, reason_of(result)), (code, reason))

    def test_versions_moved_after_the_heartbeat_stop_before_thinking(self) -> None:
        cases = [(replace(VERSIONS, activity_epoch=0), Code.stale_context, "changed_before_thinking"),
                 (replace(VERSIONS, membership_epoch=0), Code.revoked, "authority_changed"),
                 (VERSIONS, None, None)]
        for expected, code, reason in cases:
            with self.subTest(expected=expected):
                req = replace(request(), expected_versions=expected)
                result = build_context(reader(), req)
                if code is None:
                    self.assertIsInstance(result, BuiltContext)
                else:
                    self.assertEqual((result.code, reason_of(result)), (code, reason))

    def test_unknown_place_means_no_local_clock(self) -> None:
        """住在哪都不知道时不编当地时间（心跳会给出明确的不可用结果）；知道就按那个地方的时区。"""
        def reader_for(home, place):
            web = SimpleNamespace(residents=SimpleNamespace(residence_of=lambda pet_id: None), homes=SimpleNamespace(by_pet=lambda pet_id: home),
                                  home_places=SimpleNamespace(get=lambda home_id: place))
            return ServiceContextReader(web, versions_of=lambda pet_id: VERSIONS, now=lambda: NOW)

        self.assertIsNone(reader_for(None, None).local_time("pet-1", NOW))
        somewhere = reader_for(SimpleNamespace(home_id="home-1"), SimpleNamespace(timezone="Asia/Tokyo")).local_time("pet-1", NOW)
        self.assertEqual((str(somewhere.tzinfo), somewhere.hour), ("Asia/Tokyo", 11))

    def test_reader_failure_does_not_give_partial_context(self) -> None:
        source = reader()

        def broken(*args, **kwargs):
            raise RuntimeError("db locked")

        source.observations = broken
        result = build_context(source, request())
        self.assertEqual((result.code, reason_of(result), result.retryable), (Code.provider_error, "reader_failed", True))


class OfferTests(unittest.TestCase):
    def test_offers_copy_rule_facts_and_skip_infeasible(self) -> None:
        items = offers()
        self.assertEqual([o.source_ref for o in items], ["destination:local:stroll", "destination:work:fishing_port"])
        stroll, work = items
        self.assertEqual((stroll.action_kind, work.action_kind), (ActionKind.local_activity, ActionKind.work))
        self.assertEqual((work.cost_bounds, work.income_bounds, work.duration_bounds), ((0, 0), (28, 28), (200, 200)))
        self.assertEqual((destination_key_of(work), work.valid_until, work.expected_versions), ("work:fishing_port", NOW + timedelta(minutes=10), VERSIONS))
        self.assertTrue(work.summary.startswith("去渔港帮忙收网："))
        self.assertNotEqual(stroll.offer_id, work.offer_id)

    def test_expired_offers_are_dropped_and_something_must_remain(self) -> None:
        stale = offers(NOW - timedelta(minutes=11))
        result = built(reader(), request(offer_list=stale))
        self.assertEqual(result.context.action_offers, ())
        self.assertEqual(sum(d.endswith(":expired") for d in result.dropped), 2)
        for activity in (None, ActivityRef("travel", "journey:jn-9", ends_at=NOW - timedelta(minutes=1))):
            with self.subTest(activity=activity):
                failure = build_context(reader(activity_ref=activity), request(offer_list=()))
                self.assertEqual((failure.code, reason_of(failure)), (Code.stale_context, "no_offers"))

    def test_limits_bound_the_context(self) -> None:
        many = [event(f"event:{i}", f"第 {i} 件事" + "很长" * 60) for i in range(20)]
        result = built(reader(observation_records=many))
        self.assertEqual(len(result.context.observations), 2 + 8)  # 此刻的钟点与余额 + 最多 8 件事
        self.assertEqual(sum(d.endswith(":over_limit") for d in result.dropped), 12)
        self.assertTrue(all(len(f.text) <= 80 for f in result.context.observations))


class DnaReuseTests(unittest.TestCase):
    """复用现有 DNA 记录：同样的事实，不同的 DNA 形成不同的上下文与提示。"""

    def _context(self, personality: str, habits: list[str]) -> DecisionContext:
        dna = PetDNA(personality=personality, habits=habits, owner_title="妈妈", shared_memories=["咪咪是暗号"])
        record = DNARecord(dna=dna, confirmed=True, sources=["owner"], updated_at=NOW, version=4)
        source = reader(dna=dna_snapshot(record), observation_records=[event("event:jn-1:home", "昨天收工回到家：去渔港帮忙收网")])
        return built(source).context

    def test_same_facts_different_dna_differ(self) -> None:
        bold = self._context("好奇，爱冒险，精力旺盛", ["天一亮就想出门"])
        shy = self._context("恋家，胆小，不爱出门", ["喜欢窝在沙发上"])
        self.assertEqual(bold.observations, shy.observations)
        self.assertNotEqual(bold.permitted_dna, shy.permitted_dna)
        self.assertNotEqual(context_digest(bold), context_digest(shy))
        self.assertNotEqual(render(bold).messages[1]["content"], render(shy).messages[1]["content"])
        for context in (bold, shy):
            everything = " ".join([str(v) for v in context.permitted_dna.values()] + [f.text for f in context.observations])
            self.assertNotIn("咪咪", everything)
            self.assertNotIn("妈妈", everything)

    def test_prompt_uses_temporary_aliases_only(self) -> None:
        source = reader(memory_records=[note("note:cn-a", "它最喜欢去海边看渔船回港")],
                        observation_records=[event("event:jn-1:home", "昨天收工回到家：去渔港帮忙收网")])
        context = built(source).context
        prompt = render(context)
        text = "\n".join(m["content"] for m in prompt.messages)
        for internal in ("pet-1", "hh-1", "u-mom", "cn-a", "jn-1", "op-1") + tuple(o.offer_id for o in context.action_offers):
            self.assertNotIn(internal, text)
        self.assertEqual({prompt.aliases[a] for a in ("n1", "e3")}, {"note:cn-a", "event:jn-1:home"})
        self.assertEqual(set(prompt.offers), {"o1", "o2"})
        for expected in ("银行卡余额 20 星币", "你那边现在是 10:00", "[3 小时前] 昨天收工回到家", "continue：继续在家待着", "收入 28 星币", "家人已确认"):
            self.assertIn(expected, text)

    def test_unsaved_dna_is_labelled_unconfirmed(self) -> None:
        draft = Versions(runtime_epoch=1, activity_epoch=1, dna_version=0, privacy_epoch=1, membership_epoch=1)
        context = built(reader(version_state=draft)).context
        self.assertIn("家人还没确认，只作参考", render(context).messages[1]["content"])


if __name__ == "__main__":
    unittest.main()
