from __future__ import annotations

from datetime import datetime
import hashlib
import sqlite3

from .config import Settings
from .schemas import (
    AcquisitionSource,
    ArchiveItemRequest,
    CollectSouvenirsResponse,
    CurrencyAmounts,
    EconomyResponse,
    EconomySnapshot,
    EconomyTransaction,
    EconomyTransactionType,
    InventoryResponse,
    ItemMutationResponse,
    ItemStatus,
    OwnerFund,
    OwnerFundGrantRequest,
    SellItemRequest,
    SouvenirItem,
    TradePolicy,
    TravelQuest,
    Wallet,
)
from .storage import EconomyStorageConflict, JourneyStorage, PetRecord, utcnow


class EconomyConflictError(Exception):
    pass


class PetEconomyEngine:
    provider_name = "petsoul-economy-engine"

    def __init__(self, storage: JourneyStorage, settings: Settings):
        self.storage = storage
        self.settings = settings

    def economy(self, pet_id: str, now: datetime | None = None) -> EconomyResponse:
        timestamp = now or utcnow()
        wallet = self.storage.get_wallet(pet_id) or self._empty_wallet(pet_id, timestamp)
        owner_fund = self.storage.get_owner_fund(pet_id) or self._empty_owner_fund(pet_id, timestamp)
        snapshot = self.storage.get_economy_snapshot(pet_id) or self._snapshot_from_items(
            pet_id=pet_id,
            items=self.storage.list_inventory(pet_id, status=None, limit=200),
            now=timestamp,
        )
        return EconomyResponse(
            wallet=wallet,
            owner_fund=owner_fund,
            snapshot=snapshot,
            recent_transactions=self.storage.list_economy_transactions(pet_id, limit=20),
        )

    def inventory(self, pet_id: str, status: ItemStatus | None = ItemStatus.owned, limit: int = 50) -> InventoryResponse:
        items = self.storage.list_inventory(pet_id, status=status, limit=limit)
        snapshot = self.storage.get_economy_snapshot(pet_id) or self._snapshot_from_items(
            pet_id=pet_id,
            items=self.storage.list_inventory(pet_id, status=None, limit=200),
            now=utcnow(),
        )
        return InventoryResponse(items=items, snapshot=snapshot)

    def collect_souvenirs(
        self,
        *,
        pet: PetRecord,
        quest: TravelQuest,
        souvenirs: list[SouvenirItem],
        weather: str | None,
        now: datetime,
    ) -> CollectSouvenirsResponse:
        idempotency_key = f"collect_souvenirs:{pet.pet_id}:{quest.id}"
        existing_transaction = self.storage.get_transaction_by_idempotency_key(idempotency_key)
        if existing_transaction:
            items = self.storage.list_souvenirs_for_quest(pet.pet_id, quest.id)
            economy = self.economy(pet.pet_id, now=now)
            return CollectSouvenirsResponse(
                items=items,
                transactions=[existing_transaction],
                wallet=economy.wallet,
                snapshot=economy.snapshot,
            )

        enriched = [
            self._enrich_souvenir(
                pet=pet,
                quest=quest,
                item=item,
                weather=weather,
                now=now,
                index=index,
            )
            for index, item in enumerate(souvenirs)
        ]
        wallet = self.storage.get_wallet(pet.pet_id) or self._empty_wallet(pet.pet_id, now)
        snapshot = self._snapshot_after_changes(pet.pet_id, changed_items=enriched, now=now)
        transaction = self._transaction(
            pet_id=pet.pet_id,
            type=EconomyTransactionType.item_acquired,
            idempotency_key=idempotency_key,
            amounts=CurrencyAmounts(),
            item_ids=[item.id for item in enriched],
            before={
                "owned_item_count": self._snapshot_from_items(
                    pet_id=pet.pet_id,
                    items=self.storage.list_inventory(pet.pet_id, status=None, limit=200),
                    now=now,
                ).owned_item_count,
            },
            after={
                "owned_item_count": snapshot.owned_item_count,
                "total_display_value": snapshot.total_display_value,
            },
            reason=f"从 {quest.destination} 带回 {len(enriched)} 件小收藏",
            operator="pet",
            source="travel_quest_collect",
            now=now,
        )
        committed, created = self.apply_transaction(
            transaction=transaction,
            wallet=wallet,
            snapshot=snapshot,
            souvenirs=enriched,
        )
        if not created:
            enriched = self.storage.list_souvenirs_for_quest(pet.pet_id, quest.id)
            economy = self.economy(pet.pet_id, now=now)
            return CollectSouvenirsResponse(
                items=enriched,
                transactions=[committed],
                wallet=economy.wallet,
                snapshot=economy.snapshot,
            )
        return CollectSouvenirsResponse(items=enriched, transactions=[committed], wallet=wallet, snapshot=snapshot)

    def sell_item(self, *, pet_id: str, item_id: str, request: SellItemRequest, now: datetime) -> ItemMutationResponse:
        idempotency_key = f"sell_item:{pet_id}:{item_id}:{request.client_request_id}"
        existing_transaction = self.storage.get_transaction_by_idempotency_key(idempotency_key)
        if existing_transaction:
            item = self._item_or_raise(pet_id, item_id)
            economy = self.economy(pet_id, now=now)
            return ItemMutationResponse(
                success=True,
                transaction=existing_transaction,
                wallet=economy.wallet,
                item=item,
                snapshot=economy.snapshot,
            )

        item = self._item_or_raise(pet_id, item_id)
        if item.version != request.expected_item_version:
            raise EconomyConflictError("item version mismatch")
        if item.status != ItemStatus.owned:
            raise EconomyConflictError("item is not owned")
        if not self._is_sellable(item, now=now):
            raise EconomyConflictError("item is not sellable")

        sell_value = max(0, item.market_value // 2)
        wallet_before = self.storage.get_wallet(pet_id) or self._empty_wallet(pet_id, now)
        wallet_after = wallet_before.model_copy(
            update={"travel_coin": wallet_before.travel_coin + sell_value, "updated_at": now}
        )
        updated_item = item.model_copy(
            update={"status": ItemStatus.sold, "version": item.version + 1, "updated_at": now}
        )
        snapshot = self._snapshot_after_changes(pet_id, changed_items=[updated_item], now=now)
        transaction = self._transaction(
            pet_id=pet_id,
            type=EconomyTransactionType.item_sold,
            idempotency_key=idempotency_key,
            amounts=CurrencyAmounts(travel_coin=sell_value),
            item_ids=[item.id],
            before={"wallet_travel_coin": wallet_before.travel_coin, "item_status": item.status.value, "item_version": item.version},
            after={
                "wallet_travel_coin": wallet_after.travel_coin,
                "item_status": updated_item.status.value,
                "item_version": updated_item.version,
            },
            reason=f"出售{item.title}",
            operator="pet",
            source="inventory_sell",
            now=now,
        )
        committed, _ = self.apply_transaction(
            transaction=transaction,
            wallet=wallet_after,
            snapshot=snapshot,
            souvenirs=[updated_item],
            expected_item_versions={item.id: request.expected_item_version},
        )
        return ItemMutationResponse(
            success=True,
            transaction=committed,
            wallet=wallet_after,
            item=updated_item,
            snapshot=snapshot,
        )

    def archive_item(self, *, pet_id: str, item_id: str, request: ArchiveItemRequest, now: datetime) -> ItemMutationResponse:
        idempotency_key = f"archive_item:{pet_id}:{item_id}:{request.client_request_id}"
        existing_transaction = self.storage.get_transaction_by_idempotency_key(idempotency_key)
        if existing_transaction:
            item = self._item_or_raise(pet_id, item_id)
            economy = self.economy(pet_id, now=now)
            return ItemMutationResponse(
                success=True,
                transaction=existing_transaction,
                wallet=economy.wallet,
                item=item,
                snapshot=economy.snapshot,
            )

        item = self._item_or_raise(pet_id, item_id)
        if item.version != request.expected_item_version:
            raise EconomyConflictError("item version mismatch")
        if item.status not in {ItemStatus.owned, ItemStatus.stored}:
            raise EconomyConflictError("item cannot be archived")

        wallet = self.storage.get_wallet(pet_id) or self._empty_wallet(pet_id, now)
        updated_item = item.model_copy(
            update={"status": ItemStatus.archived, "version": item.version + 1, "updated_at": now}
        )
        snapshot = self._snapshot_after_changes(pet_id, changed_items=[updated_item], now=now)
        transaction = self._transaction(
            pet_id=pet_id,
            type=EconomyTransactionType.item_archived,
            idempotency_key=idempotency_key,
            amounts=CurrencyAmounts(),
            item_ids=[item.id],
            before={"item_status": item.status.value, "item_version": item.version},
            after={"item_status": updated_item.status.value, "item_version": updated_item.version},
            reason=f"归档{item.title}",
            operator="owner",
            source="inventory_archive",
            now=now,
        )
        committed, _ = self.apply_transaction(
            transaction=transaction,
            wallet=wallet,
            snapshot=snapshot,
            souvenirs=[updated_item],
            expected_item_versions={item.id: request.expected_item_version},
        )
        return ItemMutationResponse(
            success=True,
            transaction=committed,
            wallet=wallet,
            item=updated_item,
            snapshot=snapshot,
        )

    def grant_owner_fund(self, *, pet_id: str, request: OwnerFundGrantRequest, now: datetime) -> EconomyResponse:
        if request.star_dust + request.project_budget + request.cosmetic_budget + request.travel_opportunity_budget <= 0:
            raise EconomyConflictError("grant amount must be positive")

        idempotency_key = f"owner_grant:{pet_id}:{request.grant_id}"
        existing_transaction = self.storage.get_transaction_by_idempotency_key(idempotency_key)
        if existing_transaction:
            return self.economy(pet_id, now=now)

        wallet_before = self.storage.get_wallet(pet_id) or self._empty_wallet(pet_id, now)
        fund_before = self.storage.get_owner_fund(pet_id) or self._empty_owner_fund(pet_id, now)
        wallet_after = wallet_before.model_copy(
            update={"star_dust": wallet_before.star_dust + request.star_dust, "updated_at": now}
        )
        fund_after = fund_before.model_copy(
            update={
                "star_dust": fund_before.star_dust + request.star_dust,
                "project_budget": fund_before.project_budget + request.project_budget,
                "cosmetic_budget": fund_before.cosmetic_budget + request.cosmetic_budget,
                "travel_opportunity_budget": fund_before.travel_opportunity_budget + request.travel_opportunity_budget,
                "updated_at": now,
            }
        )
        snapshot = self.storage.get_economy_snapshot(pet_id) or self._snapshot_from_items(
            pet_id=pet_id,
            items=self.storage.list_inventory(pet_id, status=None, limit=200),
            now=now,
        )
        transaction = self._transaction(
            pet_id=pet_id,
            type=EconomyTransactionType.owner_fund_granted,
            idempotency_key=idempotency_key,
            amounts=CurrencyAmounts(star_dust=request.star_dust),
            item_ids=[],
            before={
                "wallet_star_dust": wallet_before.star_dust,
                "owner_fund_star_dust": fund_before.star_dust,
                "project_budget": fund_before.project_budget,
                "cosmetic_budget": fund_before.cosmetic_budget,
                "travel_opportunity_budget": fund_before.travel_opportunity_budget,
            },
            after={
                "wallet_star_dust": wallet_after.star_dust,
                "owner_fund_star_dust": fund_after.star_dust,
                "project_budget": fund_after.project_budget,
                "cosmetic_budget": fund_after.cosmetic_budget,
                "travel_opportunity_budget": fund_after.travel_opportunity_budget,
            },
            reason=request.reason,
            operator="admin",
            source="owner_fund_grant",
            now=now,
        )
        self.apply_transaction(
            transaction=transaction,
            wallet=wallet_after,
            owner_fund=fund_after,
            snapshot=snapshot,
        )
        return EconomyResponse(
            wallet=wallet_after,
            owner_fund=fund_after,
            snapshot=snapshot,
            recent_transactions=self.storage.list_economy_transactions(pet_id, limit=20),
        )

    def rebuild_derived_state(self, pet_id: str, now: datetime | None = None) -> EconomyResponse:
        timestamp = now or utcnow()
        wallet = self._empty_wallet(pet_id, timestamp)
        owner_fund = self._empty_owner_fund(pet_id, timestamp)

        for transaction in self.storage.list_all_economy_transactions(pet_id):
            if transaction.status != "committed":
                continue
            wallet = wallet.model_copy(
                update={
                    "travel_coin": wallet.travel_coin + transaction.amounts.travel_coin,
                    "star_dust": wallet.star_dust + transaction.amounts.star_dust,
                    "merit": wallet.merit + transaction.amounts.merit,
                    "updated_at": timestamp,
                }
            )
            if transaction.type == EconomyTransactionType.owner_fund_granted:
                owner_fund = owner_fund.model_copy(
                    update={
                        "star_dust": owner_fund.star_dust + transaction.amounts.star_dust,
                        "project_budget": owner_fund.project_budget + self._transaction_delta(transaction, "project_budget"),
                        "cosmetic_budget": owner_fund.cosmetic_budget + self._transaction_delta(transaction, "cosmetic_budget"),
                        "travel_opportunity_budget": owner_fund.travel_opportunity_budget
                        + self._transaction_delta(transaction, "travel_opportunity_budget"),
                        "updated_at": timestamp,
                    }
                )

        snapshot = self._snapshot_from_items(
            pet_id=pet_id,
            items=self.storage.list_inventory(pet_id, status=None, limit=200),
            now=timestamp,
        )
        self.storage.save_economy_derived_state(wallet=wallet, owner_fund=owner_fund, snapshot=snapshot)
        return EconomyResponse(
            wallet=wallet,
            owner_fund=owner_fund,
            snapshot=snapshot,
            recent_transactions=self.storage.list_economy_transactions(pet_id, limit=20),
        )

    def apply_transaction(
        self,
        *,
        transaction: EconomyTransaction,
        wallet: Wallet | None = None,
        owner_fund: OwnerFund | None = None,
        snapshot: EconomySnapshot | None = None,
        souvenirs: list[SouvenirItem] | None = None,
        expected_item_versions: dict[str, int] | None = None,
    ) -> tuple[EconomyTransaction, bool]:
        existing = self.storage.get_transaction_by_idempotency_key(transaction.idempotency_key)
        if existing:
            return existing, False
        try:
            return (
                self.storage.commit_economy_state(
                    transaction=transaction,
                    wallet=wallet,
                    owner_fund=owner_fund,
                    snapshot=snapshot,
                    souvenirs=souvenirs,
                    expected_item_versions=expected_item_versions,
                ),
                True,
            )
        except sqlite3.IntegrityError:
            existing = self.storage.get_transaction_by_idempotency_key(transaction.idempotency_key)
            if existing:
                return existing, False
            raise
        except EconomyStorageConflict as exc:
            raise EconomyConflictError("item version conflict") from exc

    def _enrich_souvenir(
        self,
        *,
        pet: PetRecord,
        quest: TravelQuest,
        item: SouvenirItem,
        weather: str | None,
        now: datetime,
        index: int,
    ) -> SouvenirItem:
        template_id = item.template_id or self._template_id(item)
        item_id = self._stable_item_id(pet.pet_id, quest.id, template_id)
        source = AcquisitionSource.quest_reward
        value = self._value_for_item(pet=pet, item=item, source=source, template_id=template_id)
        stop_id = item.source_photo_mission_id or f"quest-stop-{quest.id}-{index}"
        return item.model_copy(
            update={
                "id": item_id,
                "template_id": template_id,
                "status": ItemStatus.owned,
                "version": 1,
                "trade_policy": self._trade_policy_for(item),
                "market_value": value.market_value,
                "emotional_value": value.emotional_value,
                "honor_value": value.honor_value,
                "value_breakdown": value.value_breakdown,
                "acquire_source": source,
                "origin_event_id": f"quest:{quest.id}:{template_id}",
                "origin_activity_id": stop_id,
                "origin_activity_type": "travel_quest_stop",
                "origin_poi_name": item.place_name,
                "origin_city": item.city,
                "origin_weather": weather,
                "origin_coords": [],
                "updated_at": now,
                "obtained_at": now,
            }
        )

    def _value_for_item(self, *, pet: PetRecord, item: SouvenirItem, source: AcquisitionSource, template_id: str):
        base = {
            "toy": 25,
            "cultural_creative": 28,
            "ticket_stub": 20,
            "charm": 35,
            "snack_pack": 12,
            "photo_print": 45,
            "found_object": 18,
        }.get(item.item_type.value, 18)
        rarity_multiplier = {
            "common": 1.0,
            "uncommon": 3.0,
            "rare": 10.0,
            "sr": 40.0,
            "epic": 40.0,
            "ssr": 160.0,
            "legendary": 160.0,
            "myth": 0.0,
            "mythic": 0.0,
        }.get(item.rarity.lower(), 1.0)
        source_multiplier = {
            AcquisitionSource.shop_purchase: 1.0,
            AcquisitionSource.found: 1.2,
            AcquisitionSource.activity_reward: 1.25,
            AcquisitionSource.quest_reward: 1.4,
            AcquisitionSource.npc_gift: 1.8,
            AcquisitionSource.photo_mission: 1.35,
            AcquisitionSource.event_reward: 3.0,
            AcquisitionSource.dev_grant: 0.0,
        }[source]
        condition_multiplier = self._condition_multiplier(template_id)
        story_bonus = self._story_bonus(pet=pet, item=item)
        market_value = 0 if rarity_multiplier <= 0 else max(1, int(round(base * rarity_multiplier * source_multiplier * condition_multiplier * story_bonus)))
        emotional_multiplier = 1.6 + min(rarity_multiplier, 10.0) / 10.0
        emotional_value = max(10, int(round((market_value or base) * emotional_multiplier + 24)))
        return item_value(
            market_value=market_value,
            emotional_value=emotional_value,
            honor_value=0,
            base=base,
            rarity_multiplier=rarity_multiplier,
            source_multiplier=source_multiplier,
            condition_multiplier=condition_multiplier,
            story_bonus=story_bonus,
        )

    def _snapshot_after_changes(self, pet_id: str, *, changed_items: list[SouvenirItem], now: datetime) -> EconomySnapshot:
        by_id = {item.id: item for item in self.storage.list_inventory(pet_id, status=None, limit=200)}
        for item in changed_items:
            by_id[item.id] = item
        return self._snapshot_from_items(pet_id=pet_id, items=list(by_id.values()), now=now)

    def _snapshot_from_items(self, *, pet_id: str, items: list[SouvenirItem], now: datetime) -> EconomySnapshot:
        active_items = [item for item in items if item.status not in {ItemStatus.deleted}]
        owned_items = [item for item in active_items if item.status == ItemStatus.owned]
        sellable_items = [item for item in owned_items if self._is_sellable(item, now=now)]
        return EconomySnapshot(
            pet_id=pet_id,
            total_display_value=sum(item.market_value + item.emotional_value + item.honor_value for item in owned_items),
            sellable_value=sum(item.market_value // 2 for item in sellable_items),
            collection_value=sum(item.emotional_value for item in owned_items),
            honor_value=sum(item.honor_value for item in owned_items),
            owned_item_count=len(owned_items),
            sellable_item_count=len(sellable_items),
            archived_item_count=sum(1 for item in active_items if item.status == ItemStatus.archived),
            sold_item_count=sum(1 for item in active_items if item.status == ItemStatus.sold),
            updated_at=now,
        )

    def _transaction(
        self,
        *,
        pet_id: str,
        type: EconomyTransactionType,
        idempotency_key: str,
        amounts: CurrencyAmounts,
        item_ids: list[str],
        before: dict[str, object],
        after: dict[str, object],
        reason: str,
        operator: str,
        source: str,
        now: datetime,
    ) -> EconomyTransaction:
        digest = hashlib.sha1(idempotency_key.encode("utf-8")).hexdigest()[:14].upper()
        return EconomyTransaction(
            tx_id=f"TX-{digest}",
            pet_id=pet_id,
            type=type,
            idempotency_key=idempotency_key,
            amounts=amounts,
            item_ids=item_ids,
            before=before,
            after=after,
            reason=reason,
            operator=operator,
            source=source,
            status="committed",
            created_at=now,
        )

    def _transaction_delta(self, transaction: EconomyTransaction, key: str) -> int:
        before = transaction.before.get(key, 0)
        after = transaction.after.get(key, before)
        try:
            return int(after) - int(before)
        except (TypeError, ValueError):
            return 0

    def _item_or_raise(self, pet_id: str, item_id: str) -> SouvenirItem:
        item = self.storage.get_souvenir(pet_id, item_id)
        if item is None:
            raise KeyError(item_id)
        return item

    def _empty_wallet(self, pet_id: str, now: datetime) -> Wallet:
        return Wallet(pet_id=pet_id, updated_at=now)

    def _empty_owner_fund(self, pet_id: str, now: datetime) -> OwnerFund:
        return OwnerFund(
            pet_id=pet_id,
            daily_coin_limit=self.settings.economy_daily_coin_limit,
            coin_inflow_date=now.date(),
            updated_at=now,
        )

    def _template_id(self, item: SouvenirItem) -> str:
        digest = hashlib.sha1(f"{item.item_type.value}|{item.title}".encode("utf-8")).hexdigest()[:12]
        return f"tpl_{digest}"

    def _stable_item_id(self, pet_id: str, quest_id: str, template_id: str) -> str:
        digest = hashlib.sha1(f"{pet_id}|{quest_id}|{template_id}".encode("utf-8")).hexdigest()[:10].upper()
        return f"SV-{digest}"

    def _condition_multiplier(self, template_id: str) -> float:
        digest = hashlib.sha1(template_id.encode("utf-8")).hexdigest()
        return round(0.85 + (int(digest[:2], 16) % 16) / 100, 2)

    def _story_bonus(self, *, pet: PetRecord, item: SouvenirItem) -> float:
        text = f"{item.city} {item.place_name} {item.story} {' '.join(item.bag_influence_tags)}".lower()
        bonus = 1.0
        if any(place and place.lower() in text for place in pet.dna.favorite_places):
            bonus += 0.12
        if any(tag in {"rare_photo", "souvenir", "return_home"} for tag in item.bag_influence_tags):
            bonus += 0.08
        if item.rarity.lower() != "common":
            bonus += 0.05
        return round(bonus, 2)

    def _trade_policy_for(self, item: SouvenirItem) -> TradePolicy:
        if item.rarity.lower() in {"myth", "mythic"}:
            return TradePolicy.soulbound
        return TradePolicy.tradable

    def _is_sellable(self, item: SouvenirItem, *, now: datetime) -> bool:
        if item.status != ItemStatus.owned:
            return False
        if item.trade_policy == TradePolicy.tradable:
            return True
        if item.trade_policy == TradePolicy.time_locked and item.lock_until and item.lock_until <= now:
            return True
        return False


def item_value(
    *,
    market_value: int,
    emotional_value: int,
    honor_value: int,
    base: int,
    rarity_multiplier: float,
    source_multiplier: float,
    condition_multiplier: float,
    story_bonus: float,
):
    from .schemas import ItemValue

    return ItemValue(
        market_value=market_value,
        emotional_value=emotional_value,
        honor_value=honor_value,
        value_breakdown={
            "base": base,
            "rarity_multiplier": rarity_multiplier,
            "source_multiplier": source_multiplier,
            "condition_multiplier": condition_multiplier,
            "story_bonus": story_bonus,
            "final_market_value": market_value,
        },
    )
