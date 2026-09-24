"""研究结果的程序核对与计划成稿（TRV-03；方案 §11.1；合同 11.3、11.4）。纯函数：不连库、不联网。

逐条事实给结论：
  - `verified`：引用的来源都在本次结果里、搜索类事实的检索真的执行过、时间可判且覆盖出行；
  - `unverified`：没有来源、没有能判断的时间；
  - `stale`：过了有效期（左闭右开 `[valid_from, valid_until)`，合同 §29.3）、材料太旧、或不覆盖出行窗口。`retrieved_at` 只是抓取时间，**不刷新材料本身的年代**；
  - `conflicting`：同一地点同一类别，已核实的值互相矛盾（两边都作废）；
  - `rejected`：引用了本次结果里不存在的 `source_id`（假来源）；或票价、车费认不出金额与币种——
    币种只认 ISO 4217 三字母大写（I 裁定），「元」「人民币」「rmb」一律认不出，**整条拒、落库不带原值**（原样只留在回执里备查）。

**检索没真正执行（合同 11.3：`tool_executions < 1` 或执行标识为空）时，搜索得来的事实不落库、不进计划**——
回答正文里写了「来源」也不算。

拒绝的是那条事实，不是整份计划（合同 11.4）：**只看主目的地**，关键项不合格就挂等待原因，
可选项（票价、特色）不合格就省略；顺路建议没有已核验事实支撑就不进计划；带数字的提醒必须有已核验事实支撑。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..utils import iso, parse_dt
from .model import FACT_CONFLICTING, FACT_STALE, FACT_UNVERIFIED, ROLE_PRIMARY, ROLE_SUGGESTION, WEATHER_UNSUITABLE
from .ports import ResearchFact, ResearchResult

VERIFIED, UNVERIFIED, STALE, CONFLICT, REJECTED = "verified", "unverified", "stale", "conflicting", "rejected"  # 与 P 编译器同名
CRITICAL = frozenset({"destination_identity", "route", "opening", "weather", "notice"})
REQUIRED = ("destination_identity", "route")  # 主目的地身份、可执行路径：没有已核验的就等待
WINDOWED = frozenset({"opening", "weather", "notice"})  # 必须覆盖出行时间
# 材料本身的年代（observed_at／published_at）距此刻的上限。按类别配置，不是全表一律 24 小时（方案 §11.1）
TTL = {"destination_identity": timedelta(days=365), "route": timedelta(days=30), "opening": timedelta(days=14),
       "weather": timedelta(hours=12), "notice": timedelta(days=14), "ticket_price": timedelta(days=90),
       "transport_price": timedelta(days=30), "feature": timedelta(days=365)}
SEARCH = "search"
DIGITS = re.compile(r"[0-9０-９¥￥$]")
PRICED = frozenset({"ticket_price", "transport_price"})  # 现实参考费用（合同 §8：金额／币种／日期／是否估算；日期用事实自己的时间字段）
CURRENCY = re.compile(r"[A-Z]{3}")  # ISO 4217 字母码的形状；只查形状，不查代码表


@dataclass(frozen=True, slots=True)
class FactVerdict:
    key: str
    verdict: str
    reason: str | None
    critical: bool


@dataclass(frozen=True, slots=True)
class Review:
    verdicts: dict[str, FactVerdict]
    kept: tuple[ResearchFact, ...]  # 要落库的事实（没执行检索时，搜索类的一条不留）
    waiting: frozenset[str]  # 研究侧等待原因（只由主目的地的关键项决定）


def fact_id(operation_id: str, key: str) -> str:
    """稳定编号：同一次尝试、同一条事实，任何进程算出来都一样（认领复用时不会变出第二份）。"""
    return "tf-" + hashlib.sha256(f"{operation_id}#{key}".encode()).hexdigest()[:20]


def review(result: ResearchResult, *, now: datetime, primary: tuple[str, ...], window: tuple[str | None, str | None] = (None, None)) -> Review:
    """`primary`：主目的地在事实里可能用的写法（destination_key、准确名称）。"""
    sources = {s.source_id: s for s in result.sources}
    kept = tuple(f for f in result.facts if result.searched or f.verification != SEARCH)
    verdicts = {f.key: _judge(f, sources, now, window) for f in kept}
    groups: dict[tuple[str, str], list[ResearchFact]] = defaultdict(list)
    for fact in kept:
        if verdicts[fact.key].verdict == VERIFIED:
            groups[(fact.category, fact.subject)].append(fact)
    for group in groups.values():
        if len({_canon(f.value) for f in group}) > 1:
            for fact in group:
                verdicts[fact.key] = FactVerdict(fact.key, CONFLICT, "conflicting", fact.category in CRITICAL)
    return Review(verdicts, kept, _waiting(kept, verdicts, primary))


def _judge(fact: ResearchFact, sources: dict, now: datetime, window: tuple[str | None, str | None]) -> FactVerdict:
    critical = fact.category in CRITICAL

    def verdict(value: str, reason: str | None = None) -> FactVerdict:
        return FactVerdict(fact.key, value, reason, critical)

    if not fact.source_ids:
        return verdict(UNVERIFIED, "no_sources")
    if any(sid not in sources for sid in fact.source_ids):
        return verdict(REJECTED, "unknown_source")
    if fact.category in PRICED and not price_ok(fact.value):
        return verdict(REJECTED, "unrecognized_price")
    until = _dt(fact.valid_until)
    if until is not None and until <= now:  # 左闭右开（合同 §29.3）：到期那一刻已经过期
        return verdict(STALE, "expired")
    material = _dt(fact.observed_at) or _latest_published(fact, sources)  # 材料本身的年代：观测时间或来源发布时间，不用抓取时间
    if fact.category in WINDOWED:
        return _judge_windowed(fact, material, now, window, verdict)
    limit = TTL.get(fact.category)
    if limit is not None and material is not None and now - material > limit:
        return verdict(STALE, "too_old")
    return verdict(VERIFIED)


def _judge_windowed(fact: ResearchFact, material: datetime | None, now: datetime, window, verdict) -> FactVerdict:
    """开放、天气、公告：要么有覆盖出行窗口的有效期，要么（当天出行、没给窗口）材料够新。
    有效期左闭右开（合同 §29.3）：出行时刻只是一个点（只给起点、或当天出行）时，`valid_until` 必须**晚于**它才算覆盖。"""
    start, end = _dt(window[0]), _dt(window[1])
    begin, until = _dt(fact.valid_from), _dt(fact.valid_until)
    if begin is not None or until is not None:
        wanted_start, wanted_end = start or now, end or start or now
        covered = (begin is None or begin <= wanted_start) and (until is None or (until > wanted_start and until >= wanted_end))
        return verdict(VERIFIED) if covered else verdict(STALE, "not_covering_window")
    if material is None:
        return verdict(UNVERIFIED, "no_date")
    if start is not None and start - now > TTL[fact.category]:
        return verdict(STALE, "not_covering_window")  # 只有此刻的观测，出行却在更晚：观测管不到那天
    return verdict(VERIFIED) if now - material <= TTL[fact.category] else verdict(STALE, "too_old")


def _waiting(kept: tuple[ResearchFact, ...], verdicts: dict[str, FactVerdict], primary: tuple[str, ...]) -> frozenset[str]:
    reasons: set[str] = set()
    for category in sorted(CRITICAL):
        about = [verdicts[f.key].verdict for f in kept if f.category == category and f.subject in primary]
        if VERIFIED in about:
            continue
        if not about:
            if category in REQUIRED:
                reasons.add(FACT_UNVERIFIED)
            continue
        reasons.add(FACT_CONFLICTING if CONFLICT in about else FACT_STALE if STALE in about else FACT_UNVERIFIED)
    for fact in kept:
        if fact.category == "weather" and fact.subject in primary and verdicts[fact.key].verdict == VERIFIED \
                and isinstance(fact.value, dict) and fact.value.get("suitable") is False:
            reasons.add(WEATHER_UNSUITABLE)
    return frozenset(reasons)


def build_plan(*, wish, result: ResearchResult, outcome: Review, operation_id: str, plan_revision: int, now: datetime) -> tuple[dict, list[dict]]:
    """发布一版计划：站点、提醒都由**已核验**事实支持；返回 (计划行, 事实行)。"""
    verified = {key for key, v in outcome.verdicts.items() if v.verdict == VERIFIED}
    by_key = {f.key: f for f in outcome.kept}
    draft = result.draft
    stops = _stops(wish, draft, verified, by_key, operation_id)
    tips = []
    for index, tip in enumerate(draft.owner_tips if draft else ()):
        keys = draft.tip_fact_keys[index] if index < len(draft.tip_fact_keys) else ()
        if keys and all(k in verified for k in keys):
            tips.append({"text": tip, "fact_ids": [fact_id(operation_id, k) for k in keys]})
        elif not keys and not DIGITS.search(tip):
            tips.append({"text": tip, "fact_ids": []})
    used = {sid for key in verified for sid in by_key[key].source_ids}
    sources = [{"source_id": s.source_id, "url": s.url, "publisher": s.publisher, "retrieved_at": s.retrieved_at,
                "published_at": s.published_at} for s in result.sources if s.source_id in used]
    windowed = [by_key[k] for k in sorted(verified) if by_key[k].category in WINDOWED and by_key[k].subject in _names(wish)]
    stamp = iso(now)
    plan = {"plan_id": wish["plan_id"], "plan_revision": plan_revision, "wish_id": wish["wish_id"],
            "wish_revision_at_build": int(wish["wish_revision"]), "pet_id": wish["pet_id"], "destination_key": wish["destination_key"],
            "operation_id": operation_id, "title": (draft.title if draft and draft.title else f"想去{wish['destination_name']}")[:40],
            "summary": (draft.summary if draft else "")[:400], "stops_json": _json(stops), "owner_tips_json": _json(tips),
            "rain_alternative": draft.rain_alternative if draft else None,
            "preconditions_json": _json([fact_id(operation_id, f.key) for f in windowed]), "sources_json": _json(sources),
            "valid_from": _edge([f.valid_from for f in windowed], max), "valid_until": _edge([f.valid_until for f in windowed], min),
            "journey_id": None, "created_at": stamp}
    rows = [_fact_row(f, outcome.verdicts[f.key], wish["wish_id"], operation_id, result, stamp) for f in outcome.kept]
    return plan, rows


def _stops(wish, draft, verified: set[str], by_key: dict, operation_id: str) -> list[dict]:
    names = _names(wish)
    drafted = list(draft.stops) if draft else []
    stops, has_primary = [], False
    for stop in drafted:
        support = [k for k in stop.fact_keys if k in verified]
        primary = stop.role == ROLE_PRIMARY and stop.name in names and not has_primary
        if not primary and not support:
            continue  # 顺路建议没有已核验事实支撑：不进计划
        has_primary = has_primary or primary
        where = next((by_key[k].value for k in support if by_key[k].category == "destination_identity" and isinstance(by_key[k].value, dict)), {})
        stops.append({"name": stop.name, "role": ROLE_PRIMARY if primary else ROLE_SUGGESTION, "why": stop.why, "tip": stop.tip,
                      "fact_ids": [fact_id(operation_id, k) for k in support], "verified": bool(support),
                      "lat": where.get("lat"), "lng": where.get("lng"), "visited_event_ids": []})
    if not has_primary:
        stops.insert(0, {"name": wish["destination_name"], "role": ROLE_PRIMARY, "why": "", "tip": "", "fact_ids": [], "verified": False,
                         "lat": None, "lng": None, "visited_event_ids": []})
    return stops


def _fact_row(fact: ResearchFact, verdict: FactVerdict, wish_id: str, operation_id: str, result: ResearchResult, stamp: str) -> dict:
    retrieved = [s.retrieved_at for s in result.sources if s.source_id in fact.source_ids and s.retrieved_at]
    published = [s.published_at for s in result.sources if s.source_id in fact.source_ids and s.published_at]
    value = None if fact.category in PRICED and not price_ok(fact.value) else fact.value  # 认不出的费用不落原值，页面无从去猜
    return {"fact_id": fact_id(operation_id, fact.key), "operation_id": operation_id, "wish_id": wish_id, "category": fact.category,
            "subject": fact.subject, "value_json": _json(value), "source_ids_json": _json(list(fact.source_ids)),
            "retrieved_at": min(retrieved) if retrieved else None, "published_at": max(published) if published else None,
            "observed_at": fact.observed_at, "valid_from": fact.valid_from, "valid_until": fact.valid_until,
            "verification": fact.verification, "conclusion": fact.conclusion, "verdict": verdict.verdict,
            "blocks_departure": int(verdict.critical and verdict.verdict != VERIFIED), "created_at": stamp}


def money(amount, currency) -> tuple[float | None, str | None]:
    """金额与币种要么一起可信、要么一起为 None：金额只认非负有限数，币种只认 ISO 4217 三字母大写（I 裁定）。
    认不出就**整条不带**，不留一个页面猜不动的字符串——与「未核就是 None，不写 0」同一个道理。"""
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
        return None, None
    if not isinstance(currency, str) or CURRENCY.fullmatch(currency) is None:
        return None, None
    return float(amount), currency


def price_ok(value) -> bool:
    """票价、车费这类事实的值：`{"amount": 非负数, "currency": ISO 4217, "estimated": bool}`。不知道是不是估算，也算认不出。"""
    return isinstance(value, dict) and isinstance(value.get("estimated"), bool) and money(value.get("amount"), value.get("currency"))[1] is not None


def _names(wish) -> tuple[str, ...]:
    return (wish["destination_key"], wish["destination_name"])


def _latest_published(fact: ResearchFact, sources: dict) -> datetime | None:
    dates = [_dt(sources[sid].published_at) for sid in fact.source_ids if sid in sources]
    dates = [d for d in dates if d is not None]
    return max(dates) if dates else None


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = parse_dt(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _edge(values: list[str | None], pick) -> str | None:
    dates = [_dt(v) for v in values if v]
    return iso(pick(dates)) if dates else None


def _canon(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
