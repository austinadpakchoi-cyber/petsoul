"""把规则侧已经判定可行的出发站选项映射成 ActionOffer（纯函数）。

不调用地图、不读库、不自己判断业务规则：哪些选项此刻可行（醒着、没在外面、一天一份工、远行冷却、驾照……）由集成窗口的规则适配器先筛好；
这里只丢掉选项自己标明不可行（available=false）或钱不够（affordable=false）的，把花费、收入、时长原样带过去，模型不能改。
“留在家里”用 continue 表达（current_activity 为 at_home），也可以由规则另给一个 stay_home 行动。
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta

from ...schemas.runtime_internal import ActionKind, ActionOffer, Versions

VALID_FOR = timedelta(minutes=10)


def action_kind_of(destination_key: str) -> ActionKind:
    if destination_key.startswith("work:"):
        return ActionKind.work
    return ActionKind.local_activity if destination_key.startswith("local:") else ActionKind.travel


def offer_id_for(pet_id: str, destination_key: str, as_of: datetime) -> str:
    return "of-" + hashlib.sha1(f"{pet_id}|{destination_key}|{as_of.isoformat()}".encode("utf-8")).hexdigest()[:12]


def offers_from_options(options: Iterable, *, pet_id: str, as_of: datetime, expected_versions: Versions, valid_for: timedelta = VALID_FOR,
                        income_of: Callable[[str], int] = lambda key: 0) -> tuple[ActionOffer, ...]:
    """options：DestinationOption（或同样字段的对象）。income_of(destination_key) 由集成窗口按工作规则给出工资（例如 web_journey.local.job_of）。"""
    offers: list[ActionOffer] = []
    for option in options:
        if not getattr(option, "available", True) or not getattr(option, "affordable", True):
            continue
        key = option.destination_key
        fee, minutes, income = int(option.fee), int(option.total_minutes), int(income_of(key))
        note = getattr(option, "reference_note", None)
        summary = f"{option.title}：{option.summary}" + (f"（现实参考：{note}）" if note else "")
        offers.append(ActionOffer(offer_id=offer_id_for(pet_id, key, as_of), action_kind=action_kind_of(key), summary=summary, bounded_parameters={},
                                  source_ref=f"destination:{key}", expected_versions=expected_versions, valid_until=as_of + valid_for,
                                  cost_bounds=(fee, fee), income_bounds=(income, income), duration_bounds=(minutes, minutes)))
    return tuple(offers)


def destination_key_of(offer: ActionOffer) -> str | None:
    """集成窗口执行提案时用：offer 来自出发站选项才有 destination_key。"""
    return offer.source_ref.split(":", 1)[1] if offer.source_ref.startswith("destination:") else None
