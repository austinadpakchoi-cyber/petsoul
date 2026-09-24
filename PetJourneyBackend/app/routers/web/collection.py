"""回忆与收藏 + 集市（杂货铺收购与居民订单，都是 NPC）。玩家挂牌交易关闭：主线稳定前不开放。

0.4.0：收藏按 ?pet_id= 指明是哪只宠物的（只照顾一只时可省略）；集市卖的是这个家共用的仓库，
?pet_id= 指明换来的旅费进哪只宠物的账户。"""

from __future__ import annotations

from fastapi import Depends, Request

from ...schemas.web.common import Capability, CapabilityStatus, WebErrorCode
from ...schemas.web.market import MarketResult, MarketView, SellRequest
from ...schemas.web.social import CollectionItem
from ...web_market import MarketError
from ...web_platform import WebAPIError, WebPrincipal, require_csrf, require_idempotency_key, require_principal
from ...web_household import Action
from ._shared import cap, idempotent, redraw, require_pet, web_of, web_router

router = web_router("collection")


def capabilities(settings) -> list[Capability]:
    return [
        cap("collection.items", "collection", CapabilityStatus.available),
        cap("market.npc_shop", "market", CapabilityStatus.available, "杂货铺按固定价收购仓库物资"),
        cap("market.resident_orders", "market", CapabilityStatus.available, "星球居民每日两张订单，出价高于杂货铺"),
        cap("market.player_listing", "market", CapabilityStatus.disabled, "主线稳定后再评估一种物资固定价挂牌；当前不开放"),
    ]


def _translate(exc: MarketError) -> WebAPIError:
    if exc.reason in ("not_found", "unknown_item"):
        return WebAPIError.not_found("这件物资或订单")
    return WebAPIError(WebErrorCode.conflict, exc.message, 409, details={"reason": exc.reason})


@router.get("/collection", response_model=list[CollectionItem])
def list_collection(request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> list[CollectionItem]:
    home = require_pet(request, principal, pet_id)
    web = web_of(request)
    return web.collection.items(principal.user_id, home.pet_id)


@router.post("/collection/{pet_id}/items/{item_id}/retry-image", response_model=list[CollectionItem], dependencies=[Depends(require_csrf)])
def retry_collection_image(pet_id: str, item_id: str, request: Request,
                           principal: WebPrincipal = Depends(require_principal)) -> list[CollectionItem]:
    """明信片没画成（或结果没确认）时由家人重画：重新排队，不重复发藏品（CR-A10）。

    和通讯器的 `retry-photo` 同构：两层判断——路由这层看家庭成员与 care 权限，
    服务那层看归属与展示状态。连点两次的第二次拿不到任务号，不会再发起一次付费尝试。
    """
    require_pet(request, principal, pet_id, action=Action.care)
    web = web_of(request)
    redraw(web, web.collection.image_retrying(principal.user_id, pet_id, item_id),
           web.collection.image_state_for(principal.user_id, pet_id, item_id), "可以重画的明信片")
    return web.collection.items(principal.user_id, pet_id)


@router.get("/market", response_model=MarketView)
def market_view(request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> MarketView:
    web = web_of(request)
    home = require_pet(request, principal, pet_id, activated=True)
    return web.market.view(web.homes.ref(home.home, principal.user_id), home.pet_id)


@router.post("/market/sell", response_model=MarketResult, dependencies=[Depends(require_csrf)])
def market_sell(body: SellRequest, request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal),
                idempotency_key: str = Depends(require_idempotency_key)) -> MarketResult:
    web = web_of(request)
    home = require_pet(request, principal, pet_id, activated=True, action=Action.care)

    def handler() -> MarketResult:
        try:
            return web.market.sell(web.homes.ref(home.home, principal.user_id), body.item_key, body.qty, idempotency_key, pet_id=home.pet_id)
        except MarketError as exc:
            raise _translate(exc) from exc

    return idempotent(request, principal, "market.sell", idempotency_key, {**body.model_dump(), "pet_id": home.pet_id}, MarketResult, handler)


@router.post("/market/orders/{order_id}/fulfill", response_model=MarketResult, dependencies=[Depends(require_csrf)])
def market_fulfill(order_id: str, request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal),
                   idempotency_key: str = Depends(require_idempotency_key)) -> MarketResult:
    web = web_of(request)
    home = require_pet(request, principal, pet_id, activated=True, action=Action.care)

    def handler() -> MarketResult:
        try:
            return web.market.fulfill(web.homes.ref(home.home, principal.user_id), order_id, pet_id=home.pet_id)
        except MarketError as exc:
            raise _translate(exc) from exc

    return idempotent(request, principal, f"market.order:{order_id}", idempotency_key, {"order_id": order_id, "pet_id": home.pet_id}, MarketResult, handler)
