from __future__ import annotations

from datetime import datetime
import json
import uuid

from ..storage import JourneyStorage, iso, parse_dt, utcnow
from .schemas import (
    CommunicatorIntent,
    CommunicatorMessage,
    MessageSender,
    PendingPhotoRequest,
    PendingStatus,
)


class CommunicatorMessageStore:
    provider_name = "sqlite-communicator-message-store"

    def __init__(self, storage: JourneyStorage):
        self.storage = storage

    def add_message(self, message: CommunicatorMessage) -> CommunicatorMessage:
        payload = message.model_dump(mode="json")
        with self.storage.connect() as conn:
            conn.execute(
                """
                INSERT INTO communicator_messages (
                    id, pet_id, sender, intent, message_state, text,
                    related_message_id, payload_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.id,
                    message.pet_id,
                    message.sender.value,
                    message.intent.value if message.intent else None,
                    str(message.message_state.value),
                    message.text,
                    message.related_message_id,
                    json.dumps(payload, ensure_ascii=False),
                    iso(message.created_at),
                    iso(message.updated_at) if message.updated_at else None,
                ),
            )
        return message

    def update_message(self, message: CommunicatorMessage) -> CommunicatorMessage:
        payload = message.model_dump(mode="json")
        with self.storage.connect() as conn:
            conn.execute(
                """
                UPDATE communicator_messages
                SET message_state = ?, text = ?, payload_json = ?, updated_at = ?
                WHERE id = ? AND pet_id = ?
                """,
                (
                    str(message.message_state.value),
                    message.text,
                    json.dumps(payload, ensure_ascii=False),
                    iso(message.updated_at or utcnow()),
                    message.id,
                    message.pet_id,
                ),
            )
        return message

    def list_messages(self, pet_id: str, limit: int = 80) -> list[CommunicatorMessage]:
        with self.storage.connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM communicator_messages
                WHERE pet_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (pet_id, max(1, min(200, limit))),
            ).fetchall()
        return [CommunicatorMessage.model_validate(json.loads(row["payload_json"])) for row in reversed(rows)]

    def add_pending(self, pending: PendingPhotoRequest) -> PendingPhotoRequest:
        payload = pending.model_dump(mode="json")
        with self.storage.connect() as conn:
            conn.execute(
                """
                INSERT INTO communicator_pending_requests (
                    id, pet_id, source_message_id, intent, pending_type, status,
                    scene_hash, payload_json, available_after, expires_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pending.id,
                    pending.pet_id,
                    pending.source_message_id,
                    pending.intent.value,
                    pending.pending_type.value,
                    pending.status.value,
                    pending.scene_hash,
                    json.dumps(payload, ensure_ascii=False),
                    iso(pending.available_after),
                    iso(pending.expires_at),
                    iso(pending.created_at),
                    None,
                ),
            )
        return pending

    def update_pending(self, pending: PendingPhotoRequest) -> PendingPhotoRequest:
        payload = pending.model_dump(mode="json")
        with self.storage.connect() as conn:
            conn.execute(
                """
                UPDATE communicator_pending_requests
                SET status = ?, payload_json = ?, updated_at = ?
                WHERE id = ? AND pet_id = ?
                """,
                (
                    pending.status.value,
                    json.dumps(payload, ensure_ascii=False),
                    iso(utcnow()),
                    pending.id,
                    pending.pet_id,
                ),
            )
        return pending

    def list_due_pending(self, pet_id: str, now: datetime) -> list[PendingPhotoRequest]:
        with self.storage.connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM communicator_pending_requests
                WHERE pet_id = ? AND status = ? AND available_after <= ?
                ORDER BY available_after ASC
                LIMIT 20
                """,
                (pet_id, PendingStatus.pending.value, iso(now)),
            ).fetchall()
        return [PendingPhotoRequest.model_validate(json.loads(row["payload_json"])) for row in rows]

    def latest_photo_request_at(self, pet_id: str, scene_hash: str | None = None) -> datetime | None:
        query = """
            SELECT created_at FROM communicator_messages
            WHERE pet_id = ?
              AND sender = ?
              AND intent IN (?, ?)
        """
        params: list[object] = [
            pet_id,
            MessageSender.owner.value,
            CommunicatorIntent.current_status_visual_request.value,
            CommunicatorIntent.photo_request.value,
        ]
        if scene_hash:
            query += " AND payload_json LIKE ?"
            params.append(f"%{scene_hash}%")
        query += " ORDER BY created_at DESC LIMIT 1"
        with self.storage.connect() as conn:
            row = conn.execute(query, tuple(params)).fetchone()
        return parse_dt(row["created_at"]) if row else None


def new_message_id() -> str:
    return f"msg_{uuid.uuid4().hex}"


def new_pending_id() -> str:
    return f"pending_{uuid.uuid4().hex}"

