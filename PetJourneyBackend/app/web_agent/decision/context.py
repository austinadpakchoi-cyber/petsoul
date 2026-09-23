"""构造决策上下文：先经授权读取端口取最小资料，再按受众与用途二次过滤；每条事实保留来源（FactSource）、可见范围与 ref。

life_plan（自主安排下一段生活）的规则：
- DNA 只用全家共用那一层里和“过日子”有关的栏目（性格、习惯、爱好、喜欢的地方、爱吃的、害怕的），外加名字与物种；
  称呼、小暗号等个人层与说话方式不进来。versions.dna_version＝0 表示还没保存过共用 DNA（草稿），提示里会标“家人还没确认”；
- 家人的叮嘱只收“允许用于出行偏好 / 家中互动”的，而且这位家人同意交给模型处理；只允许私信用的、主人私人倾诉与推测一律不进。
  这些私有叮嘱只能影响决定，意图里不能照抄（validation 会拦）；待领养居民（public 受众）没有家庭，不收任何家人叮嘱；
- 观察只收世界里已经发生的事与现实参考；别的家庭、某位家人私有的回忆都不给这次决策；
- 之前的打算（model_interpretation）放在承诺一栏并标明是想法，不和 DNA、事实混在一起。
读取端口若返回了不该给的条目，这里直接丢弃，只在 dropped 里记 ref 与原因，不会交给模型。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from ...schemas.runtime_internal import ActionOffer, ActivityRef, AudienceScope, ContextFact, DecisionContext, DecisionFailure, DecisionFailureCode
from .outcomes import failure
from .ports import ContextReader, DecisionRequest, Record

LIFE_DNA_FIELDS = ("personality", "habits", "hobbies", "favorite_places", "favorite_foods", "fears")
LIFE_PURPOSES = frozenset({"travel_preference", "home_interaction"})
NEVER_KINDS = frozenset({"owner_private", "inference"})
DEFAULT_LIMITS = {"memory_refs": 6, "observations": 8, "commitments": 5, "offers": 12}
DNA_TEXT_MAX, TEXT_MAX = 60, 80
CONTINUE_LABEL = {"at_home": "继续在家待着", "local_activity": "继续在附近待着", "work": "继续把手上的活干完", "travel": "按原计划继续旅途",
                  "visit": "继续在店里坐着", "exam": "继续考试"}
Code = DecisionFailureCode


@dataclass(frozen=True)
class BuiltContext:
    context: DecisionContext
    dropped: tuple[str, ...]  # 二次过滤丢掉的条目（ref:原因），不含原文


def _text(value: object, limit: int = TEXT_MAX) -> str:
    return " ".join(str(value).split())[:limit]


def visible_to(scope: AudienceScope, audience: AudienceScope) -> bool:
    """这条事实本身的范围不比受众窄：可以进上下文，也可以在表达里提到。"""
    if scope.kind == "public":
        return True
    return scope.kind == "household" and audience.kind == "household" and scope.household_id == audience.household_id


def can_continue(activity: ActivityRef | None, as_of: datetime) -> bool:
    """能不能选“继续当前活动”：在家总可以；有结束时间的活动只有还没结束才行。"""
    if activity is None or activity.kind not in CONTINUE_LABEL:
        return False
    return activity.kind == "at_home" or activity.ends_at is None or activity.ends_at > as_of


def _memory_check(audience: AudienceScope):
    def check(record: Record) -> str | None:
        if record.kind in NEVER_KINDS:
            return "never_projected"
        if record.source != "owner_report":
            return "not_owner_report"
        if not LIFE_PURPOSES.intersection(record.purposes):
            return "purpose_not_granted"
        if record.scope.kind == "private":
            if audience.kind != "household":
                return "no_household"
            if record.scope.household_id and record.scope.household_id != audience.household_id:
                return "other_household"
            return None if record.model_ok else "member_model_consent"
        return None if visible_to(record.scope, audience) else "scope_not_allowed"
    return check


def _scoped_check(audience: AudienceScope, sources: frozenset[str]):
    def check(record: Record) -> str | None:
        if not visible_to(record.scope, audience):
            return "scope_not_allowed"
        return None if record.source in sources else "source_not_allowed"
    return check


def _keep(records: Iterable[Record], limit: int, dropped: list[str], check) -> list[ContextFact]:
    kept: list[ContextFact] = []
    for record in records:
        reason = check(record)
        if reason is None and any(fact.ref == record.ref for fact in kept):
            reason = "duplicate"
        if reason is None and not _text(record.text):
            reason = "empty"
        if reason is None and len(kept) >= limit:
            reason = "over_limit"
        if reason is not None:
            dropped.append(f"{record.ref}:{reason}")
            continue
        kept.append(ContextFact(record.ref, record.source, _text(record.text), record.scope, record.observed_at, record.deadline_at))
    return kept


def _dna(brief, snapshot, dropped: list[str]) -> dict[str, str | tuple[str, ...]]:
    dna: dict[str, str | tuple[str, ...]] = {"name": _text(brief.name, 20), "species": _text(brief.species, 20)}
    for name, values in (snapshot.fields.items() if snapshot else ()):
        if name not in LIFE_DNA_FIELDS:
            dropped.append(f"dna:{name}:not_for_life_plan")
            continue
        texts = tuple(t for t in (_text(v, DNA_TEXT_MAX) for v in values or ()) if t)
        if texts:
            dna[name] = texts
    return dna


def _offers(offers: Sequence[ActionOffer], as_of: datetime, limit: int, dropped: list[str]) -> tuple[ActionOffer, ...]:
    kept: list[ActionOffer] = []
    for offer in offers:
        if offer.valid_until <= as_of:
            dropped.append(f"offer:{offer.offer_id}:expired")
        elif any(o.offer_id == offer.offer_id for o in kept):
            dropped.append(f"offer:{offer.offer_id}:duplicate")
        elif len(kept) >= limit:
            dropped.append(f"offer:{offer.offer_id}:over_limit")
        else:
            kept.append(offer)
    return tuple(kept)


def build_context(reader: ContextReader, request: DecisionRequest) -> BuiltContext | DecisionFailure:
    op, pet_id, audience = request.operation_id, request.pet_id, request.audience
    if request.purpose != "life_plan":
        return failure(op, Code.disabled, "unsupported_purpose", str(request.purpose))
    if audience.kind not in ("household", "public"):
        return failure(op, Code.disabled, "unsupported_audience", "life_plan is decided per pet for its household, or in public for a resident")
    limits = {**DEFAULT_LIMITS, **request.limits}
    dropped: list[str] = []
    try:
        versions = reader.versions(pet_id)
        if not reader.audience_valid(pet_id, audience):
            return failure(op, Code.revoked, "audience_invalid")
        moved = request.expected_versions.stale_fields(versions) if request.expected_versions is not None else ()
        if moved:
            revoked = [name for name in moved if name in ("membership_epoch", "privacy_epoch")]
            return (failure(op, Code.revoked, "authority_changed", ",".join(revoked)) if revoked
                    else failure(op, Code.stale_context, "changed_before_thinking", ",".join(moved)))
        brief = reader.pet_brief(pet_id)
        if brief is None:
            return failure(op, Code.revoked, "pet_not_found")
        dna = _dna(brief, reader.shared_dna(pet_id), dropped)
        memory = _keep(reader.memory_items(pet_id, audience, sorted(LIFE_PURPOSES), limits["memory_refs"]), limits["memory_refs"], dropped,
                       _memory_check(audience))
        observations = _keep(reader.observations(pet_id, audience, limits["observations"]), limits["observations"], dropped,
                             _scoped_check(audience, frozenset({"world_event", "external_reference"})))
        commitments = _keep(reader.commitments(pet_id, audience, limits["commitments"]), limits["commitments"], dropped,
                            _scoped_check(audience, frozenset({"owner_report", "world_event", "model_interpretation"})))
        activity = reader.activity(pet_id, request.as_of)
        local = reader.local_time(pet_id, request.as_of)
        balance = reader.wallet_balance(pet_id)
    except Exception as exc:  # noqa: BLE001 - 读取失败：不带着半份资料去问模型
        return failure(op, Code.provider_error, "reader_failed", type(exc).__name__)
    now_facts = []
    if local is not None:
        now_facts.append(ContextFact(f"clock:{pet_id}", "world_event", f"你那边现在是 {local:%H:%M}", audience, request.as_of))
    if balance is not None:
        now_facts.append(ContextFact(f"wallet:{pet_id}", "world_event", f"银行卡余额 {balance} 星币", audience, request.as_of))
    offers = _offers(request.offers, request.as_of, limits["offers"], dropped)
    if not offers and not can_continue(activity, request.as_of):
        return failure(op, Code.stale_context, "no_offers", "no feasible offer and nothing to continue")
    context = DecisionContext(
        operation_id=op, purpose=request.purpose, pet_id=pet_id, audience_scope=audience, as_of=request.as_of, deadline_at=request.deadline_at,
        versions=versions, current_activity=activity, permitted_dna=dna, memory_refs=tuple(memory), observations=tuple(now_facts + observations),
        commitments=tuple(commitments), action_offers=offers, reason_codes=tuple(request.reason_codes), conversation_id=request.conversation_id,
        input_high_watermark=request.input_high_watermark)
    return BuiltContext(context, tuple(dropped))


def private_texts(context: DecisionContext) -> tuple[str, ...]:
    """某位家人私有的原话：可以影响决定，但意图里不能照抄（表达侧不泄露来源与原文）。"""
    return tuple(fact.text for fact in context.memory_refs + context.commitments if not visible_to(fact.scope, context.audience_scope))
