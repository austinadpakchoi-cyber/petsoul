"""世界事件 outbox：结算事务里登记，提交之后按下游各自投递。

- add_in：在结算的同一个写事务里，每个下游登记一行（event_id + consumer 唯一，重放不重复登记）；
- claim：短事务领取到期的行，带领取令牌和期限；同一聚合（旅程）同一下游按登记顺序，前一条没投递完，后一条不领；
- delivered / failed：只有持有当前令牌的领取者能改（过期被别人重新领取后，旧领取者的回执不生效）；
  失败按退避重试，用尽次数进入 dead_letter——运维可见，不再自动重试，也不挡同一旅程后面的事件。
投递语义是“至少一次”，下游按 source_event_id 自己去重。
"""

from __future__ import annotations

import json
import os
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..utils import iso, parse_dt

RETRY_SECONDS = (30, 120, 600, 1800)
MAX_ATTEMPTS = 5
CLAIM_SECONDS = 120


@dataclass(frozen=True, slots=True)
class OutboxItem:
    seq: int
    event_id: str
    consumer: str
    aggregate_id: str
    kind: str
    effective_at: datetime
    payload: dict
    attempts: int
    claim_token: str


class Outbox:
    def __init__(self, storage) -> None:
        self.storage = storage
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}"

    def add_in(self, conn, *, event_id: str, aggregate_id: str, kind: str, effective_at: datetime, payload: dict,
               consumers: list[str], now: datetime) -> int:
        """在调用者的写事务里为每个下游登记一行；返回新登记的行数。"""
        added = 0
        for consumer in consumers:
            added += conn.execute(
                "INSERT OR IGNORE INTO web_outbox (event_id, consumer, aggregate_id, kind, effective_at, payload_json, status, attempts, "
                "next_attempt_at, created_at) VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?)",
                (event_id, consumer, aggregate_id, kind, iso(effective_at), json.dumps(payload, ensure_ascii=False, default=str), iso(now), iso(now)),
            ).rowcount
        return added

    def claim(self, consumers: list[str], now: datetime, *, limit: int = 50, aggregate_id: str | None = None) -> list[OutboxItem]:
        if not consumers:
            return []
        token = f"{self.worker_id}:{uuid.uuid4().hex[:10]}"
        marks = ",".join("?" for _ in consumers)
        scope = "AND o.aggregate_id = ? " if aggregate_id else ""
        params = [*consumers, iso(now), iso(now), *([aggregate_id] if aggregate_id else []), limit]
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                f"SELECT * FROM web_outbox o WHERE o.status = 'pending' AND o.consumer IN ({marks}) AND o.next_attempt_at <= ? "
                f"AND (o.claimed_until IS NULL OR o.claimed_until <= ?) {scope}"
                "AND NOT EXISTS (SELECT 1 FROM web_outbox p WHERE p.aggregate_id = o.aggregate_id AND p.consumer = o.consumer "
                "AND p.seq < o.seq AND p.status = 'pending') ORDER BY o.seq LIMIT ?",
                params,
            ).fetchall()
            until = iso(now + timedelta(seconds=CLAIM_SECONDS))
            for row in rows:
                conn.execute("UPDATE web_outbox SET claimed_by = ?, claimed_until = ? WHERE seq = ?", (token, until, row["seq"]))
        return [OutboxItem(row["seq"], row["event_id"], row["consumer"], row["aggregate_id"], row["kind"], parse_dt(row["effective_at"]),
                           json.loads(row["payload_json"] or "{}"), row["attempts"], token) for row in rows]

    def delivered(self, item: OutboxItem, now: datetime) -> bool:
        with self.storage.connect() as conn:
            return conn.execute(
                "UPDATE web_outbox SET status = 'delivered', delivered_at = ?, claimed_by = NULL, claimed_until = NULL, last_error = NULL "
                "WHERE seq = ? AND status = 'pending' AND claimed_by = ?",
                (iso(now), item.seq, item.claim_token),
            ).rowcount == 1

    def failed(self, item: OutboxItem, error: str, now: datetime) -> str:
        attempts = item.attempts + 1
        status = "dead_letter" if attempts >= MAX_ATTEMPTS else "pending"
        retry_at = now + timedelta(seconds=RETRY_SECONDS[min(attempts, len(RETRY_SECONDS)) - 1])
        with self.storage.connect() as conn:
            conn.execute(
                "UPDATE web_outbox SET attempts = ?, status = ?, next_attempt_at = ?, last_error = ?, claimed_by = NULL, claimed_until = NULL "
                "WHERE seq = ? AND status = 'pending' AND claimed_by = ?",
                (attempts, status, iso(retry_at), error[:300], item.seq, item.claim_token),
            )
        return status

    def prune_delivered(self, now: datetime, *, keep_days: int = 14, limit: int = 500) -> int:
        """清掉早就投递完的回执（保留最近两周，够运维追查；dead_letter 与待投递不动）。"""
        cutoff = iso(now - timedelta(days=keep_days))
        with self.storage.connect() as conn:
            return conn.execute("DELETE FROM web_outbox WHERE seq IN (SELECT seq FROM web_outbox WHERE status = 'delivered' AND delivered_at < ? LIMIT ?)",
                                (cutoff, limit)).rowcount

    def stats(self, now: datetime) -> dict:
        """各下游 pending / delivered / dead_letter 数量与最老一条待投递的等待秒数（运维用）。"""
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT consumer, status, COUNT(*) AS n, MIN(created_at) AS oldest FROM web_outbox GROUP BY consumer, status").fetchall()
        stats: dict = {}
        for row in rows:
            entry = stats.setdefault(row["consumer"], {"pending": 0, "delivered": 0, "dead_letter": 0, "oldest_pending_seconds": None})
            entry[row["status"]] = row["n"]
            if row["status"] == "pending" and row["oldest"]:
                entry["oldest_pending_seconds"] = max(0, int((now - parse_dt(row["oldest"])).total_seconds()))
        return stats
