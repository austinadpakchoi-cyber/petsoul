"""寻味确定性筛选与排序（纯函数，可测试）。

流水线：召回（同区域候选）→ 硬条件（确认关闭/超硬预算/已知饮食冲突 → excluded；营业/价格未知 → needs_verification，
不当作满足）→ 分别计算 Q/M/V/L/U → **对合格候选真正排序**（同分按 branch_id、dish_id 稳定）→ 分组截取。

演示资料没有现实品质证据：Q 恒为 None，不参与排序也不补 0；排序配置 RULE_VERSION 是待校准的临时规则，
不是经过验证的最优公式，也不输出“满意概率”。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..schemas.web.food import TasteVector
from .dataset import TRAITS, DemoBranch, DemoDish

RULE_VERSION = "food-rules-r1-demo"
WEIGHTS = {"match": 0.5, "value": 0.25, "logistics": 0.25, "uncertainty": 0.2}


@dataclass
class Scored:
    branch: DemoBranch
    dish: DemoDish | None
    eligibility: str  # eligible / needs_verification / excluded
    reasons: list[str]
    not_suitable: list[str]
    unknowns: list[str]
    match: float | None
    value: float | None
    logistics: float | None
    uncertainty: float
    rank_score: float | None = None


def taste_match(taste: TasteVector, dish: DemoDish) -> float | None:
    """口味匹配 M ∈ [0,1]：只在双方都有取值的维度上比较；没有可比维度返回 None（未知≠中性）。"""
    pairs = [(getattr(taste, t), dish.traits.get(t)) for t in TRAITS]
    pairs = [(p, d) for p, d in pairs if p is not None and d is not None]
    if not pairs:
        return None
    distance = math.sqrt(sum((p - d) ** 2 for p, d in pairs) / len(pairs))
    return round(max(0.0, 1 - distance / 4), 3)


def open_at(branch: DemoBranch, local: datetime) -> bool | None:
    if branch.open_hours is None:
        return None
    start, end = branch.open_hours
    hour = local.hour + local.minute / 60
    if end > 24:
        return hour >= start or hour < end - 24
    return start <= hour < end


def evaluate(branch: DemoBranch, dish: DemoDish | None, *, taste: TasteVector, meal_local: datetime, budget: int | None,
             restrictions: list[str], stay_minutes: int | None, pet_mode: bool) -> Scored:
    reasons: list[str] = []
    not_suitable: list[str] = []
    unknowns: list[str] = []
    if branch.closed_permanently:
        return Scored(branch, dish, "excluded", [], ["资料显示已停业"], [], None, None, None, 1.0)
    conflicts = [r for r in restrictions if dish and any(r in ing or ing in r for ing in dish.ingredients)]
    if conflicts:
        return Scored(branch, dish, "excluded", [], [f"含你设置要避开的成分：{'、'.join(conflicts)}"], [], None, None, None, 1.0)
    eligibility = "eligible"
    opened = open_at(branch, meal_local)
    if opened is False:
        return Scored(branch, dish, "excluded", [], ["那个时间不营业"], [], None, None, None, 1.0)
    if opened is None:
        eligibility = "needs_verification"
        unknowns.append("营业时间未核实")
    price = dish.price_hkd if dish else None
    if price is None:
        unknowns.append("价格未知")
    elif budget is not None and price > budget:
        return Scored(branch, dish, "excluded", [], [f"超出预算（{price} > {budget}）"], [], None, None, None, 1.0)
    match = taste_match(taste, dish) if dish else None
    if match is not None:
        if match >= 0.75:
            reasons.append("和偏好很合拍：" + "、".join(dish.trait_labels) if dish else "口味合拍")
        elif match < 0.45:
            not_suitable.append("口味和偏好相差较大：" + "、".join(dish.trait_labels) if dish else "口味差异大")
    value = None if price is None or budget in (None, 0) else round(max(0.0, 1 - price / budget) * 0.6 + 0.4, 3)
    logistics = None
    if stay_minutes is not None:
        logistics = 1.0 if stay_minutes >= 40 else 0.6
        if stay_minutes < 40:
            not_suitable.append("停留时间偏短，吃得会比较赶")
    if dish is None or not dish.evidence:
        unknowns.append("没有这道菜的评价证据")
    unknowns.append("资料为演示数据，现实品质未核实")
    uncertainty = 0.85 if (dish is None or not dish.evidence) else 0.6
    if pet_mode:
        reasons.append("在 TA 可停留的时间内能到店（按行程时间）")
    return Scored(branch, dish, eligibility, reasons, not_suitable, unknowns, match, value, logistics, uncertainty)


def rank(candidates: list[Scored]) -> list[Scored]:
    """对合格候选按计算结果真正重排；缺失项不补分（不参与加权）。同分稳定：branch_id → dish_id。"""
    for c in candidates:
        if c.eligibility == "excluded":
            c.rank_score = None
            continue
        parts = [(WEIGHTS[k], v) for k, v in (("match", c.match), ("value", c.value), ("logistics", c.logistics)) if v is not None]
        total_weight = sum(w for w, _ in parts)
        base = sum(w * v for w, v in parts) / total_weight if total_weight else 0.0
        c.rank_score = round(base - WEIGHTS["uncertainty"] * c.uncertainty, 4)
    eligible = [c for c in candidates if c.eligibility != "excluded"]
    eligible.sort(key=lambda c: (-(c.rank_score or 0.0), c.branch.branch_id, c.dish.dish_id if c.dish else ""))
    return eligible


def meal_time_local(tz: str, date_value, hhmm: str) -> datetime:
    hour, minute = (int(x) for x in hhmm.split(":"))
    return datetime.combine(date_value, time(hour, minute), tzinfo=ZoneInfo(tz))


def local_of(instant: datetime, tz: str) -> datetime:
    return instant.astimezone(ZoneInfo(tz))


def stay_minutes_between(start: datetime, end: datetime) -> int:
    return int((end - start) / timedelta(minutes=1))
