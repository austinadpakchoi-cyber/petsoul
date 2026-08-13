"""经济编排：钱包、库存与物品的买卖/归档/资助。"""

from __future__ import annotations

from ..schemas import (
    ArchiveItemRequest,
    EconomyResponse,
    InventoryResponse,
    ItemMutationResponse,
    ItemStatus,
    OwnerFundGrantRequest,
    SellItemRequest,
)
from ..storage import utcnow


class EconomyMixin:
    def economy(self, pet_id: str) -> EconomyResponse:
        self._pet(pet_id)
        return self.economy_engine.economy(pet_id)

    def inventory(self, pet_id: str, status: ItemStatus | None = ItemStatus.owned, limit: int = 50) -> InventoryResponse:
        self._pet(pet_id)
        return self.economy_engine.inventory(pet_id, status=status, limit=limit)

    def sell_item(self, pet_id: str, item_id: str, request: SellItemRequest) -> ItemMutationResponse:
        self._pet(pet_id)
        return self.economy_engine.sell_item(pet_id=pet_id, item_id=item_id, request=request, now=utcnow())

    def archive_item(self, pet_id: str, item_id: str, request: ArchiveItemRequest) -> ItemMutationResponse:
        self._pet(pet_id)
        return self.economy_engine.archive_item(pet_id=pet_id, item_id=item_id, request=request, now=utcnow())

    def grant_owner_fund(self, pet_id: str, request: OwnerFundGrantRequest) -> EconomyResponse:
        self._pet(pet_id)
        return self.economy_engine.grant_owner_fund(pet_id=pet_id, request=request, now=utcnow())
