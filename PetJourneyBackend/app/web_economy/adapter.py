"""EconomyAdapter：网页所有游戏币进出都写进既有的同一本账（economy_transactions + pet_wallets.travel_coin，
与 PetEconomyEngine 共用存储层的写法）。不存在第二份可独立写入的家园余额。

并发：读余额、检查、写账本与改余额在同一个 SQLite 写事务（BEGIN IMMEDIATE）里完成——
API 进程与独立任务进程同时记账也不会丢失更新、不会扣成负数；幂等键在事务内先查、再由账本表唯一约束兜底。
apply_in 让上层的 UnitOfWork 复用同一个事务：到期结算时工资与世界事件、outbox 一起提交或一起回滚。
"""

from __future__ import annotations

import hashlib
import threading
from datetime import datetime

from ..economy_engine import PetEconomyEngine
from ..schemas import CurrencyAmounts, EconomyTransaction, EconomyTransactionType, Wallet
from ..schemas.web.home import WalletSummary
from ..storage import JourneyStorage
from ..utils import utcnow


class InsufficientFunds(Exception):
    def __init__(self, balance: int, needed: int) -> None:
        super().__init__(f"balance {balance} < {needed}")
        self.balance = balance
        self.needed = needed


class WebEconomy:
    _lock = threading.Lock()

    def __init__(self, storage: JourneyStorage, engine: PetEconomyEngine) -> None:
        self.storage = storage
        self.engine = engine

    def wallet(self, pet_id: str) -> WalletSummary:
        wallet = self.storage.get_wallet(pet_id)
        return WalletSummary(currency="travel_coin", balance=wallet.travel_coin if wallet else 0, updated_at=wallet.updated_at if wallet else None)

    def apply(
        self,
        pet_id: str,
        delta: int,
        kind: EconomyTransactionType,
        idempotency_key: str,
        reason: str,
        source: str,
        operator: str = "web",
        now: datetime | None = None,
    ) -> tuple[WalletSummary, bool]:
        """delta>0 入账，<0 扣款；同一幂等键只生效一次。自己开一个写事务。返回 (钱包, 是否新生效)。"""
        now = now or utcnow()
        with self._lock, self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            applied = self.apply_in(conn, pet_id, delta, kind, idempotency_key, reason, source, operator, now)
        return self.wallet(pet_id), applied

    def apply_in(
        self,
        conn,
        pet_id: str,
        delta: int,
        kind: EconomyTransactionType,
        idempotency_key: str,
        reason: str,
        source: str,
        operator: str = "web",
        now: datetime | None = None,
    ) -> bool:
        """在调用者的写事务（UnitOfWork）里记账：不另开连接、不提交也不回滚，也不拿进程锁（写锁已由调用者的事务持有）。

        同一幂等键已经记过就什么也不改、返回 False；余额不够抛 InsufficientFunds，由调用者整体回滚。
        """
        now = now or utcnow()
        if conn.execute("SELECT 1 FROM economy_transactions WHERE idempotency_key = ?", (idempotency_key,)).fetchone():
            return False
        row = conn.execute("SELECT * FROM pet_wallets WHERE pet_id = ?", (pet_id,)).fetchone()
        before = self.storage._wallet_from_row(row) if row else Wallet(pet_id=pet_id, updated_at=now)
        if delta < 0 and before.travel_coin + delta < 0:
            raise InsufficientFunds(before.travel_coin, -delta)
        after = before.model_copy(update={"travel_coin": before.travel_coin + delta, "updated_at": now})
        digest = hashlib.sha1(idempotency_key.encode("utf-8")).hexdigest()[:14].upper()
        transaction = EconomyTransaction(
            tx_id=f"TX-{digest}",
            pet_id=pet_id,
            type=kind,
            idempotency_key=idempotency_key,
            amounts=CurrencyAmounts(travel_coin=delta),
            item_ids=[],
            before={"travel_coin": before.travel_coin},
            after={"travel_coin": after.travel_coin},
            reason=reason,
            operator=operator,
            source=source,
            status="committed",
            created_at=now,
        )
        self.storage._insert_economy_transaction(conn, transaction)
        self.storage._upsert_wallet(conn, after)
        return True
