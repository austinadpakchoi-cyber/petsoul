"""寻味服务：两套偏好、两种模式、推荐快照与反馈。

- 宠物模式只用宠物的门到门到达上下文（由旅程服务提供）；主人模式只用主人自己的日期/时间/城市；
- 推荐快照绑定行程版本：读取详情时按当前行程重算 freshness（变化即 needs_recheck）；
- 反馈是主人自报（self_reported），只修正主人口味偏好的版本，不回流为任何现实品质证据；
- 私人饮食限制只在本人 GET 偏好时返回，不出现在推荐卡或任何公开投影中。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Callable

from ..schemas.web.common import DataOrigin, MoneyAmount
from ..schemas.web.food import (
    FeedbackVerification,
    Branch,
    Dish,
    DishSuggestion,
    EligibilityStatus,
    EvidenceCitation,
    EvidenceSourceKind,
    FoodDataStatus,
    FoodFeedback,
    FoodMode,
    FoodPreference,
    FoodRecommendation,
    FoodRecommendationList,
    FoodRecommendationRequest,
    JudgementScores,
    PreferenceSource,
    PreferenceSubject,
    RecommendationFreshness,
    RecommendationGroup,
    RecommendationProvenance,
    TasteVector,
)
from ..schemas.web.journey import Place, PlaceProvider
from ..schemas.web.transport import PetArrivalContext
from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from .context import FoodContextError, recommendation_freshness, validate_request_context
from .dataset import AREAS, CITY_AREAS
from .engine import RULE_VERSION, Scored, evaluate, local_of, meal_time_local, rank, stay_minutes_between

FACT_VERSION = "demo-dataset-2026-09-22"
FEEDBACK_ADJUST = {"too_salty": ("salty", -1), "too_sweet": ("sweet", -1), "too_spicy": ("spicy", -1), "too_oily": ("oily", -1), "too_bland": ("salty", 1)}


class FoodError(Exception):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


def default_preference(pet_id: str, subject: PreferenceSubject, now: datetime) -> FoodPreference:
    return FoodPreference(preference_id=f"pref-{subject.value}-{pet_id}", subject=subject, pet_id=pet_id, version=0, label="还没设置", taste=TasteVector(),
                          budget=MoneyAmount(amount_minor=8000, currency="HKD") if subject is PreferenceSubject.owner else None,
                          source=PreferenceSource.explicit, updated_at=now)


class WebFoodService:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage
        self.arrival_context_of: Callable[[str, str], tuple[PetArrivalContext, str] | None] = lambda user_id, pet_id: None
        self.current_itinerary_of: Callable[[str], int | None] = lambda journey_id: None

    # ---- 偏好 ----
    def preference(self, user_id: str, pet_id: str, subject: PreferenceSubject) -> FoodPreference:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT preference_json FROM web_food_preferences WHERE user_id = ? AND pet_id = ? AND subject = ?", (user_id, pet_id, subject.value)).fetchone()
        return FoodPreference.model_validate_json(row["preference_json"]) if row else default_preference(pet_id, subject, utcnow())

    def put_preference(self, user_id: str, pet_id: str, subject: PreferenceSubject, incoming: FoodPreference, now: datetime | None = None) -> FoodPreference:
        now = now or utcnow()
        current = self.preference(user_id, pet_id, subject)
        restrictions = incoming.restrictions if subject is PreferenceSubject.owner else []
        updated = incoming.model_copy(update={"preference_id": current.preference_id, "subject": subject, "pet_id": pet_id, "version": current.version + 1,
                                              "restrictions": [r.model_copy(update={"private": True}) for r in restrictions], "updated_at": now,
                                              "source": PreferenceSource.explicit})
        with self.storage.connect() as conn:
            conn.execute("INSERT INTO web_food_preferences (user_id, pet_id, subject, preference_json, version, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
                         "ON CONFLICT(user_id, pet_id, subject) DO UPDATE SET preference_json = excluded.preference_json, version = excluded.version, updated_at = excluded.updated_at",
                         (user_id, pet_id, subject.value, updated.model_dump_json(), updated.version, iso(now)))
        return updated

    # ---- 推荐 ----
    def recommend(self, user_id: str, request: FoodRecommendationRequest, now: datetime | None = None) -> FoodRecommendationList:
        now = now or utcnow()
        pet_mode = request.mode is FoodMode.pet_virtual_explore
        area_key = None
        journey_id = None
        if pet_mode:
            server_ctx = self.arrival_context_of(user_id, request.pet_id)
            if server_ctx is None:
                raise FoodError("no_journey", "TA 现在没有在旅途中，没有可用的到达时间。")
            context, area_key = server_ctx
            # 以服务端行程为准：客户端传入的上下文只能与之完全一致，防止伪造到达时间。
            request = request.model_copy(update={"pet_context": context})
            journey_id = context.journey_id
        try:
            validate_request_context(request)
        except FoodContextError as exc:
            raise FoodError("bad_context", str(exc)) from exc
        subject = PreferenceSubject.pet if pet_mode else PreferenceSubject.owner
        preference = self.preference(user_id, request.pet_id, subject)
        if pet_mode:
            ctx = request.pet_context
            tz, branches = AREAS[area_key]
            meal_local = local_of(ctx.stay_window_start_utc, tz)
            stay = stay_minutes_between(ctx.stay_window_start_utc, ctx.stay_window_end_utc)
            budget = None
        else:
            owner = request.owner_context
            area_key = CITY_AREAS.get(owner.city)
            if area_key is None:
                return FoodRecommendationList(mode=request.mode, preference=preference, items=[], shortfall_note=f"{owner.city}还没有可用的寻味资料。", data_origin=DataOrigin.live)
            tz, branches = AREAS[area_key]
            meal_local = meal_time_local(owner.timezone, owner.plan_date, owner.meal_time_local)
            stay = None
            budget = preference.budget.amount_minor // 100 if preference.budget and preference.budget.currency == "HKD" else None
        restrictions = [r.label for r in preference.restrictions]
        scored: list[Scored] = []
        for branch in branches:
            for dish in branch.dishes:
                scored.append(evaluate(branch, dish, taste=preference.taste, meal_local=meal_local, budget=budget, restrictions=restrictions, stay_minutes=stay, pet_mode=pet_mode))
        ranked = rank(scored)
        chosen: list[Scored] = []
        seen_branches: set[str] = set()
        for item in ranked:
            if item.branch.branch_id in seen_branches:
                continue
            seen_branches.add(item.branch.branch_id)
            chosen.append(item)
            if len(chosen) >= request.max_results:
                break
        batch_id = f"fb-{uuid.uuid4().hex[:10]}"
        coverage = f"演示资料集：本区域 {len(branches)} 家示例分店，每家 1–2 道示例菜；不是全城结果，也不是真实口碑。"
        items = [self._to_dto(item, index, request.mode, preference, coverage, request, now) for index, item in enumerate(chosen)]
        with self.storage.connect() as conn:
            for rec in items:
                conn.execute("INSERT INTO web_food_recommendations (recommendation_id, user_id, pet_id, batch_id, mode, journey_id, itinerary_version, payload_json, created_at) "
                             "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (rec.recommendation_id, user_id, request.pet_id, batch_id, request.mode.value, journey_id,
                                                                    rec.itinerary_version, rec.model_dump_json(), iso(now)))
        excluded = sum(1 for s in scored if s.eligibility == "excluded")
        shortfall = None if len(items) >= request.max_results else f"只有 {len(items)} 家符合条件（另有 {excluded} 个候选被营业/预算/饮食限制排除），不硬凑。"
        return FoodRecommendationList(mode=request.mode, preference=preference, items=items, shortfall_note=shortfall, data_origin=DataOrigin.live)

    def _to_dto(self, item: Scored, index: int, mode: FoodMode, preference: FoodPreference, coverage: str, request: FoodRecommendationRequest, now: datetime) -> FoodRecommendation:
        dish = item.dish
        if item.eligibility == "needs_verification":
            group = RecommendationGroup.needs_verification
        elif dish is None or not dish.evidence:
            group = RecommendationGroup.explore
        else:
            group = RecommendationGroup.primary if index == 0 else RecommendationGroup.alternative
        branch = item.branch
        place = Place(provider=PlaceProvider.fixture, place_id=branch.branch_id, name=branch.name, address=None, lat=branch.lat, lng=branch.lng,
                      coord_system="wgs84", category="餐厅", source_updated_at=None, attribution="演示资料：不对应真实商家", data_origin=DataOrigin.fixture)
        suggestions = []
        if dish is not None:
            suggestions.append(DishSuggestion(
                dish=Dish(dish_id=dish.dish_id, branch_id=branch.branch_id, name=dish.name,
                          price=MoneyAmount(amount_minor=dish.price_hkd * 100, currency="HKD") if dish.price_hkd is not None else None, flavor_traits=list(dish.trait_labels)),
                why="、".join(dish.trait_labels) or "资料不足",
                evidence=[EvidenceCitation(evidence_id=f"{dish.dish_id}:ev{i}", source_kind=EvidenceSourceKind.fixture, source_label="演示资料", aspect=a, observation=o,
                                           observed_at=None, sample_count=0) for i, (a, o) in enumerate(dish.evidence)],
            ))
        return FoodRecommendation(
            recommendation_id=f"rec-{uuid.uuid4().hex[:12]}", mode=mode, branch=Branch(branch_id=branch.branch_id, name=branch.name, brand=branch.brand, place=place, ratings=[]),
            dishes=suggestions, scores=JudgementScores(quality=None, match=item.match, value=item.value, logistics=item.logistics, uncertainty=item.uncertainty),
            eligibility=EligibilityStatus(item.eligibility), group=group, rank=index + 1 if group in (RecommendationGroup.primary, RecommendationGroup.alternative) else None,
            reasons=item.reasons, not_suitable_when=item.not_suitable, unknowns=item.unknowns,
            provenance=RecommendationProvenance(generated_at=now, fact_version=FACT_VERSION, preference_version=preference.version, rule_version=RULE_VERSION,
                                                data_status=FoodDataStatus.fixture, coverage_note=coverage),
            freshness=RecommendationFreshness.fresh, itinerary_version=request.pet_context.itinerary_version if request.pet_context else None, data_origin=DataOrigin.live,
        )

    def recommendation(self, user_id: str, recommendation_id: str) -> tuple[FoodRecommendation, str | None]:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_food_recommendations WHERE recommendation_id = ? AND user_id = ?", (recommendation_id, user_id)).fetchone()
        if row is None:
            raise FoodError("not_found", "没有找到这条推荐。")
        rec = FoodRecommendation.model_validate_json(row["payload_json"])
        if rec.mode is FoodMode.pet_virtual_explore and row["journey_id"]:
            current = self.current_itinerary_of(row["journey_id"])
            ctx = None if current is None else PetArrivalContext(journey_id=row["journey_id"], itinerary_version=current, leg_id="-", city="-",
                                                                 destination_timezone="UTC", feasible_arrival_utc=rec.provenance.generated_at,
                                                                 stay_window_start_utc=rec.provenance.generated_at, stay_window_end_utc=rec.provenance.generated_at)
            rec = rec.model_copy(update={"freshness": recommendation_freshness(rec, ctx)})
        return rec, row["journey_id"]

    def feedback(self, user_id: str, feedback: FoodFeedback, now: datetime | None = None) -> FoodFeedback:
        now = now or utcnow()
        rec, _ = self.recommendation(user_id, feedback.recommendation_id)
        if rec.mode is not FoodMode.owner_real_dining:
            raise FoodError("not_allowed", "宠物的虚拟探索不能提交现实用餐反馈。")
        stored = feedback.model_copy(update={"feedback_id": f"ffb-{uuid.uuid4().hex[:12]}", "verification": FeedbackVerification.self_reported})
        with self.storage.connect() as conn:
            conn.execute("INSERT INTO web_food_feedback (feedback_id, user_id, recommendation_id, payload_json, verification, created_at) VALUES (?, ?, ?, ?, 'self_reported', ?)",
                         (stored.feedback_id, user_id, feedback.recommendation_id, stored.model_dump_json(), iso(now)))
            pet_row = conn.execute("SELECT pet_id FROM web_food_recommendations WHERE recommendation_id = ?", (feedback.recommendation_id,)).fetchone()
        adjustments = [FEEDBACK_ADJUST[r] for r in feedback.reasons if r in FEEDBACK_ADJUST]
        if adjustments and pet_row:
            pref = self.preference(user_id, pet_row["pet_id"], PreferenceSubject.owner)
            taste = pref.taste.model_dump()
            for trait, delta in adjustments:
                taste[trait] = max(-2, min(2, (taste.get(trait) or 0) + delta))
            self.put_preference(user_id, pet_row["pet_id"], PreferenceSubject.owner, pref.model_copy(update={"taste": TasteVector(**taste)}), now)
        return stored
