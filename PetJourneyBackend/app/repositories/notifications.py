"""通知聚合 Repository mixin：设备 token 与推送投递记录。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from ..utils import iso, parse_dt, utcnow


class NotificationRepositoryMixin:
    def upsert_device_token(self, pet_id: str, device_token: str, platform: str, environment: str) -> dict[str, Any]:
        now = utcnow()
        device_id = str(uuid.uuid4())
        with self.connect() as conn:
            existing = conn.execute(
                """
                SELECT id FROM device_tokens
                WHERE device_token = ? AND platform = ? AND environment = ?
                """,
                (device_token, platform, environment),
            ).fetchone()
            if existing:
                device_id = existing["id"]
                conn.execute(
                    """
                    UPDATE device_tokens
                    SET pet_id = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (pet_id, iso(now), device_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO device_tokens (
                        id, pet_id, device_token, platform, environment, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (device_id, pet_id, device_token, platform, environment, iso(now), iso(now)),
                )
        return {
            "id": device_id,
            "pet_id": pet_id,
            "device_token": device_token,
            "platform": platform,
            "environment": environment,
            "created_at": now,
            "updated_at": now,
        }

    def remove_device_token(self, device_token: str, platform: str = "ios") -> None:
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM device_tokens WHERE device_token = ? AND platform = ?",
                (device_token, platform),
            )

    def list_device_tokens(self, pet_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM device_tokens WHERE pet_id = ? ORDER BY updated_at DESC",
                (pet_id,),
            ).fetchall()
        return [self._device_token_from_row(row) for row in rows]

    def record_notification_delivery(
        self,
        *,
        pet_id: str,
        device_token: str | None,
        title: str,
        body: str,
        category: str,
        provider: str,
        status: str,
        error: str | None = None,
        timestamp: datetime | None = None,
    ) -> dict[str, Any]:
        item = {
            "id": str(uuid.uuid4()),
            "pet_id": pet_id,
            "device_token": device_token,
            "title": title,
            "body": body,
            "category": category,
            "provider": provider,
            "status": status,
            "timestamp": timestamp or utcnow(),
            "error": error,
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO notification_deliveries (
                    id, pet_id, device_token, title, body, category, provider, status, timestamp, error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["id"],
                    pet_id,
                    device_token,
                    title,
                    body,
                    category,
                    provider,
                    status,
                    iso(item["timestamp"]),
                    error,
                ),
            )
        return item

    def list_notification_deliveries(self, pet_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM notification_deliveries
                WHERE pet_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (pet_id, limit),
            ).fetchall()
        return [self._notification_from_row(row) for row in rows]

    def _device_token_from_row(self, row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "pet_id": row["pet_id"],
            "device_token": row["device_token"],
            "platform": row["platform"],
            "environment": row["environment"],
            "created_at": parse_dt(row["created_at"]),
            "updated_at": parse_dt(row["updated_at"]),
        }

    def _notification_from_row(self, row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "pet_id": row["pet_id"],
            "device_token": row["device_token"],
            "title": row["title"],
            "body": row["body"],
            "category": row["category"],
            "provider": row["provider"],
            "status": row["status"],
            "timestamp": parse_dt(row["timestamp"]),
            "error": row["error"],
        }
