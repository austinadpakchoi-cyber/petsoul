"""经济聚合 Repository mixin：钱包 / 主人资金 / 经济快照 / 交易，及 souvenirs 底层写辅助。

`souvenirs` 的乐观锁写路径（_upsert_souvenir / _update_souvenir_with_version）在此，
travel mixin 的 `save_souvenirs` 复用之。
"""

from __future__ import annotations

from datetime import datetime
import json
import sqlite3
from typing import Any

from ..schemas import (
    CurrencyAmounts,
    EconomySnapshot,
    EconomyTransaction,
    EconomyTransactionType,
    OwnerFund,
    SouvenirItem,
    Wallet,
)
from ..utils import iso, parse_dt, utcnow
from .records import EconomyStorageConflict


class EconomyRepositoryMixin:
    def get_wallet(self, pet_id: str) -> Wallet | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM pet_wallets WHERE pet_id = ?", (pet_id,)).fetchone()
        return self._wallet_from_row(row) if row else None

    def ensure_wallet(self, pet_id: str, now: datetime | None = None) -> Wallet:
        timestamp = now or utcnow()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM pet_wallets WHERE pet_id = ?", (pet_id,)).fetchone()
            if not row:
                wallet = Wallet(pet_id=pet_id, updated_at=timestamp)
                self._upsert_wallet(conn, wallet)
                return wallet
        return self._wallet_from_row(row)

    def get_owner_fund(self, pet_id: str) -> OwnerFund | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM owner_funds WHERE pet_id = ?", (pet_id,)).fetchone()
        return self._owner_fund_from_row(row) if row else None

    def ensure_owner_fund(self, pet_id: str, daily_coin_limit: int = 300, now: datetime | None = None) -> OwnerFund:
        timestamp = now or utcnow()
        today = timestamp.date()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM owner_funds WHERE pet_id = ?", (pet_id,)).fetchone()
            if not row:
                fund = OwnerFund(
                    pet_id=pet_id,
                    daily_coin_limit=daily_coin_limit,
                    coin_inflow_date=today,
                    updated_at=timestamp,
                )
                self._upsert_owner_fund(conn, fund)
                return fund
        return self._owner_fund_from_row(row)

    def get_economy_snapshot(self, pet_id: str) -> EconomySnapshot | None:
        with self.connect() as conn:
            row = conn.execute("SELECT payload_json FROM economy_snapshots WHERE pet_id = ?", (pet_id,)).fetchone()
        return EconomySnapshot.model_validate(json.loads(row["payload_json"])) if row else None

    def save_economy_snapshot(self, snapshot: EconomySnapshot) -> EconomySnapshot:
        with self.connect() as conn:
            self._upsert_economy_snapshot(conn, snapshot)
        return snapshot

    def get_transaction_by_idempotency_key(self, idempotency_key: str) -> EconomyTransaction | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM economy_transactions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        return self._economy_transaction_from_row(row) if row else None

    def list_economy_transactions(self, pet_id: str, limit: int = 20) -> list[EconomyTransaction]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM economy_transactions
                WHERE pet_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (pet_id, max(1, min(100, limit))),
            ).fetchall()
        return [self._economy_transaction_from_row(row) for row in rows]

    def list_all_economy_transactions(self, pet_id: str) -> list[EconomyTransaction]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM economy_transactions
                WHERE pet_id = ?
                ORDER BY created_at ASC, tx_id ASC
                """,
                (pet_id,),
            ).fetchall()
        return [self._economy_transaction_from_row(row) for row in rows]

    def save_economy_derived_state(
        self,
        *,
        wallet: Wallet,
        owner_fund: OwnerFund,
        snapshot: EconomySnapshot,
    ) -> None:
        with self.connect() as conn:
            self._upsert_wallet(conn, wallet)
            self._upsert_owner_fund(conn, owner_fund)
            self._upsert_economy_snapshot(conn, snapshot)

    def clear_economy_derived_state(self, pet_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM pet_wallets WHERE pet_id = ?", (pet_id,))
            conn.execute("DELETE FROM owner_funds WHERE pet_id = ?", (pet_id,))
            conn.execute("DELETE FROM economy_snapshots WHERE pet_id = ?", (pet_id,))

    def commit_economy_state(
        self,
        *,
        transaction: EconomyTransaction,
        wallet: Wallet | None = None,
        owner_fund: OwnerFund | None = None,
        snapshot: EconomySnapshot | None = None,
        souvenirs: list[SouvenirItem] | None = None,
        expected_item_versions: dict[str, int] | None = None,
    ) -> EconomyTransaction:
        with self.connect() as conn:
            self._insert_economy_transaction(conn, transaction)
            if wallet is not None:
                self._upsert_wallet(conn, wallet)
            if owner_fund is not None:
                self._upsert_owner_fund(conn, owner_fund)
            for item in souvenirs or []:
                expected_version = (expected_item_versions or {}).get(item.id)
                if expected_version is None:
                    self._upsert_souvenir(conn, item)
                else:
                    self._update_souvenir_with_version(conn, item, expected_version=expected_version)
            if snapshot is not None:
                self._upsert_economy_snapshot(conn, snapshot)
        return transaction

    def _upsert_souvenir(self, conn: sqlite3.Connection, item: SouvenirItem) -> None:
        payload = item.model_dump(mode="json", by_alias=True)
        updated_at = item.updated_at or item.obtained_at
        conn.execute(
            """
            INSERT INTO souvenirs (
                id, pet_id, quest_id, item_type, city, place_name, payload_json, obtained_at,
                status, trade_policy, market_value, emotional_value, honor_value,
                lock_until, version, updated_at, origin_event_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                item_type = excluded.item_type,
                city = excluded.city,
                place_name = excluded.place_name,
                payload_json = excluded.payload_json,
                obtained_at = excluded.obtained_at,
                status = excluded.status,
                trade_policy = excluded.trade_policy,
                market_value = excluded.market_value,
                emotional_value = excluded.emotional_value,
                honor_value = excluded.honor_value,
                lock_until = excluded.lock_until,
                version = excluded.version,
                updated_at = excluded.updated_at,
                origin_event_id = excluded.origin_event_id
            """,
            self._souvenir_sql_values(item, payload=payload, updated_at=updated_at),
        )

    def _update_souvenir_with_version(self, conn: sqlite3.Connection, item: SouvenirItem, expected_version: int) -> None:
        payload = item.model_dump(mode="json", by_alias=True)
        updated_at = item.updated_at or utcnow()
        cursor = conn.execute(
            """
            UPDATE souvenirs
            SET item_type = ?,
                city = ?,
                place_name = ?,
                payload_json = ?,
                obtained_at = ?,
                status = ?,
                trade_policy = ?,
                market_value = ?,
                emotional_value = ?,
                honor_value = ?,
                lock_until = ?,
                version = ?,
                updated_at = ?,
                origin_event_id = ?
            WHERE id = ? AND pet_id = ? AND version = ?
            """,
            (
                item.item_type.value,
                item.city,
                item.place_name,
                json.dumps(payload, ensure_ascii=False),
                iso(item.obtained_at),
                item.status.value,
                item.trade_policy.value,
                item.market_value,
                item.emotional_value,
                item.honor_value,
                iso(item.lock_until) if item.lock_until else None,
                item.version,
                iso(updated_at),
                item.origin_event_id,
                item.id,
                item.pet_id,
                expected_version,
            ),
        )
        if cursor.rowcount != 1:
            raise EconomyStorageConflict(item.id)

    def _souvenir_sql_values(self, item: SouvenirItem, *, payload: dict[str, Any], updated_at: datetime) -> tuple[Any, ...]:
        return (
            item.id,
            item.pet_id,
            item.quest_id,
            item.item_type.value,
            item.city,
            item.place_name,
            json.dumps(payload, ensure_ascii=False),
            iso(item.obtained_at),
            item.status.value,
            item.trade_policy.value,
            item.market_value,
            item.emotional_value,
            item.honor_value,
            iso(item.lock_until) if item.lock_until else None,
            item.version,
            iso(updated_at),
            item.origin_event_id,
        )

    def _upsert_wallet(self, conn: sqlite3.Connection, wallet: Wallet) -> None:
        conn.execute(
            """
            INSERT INTO pet_wallets (pet_id, travel_coin, star_dust, merit, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(pet_id) DO UPDATE SET
                travel_coin = excluded.travel_coin,
                star_dust = excluded.star_dust,
                merit = excluded.merit,
                updated_at = excluded.updated_at
            """,
            (wallet.pet_id, wallet.travel_coin, wallet.star_dust, wallet.merit, iso(wallet.updated_at)),
        )

    def _upsert_owner_fund(self, conn: sqlite3.Connection, fund: OwnerFund) -> None:
        conn.execute(
            """
            INSERT INTO owner_funds (
                pet_id, star_dust, project_budget, cosmetic_budget, travel_opportunity_budget,
                daily_coin_limit, coin_inflow_today, coin_inflow_date, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(pet_id) DO UPDATE SET
                star_dust = excluded.star_dust,
                project_budget = excluded.project_budget,
                cosmetic_budget = excluded.cosmetic_budget,
                travel_opportunity_budget = excluded.travel_opportunity_budget,
                daily_coin_limit = excluded.daily_coin_limit,
                coin_inflow_today = excluded.coin_inflow_today,
                coin_inflow_date = excluded.coin_inflow_date,
                updated_at = excluded.updated_at
            """,
            (
                fund.pet_id,
                fund.star_dust,
                fund.project_budget,
                fund.cosmetic_budget,
                fund.travel_opportunity_budget,
                fund.daily_coin_limit,
                fund.coin_inflow_today,
                fund.coin_inflow_date.isoformat(),
                iso(fund.updated_at),
            ),
        )

    def _upsert_economy_snapshot(self, conn: sqlite3.Connection, snapshot: EconomySnapshot) -> None:
        payload = snapshot.model_dump(mode="json", by_alias=True)
        conn.execute(
            """
            INSERT INTO economy_snapshots (pet_id, payload_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(pet_id) DO UPDATE SET
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (snapshot.pet_id, json.dumps(payload, ensure_ascii=False), iso(snapshot.updated_at)),
        )

    def _insert_economy_transaction(self, conn: sqlite3.Connection, transaction: EconomyTransaction) -> None:
        payload = transaction.model_dump(mode="json", by_alias=True)
        conn.execute(
            """
            INSERT INTO economy_transactions (
                tx_id, pet_id, type, idempotency_key, amounts_json, item_ids_json,
                before_json, after_json, reason, operator, source, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transaction.tx_id,
                transaction.pet_id,
                transaction.type.value,
                transaction.idempotency_key,
                json.dumps(payload["amounts"], ensure_ascii=False),
                json.dumps(payload["item_ids"], ensure_ascii=False),
                json.dumps(payload["before"], ensure_ascii=False),
                json.dumps(payload["after"], ensure_ascii=False),
                transaction.reason,
                transaction.operator,
                transaction.source,
                transaction.status,
                iso(transaction.created_at),
            ),
        )

    def _wallet_from_row(self, row: sqlite3.Row) -> Wallet:
        return Wallet(
            pet_id=row["pet_id"],
            travel_coin=int(row["travel_coin"]),
            star_dust=int(row["star_dust"]),
            merit=int(row["merit"]),
            updated_at=parse_dt(row["updated_at"]),
        )

    def _owner_fund_from_row(self, row: sqlite3.Row) -> OwnerFund:
        return OwnerFund(
            pet_id=row["pet_id"],
            star_dust=int(row["star_dust"]),
            project_budget=int(row["project_budget"]),
            cosmetic_budget=int(row["cosmetic_budget"]),
            travel_opportunity_budget=int(row["travel_opportunity_budget"]),
            daily_coin_limit=int(row["daily_coin_limit"]),
            coin_inflow_today=int(row["coin_inflow_today"]),
            coin_inflow_date=datetime.fromisoformat(row["coin_inflow_date"]).date(),
            updated_at=parse_dt(row["updated_at"]),
        )

    def _economy_transaction_from_row(self, row: sqlite3.Row) -> EconomyTransaction:
        return EconomyTransaction(
            tx_id=row["tx_id"],
            pet_id=row["pet_id"],
            type=EconomyTransactionType(row["type"]),
            idempotency_key=row["idempotency_key"],
            amounts=CurrencyAmounts.model_validate(json.loads(row["amounts_json"] or "{}")),
            item_ids=list(json.loads(row["item_ids_json"] or "[]")),
            before=json.loads(row["before_json"] or "{}"),
            after=json.loads(row["after_json"] or "{}"),
            reason=row["reason"],
            operator=row["operator"],
            source=row["source"],
            status=row["status"],
            created_at=parse_dt(row["created_at"]),
        )
