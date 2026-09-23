"""网页路由共享辅助：统一前缀、错误响应声明、能力声明、服务获取、家/入住守卫与幂等执行。

模块路由只做：鉴权/CSRF/幂等依赖 → 调用 app.state.web 中的领域服务 → 把领域错误翻译成稳定错误码。
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ...schemas.web.common import WEB_API_PREFIX, Capability, CapabilityStatus, WebErrorCode, WebErrorEnvelope
from ...web_household import Action, HouseholdError
from ...web_platform.errors import WebAPIError
from ...web_platform.session import WebPrincipal

ERROR_RESPONSES = {
    status: {"model": WebErrorEnvelope}
    for status in (400, 401, 403, 404, 409, 422, 429, 500, 501, 503)
}

M = TypeVar("M", bound=BaseModel)


def web_router(tag: str) -> APIRouter:
    return APIRouter(prefix=WEB_API_PREFIX, tags=[f"web:{tag}"], responses=ERROR_RESPONSES)


def not_implemented(capability: str) -> WebAPIError:
    return WebAPIError.capability_unavailable(capability, CapabilityStatus.not_implemented)


def cap(key: str, module: str, status: CapabilityStatus, note: str | None = None) -> Capability:
    return Capability(key=key, module=module, status=status, note=note)


def web_of(request: Request):
    return request.app.state.web


def conflict(reason: str, message: str, code: WebErrorCode = WebErrorCode.conflict, status: int = 409, **details: Any) -> WebAPIError:
    return WebAPIError(code, message, status, details={"reason": reason, **details})


def household_error(exc: HouseholdError) -> WebAPIError:
    """家庭领域错误 → 稳定错误码：不是成员 404（不暴露资源是否存在）；角色不够 403；没加入家庭 409 PET_NOT_ACTIVATED；需要指明宠物/家庭 409。"""
    if exc.status == 404:
        return WebAPIError(WebErrorCode.not_found, exc.message, 404, details={"reason": exc.reason, **exc.details})
    if exc.status == 403:
        return WebAPIError(WebErrorCode.forbidden, exc.message, 403, details={"reason": exc.reason, **exc.details})
    if exc.reason == "needs_companion":
        return WebAPIError(WebErrorCode.pet_not_activated, exc.message, 409, details={"reason": exc.reason, "onboarding_step": "needs_companion", **exc.details})
    return WebAPIError(WebErrorCode.conflict, exc.message, exc.status, details={"reason": exc.reason, **exc.details})


def require_pet(request: Request, principal: WebPrincipal, pet_id: str | None = None, *, activated: bool = False, action: Action = Action.view):
    """这位成员要照顾的那只宠物与它的家（PetHome）。

    - pet_id 显式给出时按它；没给时只有“能照顾的宠物恰好一只”才默认它（兼容只养一只的旧页面），否则 409 pet_required；
    - 每次请求都查有效成员关系：被移除的成员立刻失去访问权；
    - activated=True 时要求家已经入住、这只宠物也已经住进来。"""
    web = web_of(request)
    try:
        access = web.households.resolve_pet(principal.user_id, pet_id, action)
    except HouseholdError as exc:
        raise household_error(exc) from exc
    pet_home = web.homes.pet_home(access)
    if activated:
        if pet_home.activated_at is None:
            raise WebAPIError(WebErrorCode.pet_not_activated, "还没入住，先完成入住。", 409,
                              details={"onboarding_step": web.homes.onboarding(principal.user_id).step.value, "pet_id": access.pet_id})
        step = web.homes.join_step(access.pet_id, pet_home.home)
        if step.value != "moved_in":
            raise WebAPIError(WebErrorCode.pet_not_activated, "这只宠物还没住进来，先完成它的入住。", 409,
                              details={"onboarding_step": step.value, "pet_id": access.pet_id})
    return pet_home


def require_home(request: Request, principal: WebPrincipal, activated: bool = False, pet_id: str | None = None, action: Action = Action.view):
    """旧名字，保留给只需要“这只宠物和它的家”的路由；等同 require_pet。"""
    return require_pet(request, principal, pet_id, activated=activated, action=action)


def require_household(request: Request, principal: WebPrincipal, household_id: str | None = None, pet_id: str | None = None,
                      action: Action = Action.view):
    """(HouseholdAccess, HomeRow)：家庭层面的操作（成员、邀请、设置、家庭仓库、串门）。"""
    web = web_of(request)
    try:
        access = web.households.resolve_household(principal.user_id, household_id, pet_id, action)
    except HouseholdError as exc:
        raise household_error(exc) from exc
    home = web.homes.by_household(access.household_id)
    return access, home


def idempotent(request: Request, principal: WebPrincipal, scope: str, key: str, payload: Any, model: type[M], handler: Callable[[], M]) -> M:
    """同一用户同一 scope 下，同键同请求返回首个结果；同键不同请求 409。"""
    store = request.app.state.web_idempotency
    outcome = store.run(user_id=principal.user_id, scope=scope, key=key, payload=payload, handler=lambda: handler().model_dump(mode="json"))
    return model.model_validate(outcome.response)


def redraw(web, ticket: str | None, state: str | None, missing: str) -> str:
    """三条"重画"入口（通讯器插画 / 收藏明信片 / 攻略手账图）的统一处理。返回这次实际发生了什么。

    两层判断，缺一不可：
    - 拿不到重画凭据时，还要问一次"这个对象在不在"。**拿不到凭据 ≠ 找不到对象**：
      正在画、已经画好，对象都在，应当回当前状态，不能一律 404；只有 `state` 也是 None 才是真的找不到。
    - 拿到凭据就交给 `illustrations.retry`，它返回四种结果，**不能一律当成"新尝试已创建"**：
      `requeued` 真排了一次；`already_queued` 已经在排队/执行中（连点或并发）；
      `stale_attempt` 这次点击对应的是更早那次失败（迟到的重复请求）——这三种都回当前状态；
      `not_retryable` 是"这东西不能重画"（已画好、已作废、任务号不存在）——明确拒绝。
    防重复发起的最终保护在 `retry` 的同一个写事务里，不在这里的查询。
    """
    if ticket is None:
        if state is None:
            raise WebAPIError.not_found(missing)
        return "unavailable"  # 对象在，只是这一刻不能重画（正在画 / 已经画好）
    outcome = web.illustrations.retry(ticket)
    if outcome == "not_retryable":
        raise WebAPIError.not_found(missing)
    return outcome

