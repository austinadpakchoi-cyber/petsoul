"""寻味契约：两种模式、两套偏好、分店+菜品证据、四类判断分开、未知与来源诚实。

- Q（餐食品质证据）/ M（口味匹配）/ V（本次价值）/ L（行程便利）/ U（不确定性）分别可缺省；
  缺失不默认高分也不默认 0。内部排序分不包装成满意概率。
- source_rating_count（平台总评价数）与 observed_sample_count（实际取得样本）分开。
- fixture / 虚拟吃饭 / AI 图 / 游戏点赞永不进入现实品质证据池。
- 私人饮食限制 visibility 恒为 private，不进入公开动态或他人可读投影。
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import Field

from .common import DataOrigin, MoneyAmount, WebModel
from .journey import Place
from .transport import PetArrivalContext


class FoodMode(str, Enum):
    pet_virtual_explore = "pet_virtual_explore"
    owner_real_dining = "owner_real_dining"


class PreferenceSubject(str, Enum):
    pet = "pet"
    owner = "owner"


class PreferenceSource(str, Enum):
    explicit = "explicit"
    reception_confirmed = "reception_confirmed"
    feedback_derived = "feedback_derived"
    fixture = "fixture"


class TasteVector(WebModel):
    """-2（很不喜欢）… 2（很喜欢）；null 表示未知，不等于中性。"""

    sweet: int | None = Field(default=None, ge=-2, le=2)
    salty: int | None = Field(default=None, ge=-2, le=2)
    spicy: int | None = Field(default=None, ge=-2, le=2)
    oily: int | None = Field(default=None, ge=-2, le=2)
    aromatic_spice: int | None = Field(default=None, ge=-2, le=2)
    rich_broth: int | None = Field(default=None, ge=-2, le=2)
    crispy: int | None = Field(default=None, ge=-2, le=2)


class DietaryRestrictionKind(str, Enum):
    allergy = "allergy"
    avoid = "avoid"
    religious = "religious"
    other = "other"


class DietaryRestriction(WebModel):
    kind: DietaryRestrictionKind
    label: str
    private: bool = Field(default=True, description="恒为私密；公开/社交接口不得输出")


class FoodPreference(WebModel):
    preference_id: str
    subject: PreferenceSubject
    pet_id: str
    version: int
    label: str = Field(description="主人可读的偏好名，例如“清淡”“浓郁”")
    taste: TasteVector
    budget: MoneyAmount | None = None
    max_wait_minutes: int | None = None
    party_size: int | None = None
    restrictions: list[DietaryRestriction] = Field(default_factory=list)
    source: PreferenceSource
    updated_at: datetime


class EvidenceSourceKind(str, Enum):
    map_poi = "map_poi"
    merchant_menu = "merchant_menu"
    licensed_review = "licensed_review"
    owner_feedback = "owner_feedback"
    partner_note = "partner_note"
    fixture = "fixture"


class SourceRating(WebModel):
    provider: str
    rating: float | None = None
    source_rating_count: int | None = Field(default=None, description="平台总评价数")
    observed_sample_count: int = Field(default=0, description="本系统实际取得并分析的样本数")
    fetched_at: datetime | None = None


class Branch(WebModel):
    """branch_id 含来源命名空间（amap:/google:/fixture:）；总店证据不自动转移给分店。"""

    branch_id: str
    name: str
    brand: str | None = None
    place: Place | None = None
    ratings: list[SourceRating] = Field(default_factory=list)


class Dish(WebModel):
    dish_id: str
    branch_id: str
    name: str
    price: MoneyAmount | None = None
    flavor_traits: list[str] = Field(default_factory=list)


class EvidenceCitation(WebModel):
    evidence_id: str
    source_kind: EvidenceSourceKind
    source_label: str
    aspect: str
    observation: str
    observed_at: datetime | None = None
    sample_count: int = 0


class JudgementScores(WebModel):
    quality: float | None = None
    match: float | None = None
    value: float | None = None
    logistics: float | None = None
    uncertainty: float | None = None


class EligibilityStatus(str, Enum):
    eligible = "eligible"
    needs_verification = "needs_verification"
    excluded = "excluded"


class RecommendationGroup(str, Enum):
    primary = "primary"
    alternative = "alternative"
    explore = "explore"
    needs_verification = "needs_verification"


class RecommendationFreshness(str, Enum):
    fresh = "fresh"
    needs_recheck = "needs_recheck"
    expired = "expired"


class DishSuggestion(WebModel):
    dish: Dish
    why: str
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class FoodDataStatus(str, Enum):
    fixture = "fixture"
    live_verified = "live_verified"
    live_partial = "live_partial"


class RecommendationProvenance(WebModel):
    generated_at: datetime
    fact_version: str
    preference_version: int
    rule_version: str
    data_status: FoodDataStatus
    coverage_note: str


class OwnerDiningContext(WebModel):
    """主人现实用餐：使用主人自己的日期/位置/时间，不套宠物行程。"""

    plan_date: date
    meal_time_local: str = Field(pattern=r"^\d{2}:\d{2}$")
    timezone: str
    city: str
    area: str | None = None


class FoodRecommendation(WebModel):
    recommendation_id: str
    mode: FoodMode
    branch: Branch
    dishes: list[DishSuggestion] = Field(default_factory=list)
    scores: JudgementScores
    eligibility: EligibilityStatus
    group: RecommendationGroup
    rank: int | None = None
    reasons: list[str] = Field(default_factory=list)
    not_suitable_when: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    provenance: RecommendationProvenance
    freshness: RecommendationFreshness
    itinerary_version: int | None = Field(default=None, description="pet 模式绑定的行程版本；变化后 needs_recheck")
    data_origin: DataOrigin


class FoodRecommendationRequest(WebModel):
    mode: FoodMode
    pet_id: str
    preference_id: str | None = None
    pet_context: PetArrivalContext | None = None
    owner_context: OwnerDiningContext | None = None
    scene: str | None = Field(default=None, description="确定性场景配置键，例如 special_trip / quick_bite")
    max_results: int = Field(default=3, ge=1, le=5)


class FoodRecommendationList(WebModel):
    mode: FoodMode
    preference: FoodPreference
    items: list[FoodRecommendation] = Field(default_factory=list)
    shortfall_note: str | None = Field(default=None, description="数量不足时如实说明，不强造三个")
    data_origin: DataOrigin


class FeedbackVerdict(str, Enum):
    liked = "liked"
    neutral = "neutral"
    disliked = "disliked"


class FeedbackVerification(str, Enum):
    self_reported = "self_reported"
    verified = "verified"


class FoodFeedback(WebModel):
    """主人实际用餐反馈；不同于虚拟到访 visit_id，需 Idempotency-Key。"""

    feedback_id: str | None = None
    recommendation_id: str
    dish_ids: list[str] = Field(default_factory=list)
    verdict: FeedbackVerdict
    reasons: list[str] = Field(default_factory=list)
    note: str | None = Field(default=None, max_length=500)
    dined_on: date
    verification: FeedbackVerification = FeedbackVerification.self_reported


__all__ = [
    "FoodMode",
    "PreferenceSubject",
    "PreferenceSource",
    "TasteVector",
    "DietaryRestrictionKind",
    "DietaryRestriction",
    "FoodPreference",
    "EvidenceSourceKind",
    "SourceRating",
    "Branch",
    "Dish",
    "EvidenceCitation",
    "JudgementScores",
    "EligibilityStatus",
    "RecommendationGroup",
    "RecommendationFreshness",
    "DishSuggestion",
    "FoodDataStatus",
    "RecommendationProvenance",
    "OwnerDiningContext",
    "FoodRecommendation",
    "FoodRecommendationRequest",
    "FoodRecommendationList",
    "FeedbackVerdict",
    "FeedbackVerification",
    "FoodFeedback",
]
