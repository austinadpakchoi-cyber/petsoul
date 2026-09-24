"""菜园与串门：种植/收获、邻居列表、访问别人家的菜园、互偷（宠物在家守护时偷不到）。

0.4.0 家庭：菜园属于这个家（家庭共用）。种植/收获用请求里的 home_id 找到家庭并检查成员关系；
串门、偷菜、巡院按 ?household_id=（或 ?pet_id=）指明是哪个家庭（只在一个家庭时可省略）。
每批作物每个家庭只能摘一次；自己家庭的菜不能偷；守护看家里此刻在家的全部宠物。"""

from __future__ import annotations

from fastapi import Depends, Request

from ...schemas.web.common import Capability, CapabilityStatus, WebErrorCode
from ...schemas.web.farm import CropInfo, NeighborHomeSummary, NeighborHomeView, PatrolResult, StealRequest, StealResult
from ...schemas.web.home import FarmActionKind, FarmActionRequest, FarmActionResult
from ...web_farm import CROPS, FarmError
from ...web_platform import WebAPIError, WebPrincipal, require_csrf, require_idempotency_key, require_principal
from ...utils import utcnow
from ...web_household import Action
from ._shared import cap, idempotent, require_household, web_of, web_router

router = web_router("farm")


def capabilities(settings) -> list[Capability]:
    return [
        cap("farm.actions", "farm", CapabilityStatus.available),
        cap("farm.steal", "farm", CapabilityStatus.available, "每批作物全体访客共享可偷上限；宠物在家守护；偷到的是物资"),
        cap("farm.patrol", "farm", CapabilityStatus.available, "宠物外出时主人巡院 10 分钟，冷却 30 分钟"),
    ]


def _translate(exc: FarmError) -> WebAPIError:
    if exc.reason == "not_found":
        return WebAPIError.not_found("这块地")
    if exc.reason == "guarded":
        return WebAPIError(WebErrorCode.farm_guarded, exc.message, 409, details={"reason": exc.reason})
    return WebAPIError(WebErrorCode.conflict, exc.message, 409, details={"reason": exc.reason})


@router.get("/farm/crops", response_model=list[CropInfo])
def crops(principal: WebPrincipal = Depends(require_principal)) -> list[CropInfo]:
    return list(CROPS.values())


@router.post("/farm/actions", response_model=FarmActionResult, dependencies=[Depends(require_csrf)])
def farm_action(body: FarmActionRequest, request: Request, principal: WebPrincipal = Depends(require_principal),
                idempotency_key: str = Depends(require_idempotency_key)) -> FarmActionResult:
    web = web_of(request)
    household_id = web.households.household_of_home(body.home_id)
    if household_id is None:
        raise WebAPIError.not_found("这个家")
    _, home = _my_home(request, principal, household_id=household_id, action=Action.care)
    ref = web.homes.ref(home, principal.user_id)

    def handler() -> FarmActionResult:
        try:
            if body.action is FarmActionKind.plant:
                plot = web.farm.plant(ref, body.plot_id, body.crop_key or "sun_pea")
                return FarmActionResult(plot=plot, wallet=web.economy.wallet(ref.pet_id), gained_items=[])
            if body.action is FarmActionKind.harvest:
                plot, wallet, units = web.farm.harvest(ref, body.plot_id)
                return FarmActionResult(plot=plot, wallet=wallet, gained_items=[f"{plot.crop_label} ×{units} 进了仓库"])
        except FarmError as exc:
            raise _translate(exc) from exc
        raise WebAPIError(WebErrorCode.validation_failed, "偷菜请到邻居家的菜园。", 422)

    return idempotent(request, principal, "farm.action", idempotency_key, body.model_dump(mode="json"), FarmActionResult, handler)


@router.get("/neighbors", response_model=list[NeighborHomeSummary])
def neighbors(request: Request, household_id: str | None = None, pet_id: str | None = None,
              principal: WebPrincipal = Depends(require_principal)) -> list[NeighborHomeSummary]:
    web = web_of(request)
    _, home = _my_home(request, principal, household_id=household_id, pet_id=pet_id)

    def avatar(pet_id: str) -> str | None:
        record = web.pets.profile(pet_id)
        return web.pets.photo_url(record) if record and record.visibility.value == "public" else None

    return web.farm.neighbors(web.homes.ref(home, principal.user_id), avatar, web.homes.ref_of_home)


@router.get("/homes/{home_id}", response_model=NeighborHomeView)
def visit_home(home_id: str, request: Request, household_id: str | None = None, pet_id: str | None = None,
               principal: WebPrincipal = Depends(require_principal)) -> NeighborHomeView:
    web = web_of(request)
    _, mine = _my_home(request, principal, household_id=household_id, pet_id=pet_id)
    target = web.homes.by_home_id(home_id)
    if target is None or target.activated_at is None:
        raise WebAPIError.not_found("这个家")
    target_ref = web.homes.ref(target)
    record = web.pets.profile(target_ref.pet_id)
    avatar = web.pets.photo_url(record) if record and record.visibility.value == "public" else None
    return web.farm.visit(web.homes.ref(mine, principal.user_id), target_ref, avatar)


@router.post("/farm/steal", response_model=StealResult, dependencies=[Depends(require_csrf)])
def steal(body: StealRequest, request: Request, household_id: str | None = None, pet_id: str | None = None,
          principal: WebPrincipal = Depends(require_principal), idempotency_key: str = Depends(require_idempotency_key)) -> StealResult:
    """去别的家庭的菜园摘一颗（摘到的进自己家庭的仓库）。每批作物每个家庭只能摘一次。"""
    web = web_of(request)
    _, mine = _my_home(request, principal, household_id=household_id, pet_id=pet_id, action=Action.care)
    target = web.homes.by_home_id(body.home_id)
    if target is None or target.activated_at is None:
        raise WebAPIError.not_found("这个家")

    def handler() -> StealResult:
        try:
            plot, item_key, message = web.farm.steal(web.homes.ref(mine, principal.user_id), web.homes.ref(target), body.plot_id, body.cycle_id)
        except FarmError as exc:
            raise _translate(exc) from exc
        return StealResult(home_id=body.home_id, plot=plot, gained_item_key=item_key, gained_units=1, message=message)

    return idempotent(request, principal, "farm.steal", idempotency_key, {**body.model_dump(), "household_id": mine.household_id}, StealResult, handler)


@router.post("/farm/patrol", response_model=PatrolResult, dependencies=[Depends(require_csrf)])
def patrol(request: Request, household_id: str | None = None, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> PatrolResult:
    """全家宠物都不在家时家人巡院：短时守护菜园（有冷却）。巡院中重复点击返回同一窗口。"""
    web = web_of(request)
    _, home = _my_home(request, principal, household_id=household_id, pet_id=pet_id, action=Action.care)
    try:
        web.farm.patrol(web.homes.ref(home, principal.user_id))
    except FarmError as exc:
        raise _translate(exc) from exc
    guard = web.homes.guard_state(web.homes.by_home_id(home.home_id) or home, utcnow())
    return PatrolResult(guard=guard, message="你在院子里转了一圈，这段时间邻居摘不走菜。")


def _my_home(request: Request, principal: WebPrincipal, *, household_id: str | None = None, pet_id: str | None = None, action: Action = Action.view):
    """(HouseholdAccess, HomeRow)：自己家庭的家，要求已经入住。"""
    access, home = require_household(request, principal, household_id, pet_id, action)
    if home is None or home.activated_at is None:
        raise WebAPIError(WebErrorCode.pet_not_activated, "还没入住，先完成入住。", 409, details={"onboarding_step": "reception_optional"})
    return access, home

