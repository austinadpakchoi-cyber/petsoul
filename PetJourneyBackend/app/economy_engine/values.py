"""纪念品估值辅助（架构审计 P1-2 包化）。"""

from __future__ import annotations

from ..schemas import ItemValue


def item_value(
    *,
    market_value: int,
    emotional_value: int,
    honor_value: int,
    base: int,
    rarity_multiplier: float,
    source_multiplier: float,
    condition_multiplier: float,
    story_bonus: float,
):
    from ..schemas import ItemValue

    return ItemValue(
        market_value=market_value,
        emotional_value=emotional_value,
        honor_value=honor_value,
        value_breakdown={
            "base": base,
            "rarity_multiplier": rarity_multiplier,
            "source_multiplier": source_multiplier,
            "condition_multiplier": condition_multiplier,
            "story_bonus": story_bonus,
            "final_market_value": market_value,
        },
    )
