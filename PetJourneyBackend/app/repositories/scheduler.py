"""调度器状态 Repository mixin：scheduler_state 键值存储。"""

from __future__ import annotations

from datetime import datetime

from ..utils import iso, utcnow


class SchedulerRepositoryMixin:
    def set_scheduler_state(self, key: str, value: str, timestamp: datetime | None = None) -> None:
        now = timestamp or utcnow()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO scheduler_state (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, value, iso(now)),
            )

    def get_scheduler_state(self, key: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM scheduler_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None
