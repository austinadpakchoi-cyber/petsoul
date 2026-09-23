"""把决策上下文写成给模型的消息。模型看到的编号都是本次临时编号（o1、e2……），不暴露内部 ID 与家人身份。

- 资料按来源分栏：家人确认的 DNA / 家人允许用于安排生活的叮嘱 / 此刻与最近真实发生的事 / 家人的建议与之前的打算；
  现实参考标“现实参考”，之前的打算标“是想法，不是事实”；
- 只能从“现在能做的事”里选，或选 continue；钱、收入、时长都来自规则给出的行动，模型不能自己写数字；
- 输出限定为一个 JSON 对象（与 json_mode 配合）；格式修复与工具续问都另起一条消息。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from datetime import datetime, timedelta

from ...schemas.runtime_internal import ActionOffer, ContextFact, DecisionContext
from .context import CONTINUE_LABEL, LIFE_DNA_FIELDS, can_continue
from .ports import ToolSpec

PROMPT_VERSION = "life-plan-2026-09-23.1"
SPECIES_TEXT = {"cat": "猫", "dog": "狗", "rabbit": "兔子", "hamster": "仓鼠", "bird": "小鸟", "parrot": "鹦鹉", "other": "小动物"}
DNA_LABELS = {"personality": "性格", "habits": "小习惯", "hobbies": "爱好", "favorite_places": "喜欢的地方", "favorite_foods": "爱吃的", "fears": "害怕的"}
DOING = {"at_home": "在家", "local_activity": "在家附近活动", "work": "在打工", "travel": "在旅途中", "visit": "在店里", "exam": "在考试"}
SOURCE_TAG = {"external_reference": "（现实参考）", "model_interpretation": "（之前的想法，不是已经发生的事）", "creative_fiction": "（角色设定）"}
TOOL_RESULT_MAX = 300


@dataclass(frozen=True)
class RenderedPrompt:
    messages: tuple[dict[str, str], ...]
    aliases: dict[str, str]  # 临时编号 → 资料 ref
    offers: dict[str, str]  # 临时编号 → offer_id
    tools_offered: bool
    version: str = PROMPT_VERSION


def _span(delta: timedelta) -> str:
    minutes = int(abs(delta.total_seconds()) // 60)
    if minutes < 60:
        return f"{max(1, minutes)} 分钟"
    return f"{minutes // 60} 小时" if minutes < 48 * 60 else f"{minutes // 1440} 天"


def _fact_lines(prefix: str, facts: tuple[ContextFact, ...], aliases: dict[str, str], as_of: datetime) -> list[str]:
    """时间写成相对 as_of 的“多久以前 / 多久之内”，不依赖猜测的时区。"""
    lines = []
    for index, fact in enumerate(facts, start=1):
        alias = f"{prefix}{index}"
        aliases[alias] = fact.ref
        when = f"[{_span(as_of - fact.observed_at)}前] " if fact.observed_at and fact.observed_at < as_of else ""
        due = f"（{_span(fact.deadline_at - as_of)}之内）" if fact.deadline_at and fact.deadline_at > as_of else ""
        lines.append(f"- {alias} {when}{fact.text}{due}{SOURCE_TAG.get(fact.source, '')}")
    return lines


def _offer_line(alias: str, offer: ActionOffer) -> list[str]:
    facts = []
    if offer.cost_bounds[1]:
        facts.append(f"花费 {offer.cost_bounds[0]} 星币" if offer.cost_bounds[0] == offer.cost_bounds[1] else f"花费 {offer.cost_bounds[0]}–{offer.cost_bounds[1]} 星币")
    if offer.income_bounds[1]:
        facts.append(f"收入 {offer.income_bounds[0]} 星币" if offer.income_bounds[0] == offer.income_bounds[1] else f"收入 {offer.income_bounds[0]}–{offer.income_bounds[1]} 星币")
    if offer.duration_bounds[1]:
        facts.append(f"约 {offer.duration_bounds[0]} 分钟" if offer.duration_bounds[0] == offer.duration_bounds[1] else f"约 {offer.duration_bounds[0]}–{offer.duration_bounds[1]} 分钟")
    lines = [f"- {alias} {offer.summary}" + (f"（{'，'.join(facts)}）" if facts else "")]
    for name, bound in offer.bounded_parameters.items():
        allowed = " / ".join(bound.choices) if bound.choices else f"{bound.minimum} 到 {bound.maximum} 的整数"
        lines.append(f"  可选参数 {name}：{allowed}")
    return lines


def render(context: DecisionContext, *, tools: tuple[ToolSpec, ...] = (), tools_allowed: int = 0) -> RenderedPrompt:
    dna = context.permitted_dna
    name = str(dna.get("name") or "TA")
    species = SPECIES_TEXT.get(str(dna.get("species") or "other"), "小动物")
    activity = context.current_activity
    aliases: dict[str, str] = {}
    offers: dict[str, str] = {}
    continuing = can_continue(activity, context.as_of)
    body: list[str] = [f"此刻：{DOING.get(activity.kind, '状态不明') if activity else '状态不明'}。"]
    confirmed = context.versions.dna_version > 0
    dna_lines = []
    for index, (field, values) in enumerate(((f, dna[f]) for f in LIFE_DNA_FIELDS if f in dna), start=1):
        alias = f"d{index}"
        aliases[alias] = f"dna:{field}@{context.versions.dna_version}"
        text = "、".join(values) if isinstance(values, tuple) else str(values)
        dna_lines.append(f"- {alias} {DNA_LABELS[field]}：{text}")
    if dna_lines:
        body += [f"{name}的 DNA（{'家人已确认' if confirmed else '家人还没确认，只作参考'}）："] + dna_lines
    for title, prefix, facts in (("家人允许用于安排生活的叮嘱（只作参考；不要照抄，不要提是谁说的）：", "n", context.memory_refs),
                                 ("此刻与最近真实发生的事：", "e", context.observations),
                                 ("家人的建议、答应过的事与之前的打算：", "c", context.commitments)):
        if facts:
            body.append(title)
            body += _fact_lines(prefix, facts, aliases, context.as_of)
    body.append("现在能做的事：")
    for index, offer in enumerate(context.action_offers, start=1):
        alias = f"o{index}"
        offers[alias] = offer.offer_id
        body += _offer_line(alias, offer)
    if continuing:
        body.append(f"- continue：{CONTINUE_LABEL[activity.kind]}")
    choices = "行动编号" + ("或 \"continue\"" if continuing else "")
    rules = [
        f"你在替「{name}」（一只{species}）安排接下来做什么。{name}生活在 PetSoul 动物星球，是一只真实的动物，有自己的生活节奏，不会受伤；"
        f"家人只提建议，最后由{name}自己决定。",
        "规则：",
        f"1. 只能从“现在能做的事”里选一项，choice 写{choices}。不能编造别的活动、地点、价格、收入、时长，也不要在输出里写这些数字。",
        "2. 依据只用给出的资料：DNA 是家人确认的样子；标着“之前的想法”的不是已经发生的事。",
        "3. 家人的叮嘱只作参考：intent 里不要引用原话，也不要说是谁说的。",
        "4. 钱不够的事已经不在列表里；家人的建议可以采纳，也可以不采纳。",
        "5. 只输出一个 JSON 对象，不要任何其他文字。",
        '格式：{"choice": "o1", "intent": "……", "review_after_minutes": 60, "uses": ["e1", "d2"], "remember": ["e1"]}',
        "- choice：必填；",
        "- intent：必填，第一人称一句话说明打算，不超过 40 个字；",
        "- review_after_minutes：可选，15 到 720 之间的整数，表示多久以后再想想；",
        "- uses：可选，做这个决定用到的资料编号；",
        "- remember：可选，最多 3 个值得记住的事件编号（只能是 e 开头）；",
        "- parameters：只有行动写了可选参数时才填，取值只能是列出的那些。",
    ]
    tools_offered = tools_allowed > 0 and bool(tools)
    if tools_offered:
        rules.append(f'如果需要先查更多资料，可以只输出 {{"tools": [{{"name": "工具名", "arg": "编号"}}]}}（最多 {tools_allowed} 个），'
                     "查到后会再问你一次，那一次必须给出决定。可用工具：")
        rules += [f"- {tool.name}（arg 为{'行动编号' if tool.arg == 'offer' else '资料编号'}）：{tool.description}" for tool in tools]
    messages = ({"role": "system", "content": "\n".join(rules)}, {"role": "user", "content": "\n".join(body)})
    return RenderedPrompt(messages=messages, aliases=aliases, offers=offers, tools_offered=tools_offered)


def repair_messages(bad_output: str, problem: str, prompt: RenderedPrompt, continuing: bool) -> list[dict[str, str]]:
    ids = "、".join(list(prompt.offers) + (["continue"] if continuing else []))
    return [{"role": "assistant", "content": bad_output[:500]},
            {"role": "user", "content": f"上面的输出不符合要求：{problem}。请只输出一个符合格式的 JSON 对象；choice 只能是 {ids} 之一。"}]


def tool_messages(request_text: str, results: list[tuple[str, str, str]]) -> list[dict[str, str]]:
    lines = [f"- {name}({arg})：{' '.join(result.split())[:TOOL_RESULT_MAX]}" for name, arg, result in results]
    return [{"role": "assistant", "content": request_text[:500]},
            {"role": "user", "content": "查询结果：\n" + "\n".join(lines) + "\n现在请给出决定：只输出一个 JSON 对象，不能再调用工具。"}]


def context_digest(context: DecisionContext) -> str:
    """上下文摘要（审计用）：同样的资料与版本得到同样的摘要；不存原文也能核对“当时依据的是哪一版”。"""
    activity = context.current_activity
    payload = {
        "op": context.operation_id, "pet": context.pet_id, "purpose": context.purpose,
        "versions": {f.name: getattr(context.versions, f.name) for f in fields(context.versions)},
        "dna": {k: list(v) if isinstance(v, tuple) else v for k, v in context.permitted_dna.items()},
        "facts": [[f.ref, f.source, f.text] for f in context.memory_refs + context.observations + context.commitments],
        "offers": [[o.offer_id, o.source_ref, list(o.cost_bounds), list(o.income_bounds), list(o.duration_bounds), o.valid_until.isoformat()]
                   for o in context.action_offers],
        "activity": [activity.kind, activity.ref] if activity else None,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
