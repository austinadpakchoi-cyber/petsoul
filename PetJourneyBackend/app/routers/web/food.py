"""寻味：两套偏好（宠物/主人）、两种模式推荐、推荐详情（按当前行程重算新鲜度）、主人现实用餐反馈。

0.4.0：推荐目前只有演示小样本（没有获准分析的真实菜单/评论资料），所以只在演示环境提供；正式环境明确返回“能力不可用”，不把演示资料混进真实体验。"""

from __future__ import annotations

from fastapi import Depends, Request

from ...food_discovery.store import FoodError
from ...schemas.web.common import Capability, CapabilityStatus, WebErrorCode
from ...schemas.web.food import FoodFeedback, FoodPreference, FoodRecommendation, FoodRecommendationList, FoodRecommendationRequest, PreferenceSubject
from ...web_platform import WebAPIError, WebPrincipal, require_csrf, require_idempotency_key, require_principal
from ._shared import cap, idempotent, require_pet, web_of, web_router

router = web_router("food_discovery")


def capabilities(settings) -> list[Capability]:
    return [
        cap("food.preferences", "food_discovery", CapabilityStatus.available),
        cap("food.recommendations", "food_discovery", CapabilityStatus.available if settings.web_demo_catalog else CapabilityStatus.not_configured,
            "确定性筛选+重排已实现；资料为演示小样本，只在演示环境提供" if settings.web_demo_catalog else
            "没有获准分析的真实菜单/评论资料；演示小样本只在演示环境提供，正式环境不给推荐"),
        cap("food.feedback", "food_discovery", CapabilityStatus.available, "主人自报，只修正口味偏好，不回流为品质证据"),
        cap("food.real_evidence", "food_discovery", CapabilityStatus.not_implemented, "尚无获准分析的真实菜单/评论资料"),
    ]


def _translate(exc: FoodError) -> WebAPIError:
    if exc.reason == "not_found":
        return WebAPIError.not_found("这条推荐")
    if exc.reason in ("bad_context", "not_allowed"):
        return WebAPIError(WebErrorCode.validation_failed, exc.message, 422, details={"reason": exc.reason})
    return WebAPIError(WebErrorCode.conflict, exc.message, 409, details={"reason": exc.reason})


def _pet(request: Request, principal: WebPrincipal, pet_id: str) -> None:
    """这只宠物的家人（口味偏好与推荐是每位家人自己的，别的家人看不到）。"""
    require_pet(request, principal, pet_id)


@router.get("/food/preferences/{subject}", response_model=FoodPreference)
def get_food_preference(subject: PreferenceSubject, pet_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> FoodPreference:
    _pet(request, principal, pet_id)
    return web_of(request).food.preference(principal.user_id, pet_id, subject)


@router.put("/food/preferences/{subject}", response_model=FoodPreference, dependencies=[Depends(require_csrf)])
def put_food_preference(subject: PreferenceSubject, body: FoodPreference, request: Request, principal: WebPrincipal = Depends(require_principal),
                        idempotency_key: str = Depends(require_idempotency_key)) -> FoodPreference:
    _pet(request, principal, body.pet_id)
    return idempotent(request, principal, f"food.pref:{subject.value}", idempotency_key, body.model_dump(mode="json"), FoodPreference,
                      lambda: web_of(request).food.put_preference(principal.user_id, body.pet_id, subject, body))


@router.post("/food/recommendations", response_model=FoodRecommendationList, dependencies=[Depends(require_csrf)])
def request_recommendations(body: FoodRecommendationRequest, request: Request, principal: WebPrincipal = Depends(require_principal)) -> FoodRecommendationList:
    _pet(request, principal, body.pet_id)
    if not request.app.state.settings.web_demo_catalog:
        raise WebAPIError.capability_unavailable("food.recommendations", CapabilityStatus.not_configured)
    try:
        return web_of(request).food.recommend(principal.user_id, body)
    except FoodError as exc:
        raise _translate(exc) from exc


@router.get("/food/recommendations/{recommendation_id}", response_model=FoodRecommendation)
def get_recommendation(recommendation_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> FoodRecommendation:
    try:
        return web_of(request).food.recommendation(principal.user_id, recommendation_id)[0]
    except FoodError as exc:
        raise _translate(exc) from exc


@router.post("/food/feedback", response_model=FoodFeedback, status_code=201, dependencies=[Depends(require_csrf)])
def submit_feedback(body: FoodFeedback, request: Request, principal: WebPrincipal = Depends(require_principal),
                    idempotency_key: str = Depends(require_idempotency_key)) -> FoodFeedback:
    def handler() -> FoodFeedback:
        try:
            return web_of(request).food.feedback(principal.user_id, body)
        except FoodError as exc:
            raise _translate(exc) from exc

    return idempotent(request, principal, "food.feedback", idempotency_key, body.model_dump(mode="json"), FoodFeedback, handler)
