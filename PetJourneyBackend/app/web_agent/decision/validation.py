"""校验模型输出：只接受选中给定行动（或 continue）的一个 JSON 对象。坏结构、未知行动、过期、越界参数、自己编的钱与时间、
编造的依据编号、照抄家人私密原话，都给出明确的失败码（runtime-internal 的 10 个码之一）和更细的原因。

校验只看结构与“是不是在给定范围里”，不替模型改答案；能否执行、钱够不够、权限还在不在，最终由集成窗口在事务里再核一次。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

from ...schemas.runtime_internal import DecisionContext, DecisionFailureCode, ParamBound
from .context import can_continue, private_texts
from .ports import CallLimits, ToolSpec
from .prompt import RenderedPrompt

Code = DecisionFailureCode
ALLOWED_KEYS = frozenset({"choice", "intent", "review_after_minutes", "uses", "remember", "parameters"})
# 模型不能自己给出的“事实数字”：钱、收入、时长、时刻、地点坐标
FABRICATED_KEYS = frozenset({"fee", "price", "cost", "coins", "star_coins", "wage", "pay", "salary", "income", "minutes", "duration", "hours", "time",
                             "departure", "depart_at", "arrive_at", "arrival", "place", "address", "lat", "lng", "route", "budget"})
INTENT_MAX = 60
USES_MAX, REMEMBER_MAX = 12, 3
ECHO_WINDOW, ECHO_MIN = 8, 4
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)
_URL = re.compile(r"https?://|www\.", re.IGNORECASE)
_NOISE = re.compile(r"[\s，,。．.；;、！!？?：:“”\"'‘’（）()【】\[\]…~～·-]+")


@dataclass(frozen=True)
class Choice:
    offer_id: str | None
    parameters: dict[str, str | int]
    intent: str
    review_after_seconds: int | None
    used_refs: tuple[str, ...]
    remember_refs: tuple[str, ...]


@dataclass(frozen=True)
class ToolRequest:
    calls: tuple[tuple[str, str, str], ...]  # (工具名, 模型写的编号, 解析后的 offer_id 或 ref)


@dataclass(frozen=True)
class Invalid:
    code: DecisionFailureCode
    reason: str  # 更细的原因，写进 DecisionFailure.detail 开头
    problem: str  # 给修复提示用的说明：不含私人原文
    repairable: bool = True


def parse_json(text: str) -> dict | Invalid:
    raw = (text or "").strip()
    fenced = _FENCE.match(raw)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return Invalid(Code.bad_output, "invalid_json", "不是一个合法的 JSON 对象")
    return data if isinstance(data, dict) else Invalid(Code.bad_output, "invalid_json", "输出必须是一个 JSON 对象")


def _normalized(text: str) -> str:
    return _NOISE.sub("", text or "")


def echoes_private_text(intent: str, secrets: tuple[str, ...]) -> bool:
    """intent 是否照抄了某位家人的私密原话：连续 8 个字相同；原话不足 8 个字（至少 4 个字）时整句出现。"""
    said = _normalized(intent)
    for secret in secrets:
        norm = _normalized(secret)
        if len(norm) < ECHO_MIN:
            continue
        if len(norm) <= ECHO_WINDOW:
            if norm in said:
                return True
        elif any(norm[i:i + ECHO_WINDOW] in said for i in range(len(norm) - ECHO_WINDOW + 1)):
            return True
    return False


def _string_list(value, limit: int) -> list[str] | None:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > limit or not all(isinstance(v, str) for v in value):
        return None
    return value


def _param_ok(bound: ParamBound, value) -> bool:
    if bound.choices:
        return isinstance(value, str) and value in bound.choices
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return (bound.minimum is None or value >= bound.minimum) and (bound.maximum is None or value <= bound.maximum)


def _tools(data: dict, prompt: RenderedPrompt, specs: tuple[ToolSpec, ...], tools_left: int, final_only: bool) -> ToolRequest | Invalid:
    if final_only or not prompt.tools_offered:
        return Invalid(Code.bad_output, "tool_not_allowed", "这一次不能调用工具，请直接给出决定", repairable=not final_only)
    calls = data.get("tools")
    if set(data) != {"tools"} or not isinstance(calls, list) or not calls or not all(isinstance(c, dict) for c in calls):
        return Invalid(Code.bad_output, "schema_violation", "调用工具时只输出 tools 一个字段，值是非空的对象列表")
    if len(calls) > tools_left:
        return Invalid(Code.bad_output, "tool_not_allowed", f"工具最多还能用 {tools_left} 次")
    by_name = {tool.name: tool for tool in specs}
    resolved: list[tuple[str, str, str]] = []
    for call in calls:
        name, arg = call.get("name"), call.get("arg")
        if set(call) != {"name", "arg"} or not isinstance(name, str) or not isinstance(arg, str):
            return Invalid(Code.bad_output, "schema_violation", "每个工具调用只能有 name 和 arg 两个字符串字段")
        spec = by_name.get(name)
        if spec is None:
            return Invalid(Code.bad_output, "tool_not_allowed", f"没有叫 {name[:20]} 的工具")
        table = prompt.offers if spec.arg == "offer" else prompt.aliases
        if arg not in table:
            return (Invalid(Code.unknown_offer, "unknown_offer", f"{arg[:12]} 不是给出的行动编号") if spec.arg == "offer"
                    else Invalid(Code.bad_output, "unknown_reference", f"{arg[:12]} 不是给出的资料编号"))
        resolved.append((name, arg, table[arg]))
    return ToolRequest(tuple(resolved))


def _references(data: dict, prompt: RenderedPrompt) -> tuple[tuple[str, ...], tuple[str, ...]] | Invalid:
    uses = _string_list(data.get("uses"), USES_MAX)
    remember = _string_list(data.get("remember"), REMEMBER_MAX)
    if uses is None or remember is None:
        return Invalid(Code.bad_output, "schema_violation", "uses、remember 必须是字符串列表（remember 最多 3 个）")
    used: list[str] = []
    for alias in uses:
        ref = prompt.aliases.get(alias) or (f"offer:{prompt.offers[alias]}" if alias in prompt.offers else None)
        if ref is None:
            return Invalid(Code.bad_output, "unknown_reference", f"{alias[:12]} 不是给出的资料编号")
        used.append(ref)
    if any(not alias.startswith("e") or alias not in prompt.aliases for alias in remember):
        return Invalid(Code.bad_output, "unknown_reference", "remember 只能写给出的事件编号（e 开头）")
    return tuple(dict.fromkeys(used)), tuple(dict.fromkeys(prompt.aliases[a] for a in remember))


def validate(text: str, context: DecisionContext, prompt: RenderedPrompt, limits: CallLimits, now: datetime, *, tools: tuple[ToolSpec, ...] = (),
             tools_left: int = 0, final_only: bool = False) -> Choice | ToolRequest | Invalid:
    data = parse_json(text)
    if isinstance(data, Invalid):
        return data
    if "tools" in data:
        return _tools(data, prompt, tools, tools_left, final_only)
    keys = set(data)
    if keys & FABRICATED_KEYS:
        return Invalid(Code.out_of_bounds, "fabricated_value", "不能自己写钱、收入、时长、时刻或地点，这些只由给出的行动决定")
    if keys - ALLOWED_KEYS:
        return Invalid(Code.bad_output, "schema_violation", "出现了格式里没有的字段")
    choice = data.get("choice")
    if not isinstance(choice, str) or not choice.strip():
        return Invalid(Code.bad_output, "schema_violation", "choice 必须是字符串")
    choice = choice.strip()
    offer = None
    if choice == "continue":
        if not can_continue(context.current_activity, context.as_of):
            return Invalid(Code.unknown_offer, "continue_not_allowed", "现在不能选 continue，请从给出的行动里选")
    else:
        offer_id = prompt.offers.get(choice) or (choice if any(o.offer_id == choice for o in context.action_offers) else None)
        offer = next((o for o in context.action_offers if o.offer_id == offer_id), None)
        if offer is None:
            return Invalid(Code.unknown_offer, "unknown_offer", f"{choice[:12]} 不是给出的行动编号")
        if now >= offer.valid_until:
            return Invalid(Code.stale_context, "offer_expired", "这项行动已经过了有效期", repairable=False)
    intent = data.get("intent")
    if not isinstance(intent, str) or not intent.strip() or len(intent.strip()) > INTENT_MAX or _URL.search(intent):
        return Invalid(Code.bad_output, "schema_violation", f"intent 必须是不超过 {INTENT_MAX} 个字、不带链接的一句话")
    intent = " ".join(intent.split())
    if echoes_private_text(intent, private_texts(context)):
        return Invalid(Code.bad_output, "private_text_echo", "intent 照抄了家人的叮嘱原话，请换成自己的话，也不要提是谁说的")
    review = data.get("review_after_minutes")
    if review is not None and (isinstance(review, bool) or not isinstance(review, int)
                               or not limits.min_review_minutes <= review <= limits.max_review_minutes):
        return Invalid(Code.bad_output, "schema_violation", f"review_after_minutes 必须是 {limits.min_review_minutes} 到 {limits.max_review_minutes} 的整数")
    refs = _references(data, prompt)
    if isinstance(refs, Invalid):
        return refs
    params = data.get("parameters") or {}
    if not isinstance(params, dict):
        return Invalid(Code.bad_output, "schema_violation", "parameters 必须是对象")
    if set(params) & FABRICATED_KEYS:
        return Invalid(Code.out_of_bounds, "fabricated_value", "参数里不能写钱、收入、时长、时刻或地点")
    bounds = dict(offer.bounded_parameters) if offer else {}
    if any(key not in bounds or not _param_ok(bounds[key], value) for key, value in params.items()):
        return Invalid(Code.out_of_bounds, "parameter_out_of_bounds", "参数只能从行动列出的可选值里选")
    return Choice(offer_id=offer.offer_id if offer else None, parameters=dict(params), intent=intent,
                  review_after_seconds=review * 60 if review is not None else None, used_refs=refs[0], remember_refs=refs[1])
