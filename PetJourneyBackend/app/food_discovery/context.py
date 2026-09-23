"""寻味的上下文与证据边界（纯函数，R0 已测试；评分/排序算法留给寻味模块实现）。"""

from __future__ import annotations

from collections.abc import Iterable

from ..schemas.web.food import (
    EvidenceCitation,
    EvidenceSourceKind,
    FoodMode,
    FoodPreference,
    FoodRecommendation,
    FoodRecommendationRequest,
    RecommendationFreshness,
)
from ..schemas.web.transport import PetArrivalContext

# 只有这些来源可以进入现实餐食品质证据池；fixture/虚拟吃饭/AI 图/游戏点赞永不进入。
REAL_QUALITY_SOURCES = frozenset(
    {
        EvidenceSourceKind.merchant_menu,
        EvidenceSourceKind.licensed_review,
        EvidenceSourceKind.owner_feedback,
        EvidenceSourceKind.partner_note,
    }
)


class FoodContextError(ValueError):
    pass


def validate_request_context(request: FoodRecommendationRequest) -> None:
    """宠物模式只用宠物门到门行程；主人模式只用主人自己的日期/位置，不能互相套用。"""
    if request.mode is FoodMode.pet_virtual_explore:
        if request.pet_context is None:
            raise FoodContextError("pet_virtual_explore 需要 pet_context（可行到达与停留窗口）")
        if request.owner_context is not None:
            raise FoodContextError("pet_virtual_explore 不接受主人的现实用餐计划")
        ctx = request.pet_context
        if not (ctx.feasible_arrival_utc <= ctx.stay_window_start_utc < ctx.stay_window_end_utc):
            raise FoodContextError("停留窗口必须晚于可行到达且非空")
    else:
        if request.owner_context is None:
            raise FoodContextError("owner_real_dining 需要主人自己的 owner_context")
        if request.pet_context is not None:
            raise FoodContextError("owner_real_dining 不能套用宠物当前行程")


def recommendation_freshness(
    recommendation: FoodRecommendation, current: PetArrivalContext | None
) -> RecommendationFreshness:
    """行程版本变化（延误/改线）→ 旧推荐待复核；不能为了餐厅压短交通。"""
    if recommendation.mode is FoodMode.owner_real_dining:
        return recommendation.freshness
    if current is None or recommendation.itinerary_version is None:
        return RecommendationFreshness.needs_recheck
    if recommendation.itinerary_version != current.itinerary_version:
        return RecommendationFreshness.needs_recheck
    return recommendation.freshness


def real_quality_evidence(citations: Iterable[EvidenceCitation]) -> list[EvidenceCitation]:
    return [item for item in citations if item.source_kind in REAL_QUALITY_SOURCES]


def public_preference_view(preference: FoodPreference) -> dict:
    """任何公开/社交投影只能拿到这里的字段：私人饮食限制、预算一律剔除。"""
    return {"subject": preference.subject.value, "label": preference.label}
