"""驾考消息发件箱：消息与状态变更在同一事务写入，提交后再投递（独立核查 P1 修复）。

- 投递失败（通讯器暂时不可用等）不影响考试结果与驾驶资格；消息留在发件箱，世界定时器下一轮按去重键重试；
- 通讯器按去重键写入（INSERT OR IGNORE），同一条消息重复投递也只出现一次；
- 消息时间用事件发生的时间，不因为补投而变成“现在”。
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from typing import Callable

from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 100  # 连续失败这么多次后不再自动重试（留在表里供排查）


class DrivingNotes:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage
        self.say: Callable[[str, str, str, str, datetime], None] = lambda user_id, pet_id, text, key, at: None

    @staticmethod
    def queue(conn: sqlite3.Connection, user_id: str, pet_id: str, key: str, text: str, at: datetime) -> None:
        """在调用方的事务里登记一条要发的消息（同一去重键只登记一次）。"""
        conn.execute("INSERT OR IGNORE INTO web_driving_notes (dedupe_key, user_id, pet_id, text, created_at) VALUES (?, ?, ?, ?, ?)",
                     (key, user_id, pet_id, text, iso(at)))

    def deliver(self, pet_id: str | None = None, limit: int = 50) -> int:
        """投递还没送达的消息；返回这次送达的条数。任何一条失败都只记下原因，不抛出。"""
        where = "delivered_at IS NULL AND attempts < ?" + (" AND pet_id = ?" if pet_id else "")
        params: tuple = (MAX_ATTEMPTS, pet_id) if pet_id else (MAX_ATTEMPTS,)
        with self.storage.connect() as conn:
            rows = conn.execute(f"SELECT * FROM web_driving_notes WHERE {where} ORDER BY created_at, rowid LIMIT ?", params + (limit,)).fetchall()
        sent = 0
        for row in rows:
            try:
                self.say(row["user_id"], row["pet_id"], row["text"], row["dedupe_key"], parse_dt(row["created_at"]))
            except Exception as exc:  # noqa: BLE001 - 消息失败不影响资格，下一轮再试
                logger.warning("driving note delivery failed key=%s: %s", row["dedupe_key"], type(exc).__name__)
                with self.storage.connect() as conn:
                    conn.execute("UPDATE web_driving_notes SET attempts = attempts + 1, last_error = ? WHERE dedupe_key = ?", (type(exc).__name__, row["dedupe_key"]))
                continue
            with self.storage.connect() as conn:
                conn.execute("UPDATE web_driving_notes SET delivered_at = ?, attempts = attempts + 1 WHERE dedupe_key = ?", (iso(utcnow()), row["dedupe_key"]))
            sent += 1
        return sent

    def pending(self, pet_id: str) -> int:
        with self.storage.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM web_driving_notes WHERE pet_id = ? AND delivered_at IS NULL", (pet_id,)).fetchone()[0]
