"""经济系统端点：钱包、物品、售卖、归档、开发者拨款。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from ..dependencies import get_engine, get_settings
from ..economy_engine import EconomyConflictError
from .helpers import with_not_found
from ..schemas import (
    ArchiveItemRequest,
    EconomyResponse,
    InventoryResponse,
    ItemMutationResponse,
    ItemStatus,
    OwnerFundGrantRequest,
    SellItemRequest,
)

router = APIRouter()


@router.get("/api/v1/pets/{pet_id}/economy", response_model=EconomyResponse)
def pet_economy(pet_id: str, engine=Depends(get_engine)) -> EconomyResponse:
    return with_not_found(lambda: engine.economy(pet_id))


@router.get("/api/v1/pets/{pet_id}/inventory", response_model=InventoryResponse)
def pet_inventory(
    pet_id: str,
    status: str = "owned",
    limit: int = 50,
    engine=Depends(get_engine),
) -> InventoryResponse:
    item_status: ItemStatus | None
    if status == "all":
        item_status = None
    else:
        try:
            item_status = ItemStatus(status)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid item status") from exc
    return with_not_found(lambda: engine.inventory(pet_id, status=item_status, limit=limit))


@router.post("/api/v1/pets/{pet_id}/items/{item_id}/sell", response_model=ItemMutationResponse)
def sell_item(
    pet_id: str,
    item_id: str,
    request: SellItemRequest,
    engine=Depends(get_engine),
) -> ItemMutationResponse:
    try:
        return with_not_found(lambda: engine.sell_item(pet_id, item_id, request))
    except EconomyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/api/v1/pets/{pet_id}/items/{item_id}/archive", response_model=ItemMutationResponse)
def archive_item(
    pet_id: str,
    item_id: str,
    request: ArchiveItemRequest,
    engine=Depends(get_engine),
) -> ItemMutationResponse:
    try:
        return with_not_found(lambda: engine.archive_item(pet_id, item_id, request))
    except EconomyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/api/v1/pets/{pet_id}/owner_fund/grant", response_model=EconomyResponse)
def grant_owner_fund(
    pet_id: str,
    request: OwnerFundGrantRequest,
    admin_token: str | None = Header(default=None, alias="X-PetJourney-Admin-Token"),
    settings=Depends(get_settings),
    engine=Depends(get_engine),
) -> EconomyResponse:
    if not settings.economy_dev_grants_enabled or not settings.economy_admin_token:
        raise HTTPException(status_code=403, detail="owner fund grants are disabled")
    if admin_token != settings.economy_admin_token:
        raise HTTPException(status_code=403, detail="invalid admin token")
    try:
        return with_not_found(lambda: engine.grant_owner_fund(pet_id, request))
    except EconomyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
