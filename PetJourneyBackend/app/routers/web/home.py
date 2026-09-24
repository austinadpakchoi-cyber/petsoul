"""共同的家：HomeSnapshot（权威快照：宠物唯一位置、守护、统一钱包、菜园、旅途摘要、入住欢迎、未读）。

0.4.0 家庭：一个家庭一个家，多只宠物共用。/home?pet_id= 指明以哪只宠物的视角看（钱包、位置、旅途、未读都是这只的；
菜园、仓库、守护是全家的；pets 列出家里每一只）。只照顾一只时可省略。家的位置属于家庭，只有管理员能搬家。"""

from __future__ import annotations

from fastapi import Depends, Request

from ...schemas.web.common import Capability, CapabilityStatus, WebErrorCode
from ...schemas.web.home import HabitatKind, HabitatOption, HomePlaceRequest, HomePlaceSummary, HomePlaceView, HomeSnapshot
from ...schemas.web.pets import PetPresence
from ...utils import utcnow
from ...web_home.place import HABITATS, OPEN_AREAS
from ...web_household import Action
from ...web_platform import WebAPIError, WebPrincipal, require_csrf, require_principal
from ._shared import cap, require_pet, web_of, web_router

router = web_router("home")


def capabilities(settings) -> list[Capability]:
    return [
        cap("home.snapshot", "home", CapabilityStatus.available),
        cap("home.place", "home", CapabilityStatus.available,
            "家是一个概念：选一类地方，落在一个片区（不给具体地址）。新家只开放交通与地点都已接通的片区（香港·中环、香港·西贡）；已有的家保持原地"),
    ]


def place_summary(place) -> HomePlaceSummary:
    return HomePlaceSummary(habitat=HabitatKind(place.habitat), habitat_label=place.habitat_label, city=place.city, area_label=place.area_label,
                            display=place.display, timezone=place.timezone, chosen=place.chosen)


def _place_view(request: Request, home) -> HomePlaceView:
    """options 里 open=false 的类型暂未开放给新家（没有完整的真实交通与地点支持）。搬家要求全家宠物都在家，并且是家庭管理员。"""
    web = web_of(request)
    options = [HabitatOption(habitat=HabitatKind(key), label=label, examples=list(dict.fromkeys(a.city for a in areas if a.key in OPEN_AREAS)) or
                             list(dict.fromkeys(a.city for a in areas)), open=any(a.key in OPEN_AREAS for a in areas))
               for key, (label, areas) in HABITATS.items()]
    pets = web.households.pets_of(home.household_id) if home.household_id else [home.pet_id]
    everyone_home = all(web.presence(p) in (PetPresence.at_home, PetPresence.not_activated) for p in pets)
    can_change = everyone_home and home.access.allows(Action.manage)
    return HomePlaceView(place=place_summary(web.home_places.get(home.home_id)), options=options, can_change=can_change)


@router.get("/home/place", response_model=HomePlaceView)
def read_place(request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> HomePlaceView:
    return _place_view(request, require_pet(request, principal, pet_id))


@router.put("/home/place", response_model=HomePlaceView, dependencies=[Depends(require_csrf)])
def choose_place(body: HomePlaceRequest, request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> HomePlaceView:
    """选一类地方，服务端在对应的开放片区里分配（迁居，整个家庭一起搬）。同一类型重复提交保持原来的地方；有宠物在外面时不能搬家。"""
    home = require_pet(request, principal, pet_id, action=Action.manage)
    view = _place_view(request, home)
    if not view.can_change:
        raise WebAPIError(WebErrorCode.conflict, "有宠物还在外面，等大家都回家了再搬。", 409, details={"reason": "pet_away"})
    try:
        web_of(request).home_places.assign(home.home_id, body.habitat.value, utcnow(), open_only=True)
    except ValueError as exc:
        raise WebAPIError(WebErrorCode.validation_failed, str(exc), 422, details={"reason": "habitat_not_supported"}) from exc
    return _place_view(request, home)


@router.get("/home", response_model=HomeSnapshot)
def home_snapshot(request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> HomeSnapshot:
    """这只宠物视角的家（多只宠物时用 ?pet_id= 切换；pets 字段列出家里每一只，页面据此做标签切换）。只读：不推进世界。"""
    web = web_of(request)
    home = require_pet(request, principal, pet_id)
    return web.homes.snapshot(home).model_copy(update={"catching_up": web.journeys.catching_up(home.pet_id)})
