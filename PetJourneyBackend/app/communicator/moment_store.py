from __future__ import annotations

from datetime import datetime
import json
import uuid

from ..storage import JourneyStorage, iso, parse_dt, utcnow
from .schemas import CommunicatorMoment, MomentReaction, MomentSourceType


class CommunicatorMomentStore:
    provider_name = "sqlite-communicator-moment-store"

    def __init__(self, storage: JourneyStorage):
        self.storage = storage

    def add_moment(self, moment: CommunicatorMoment, scene_hash: str | None = None) -> CommunicatorMoment:
        payload = moment.model_dump(mode="json")
        attachments = [item.model_dump(mode="json") for item in moment.attachments]
        location = moment.location
        with self.storage.connect() as conn:
            conn.execute(
                """
                INSERT INTO communicator_moments (
                    id, pet_id, source_type, source_event_id, text, city, place_name,
                    lat, lng, mood, scene_hash, attachments_json, reactions_json,
                    owner_reaction, is_read, payload_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    text = excluded.text,
                    attachments_json = excluded.attachments_json,
                    reactions_json = excluded.reactions_json,
                    owner_reaction = excluded.owner_reaction,
                    is_read = excluded.is_read,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    moment.id,
                    moment.pet_id,
                    moment.source_type.value,
                    moment.source_event_id,
                    moment.text,
                    location.city if location else None,
                    location.place_name if location else None,
                    location.lat if location else None,
                    location.lng if location else None,
                    moment.mood,
                    scene_hash,
                    json.dumps(attachments, ensure_ascii=False),
                    json.dumps(moment.reactions, ensure_ascii=False),
                    moment.owner_reaction.value if moment.owner_reaction else None,
                    1 if moment.is_read else 0,
                    json.dumps(payload, ensure_ascii=False),
                    iso(moment.created_at),
                    iso(moment.updated_at) if moment.updated_at else None,
                ),
            )
        return moment

    def list_moments(self, pet_id: str, limit: int = 50) -> list[CommunicatorMoment]:
        with self.storage.connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM communicator_moments
                WHERE pet_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (pet_id, max(1, min(100, limit))),
            ).fetchall()
        return [CommunicatorMoment.model_validate(json.loads(row["payload_json"])) for row in rows]

    def get_moment(self, pet_id: str, moment_id: str) -> CommunicatorMoment | None:
        with self.storage.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM communicator_moments WHERE pet_id = ? AND id = ?",
                (pet_id, moment_id),
            ).fetchone()
        return CommunicatorMoment.model_validate(json.loads(row["payload_json"])) if row else None

    def latest_moment_at(self, pet_id: str, scene_hash: str | None = None, photo_only: bool = False) -> datetime | None:
        query = "SELECT created_at FROM communicator_moments WHERE pet_id = ?"
        params: list[object] = [pet_id]
        if scene_hash:
            query += " AND scene_hash = ?"
            params.append(scene_hash)
        if photo_only:
            query += " AND attachments_json LIKE ?"
            params.append("%photo_%")
        query += " ORDER BY created_at DESC LIMIT 1"
        with self.storage.connect() as conn:
            row = conn.execute(query, tuple(params)).fetchone()
        return parse_dt(row["created_at"]) if row else None

    def count_moments_since(self, pet_id: str, since: datetime, photo_only: bool = False) -> int:
        query = "SELECT COUNT(*) AS count FROM communicator_moments WHERE pet_id = ? AND created_at >= ?"
        params: list[object] = [pet_id, iso(since)]
        if photo_only:
            query += " AND attachments_json LIKE ?"
            params.append("%photo_%")
        with self.storage.connect() as conn:
            row = conn.execute(query, tuple(params)).fetchone()
        return int(row["count"])

    def upsert_reaction(self, *, pet_id: str, moment_id: str, reaction: MomentReaction) -> CommunicatorMoment:
        now = utcnow()
        moment = self.get_moment(pet_id, moment_id)
        if moment is None:
            raise KeyError(moment_id)
        previous = moment.owner_reaction
        counts = dict(moment.reactions)
        if previous:
            counts[previous.value] = max(0, counts.get(previous.value, 0) - 1)
        counts[reaction.value] = counts.get(reaction.value, 0) + 1
        updated = moment.model_copy(update={
            "reactions": counts,
            "owner_reaction": reaction,
            "updated_at": now,
        })
        with self.storage.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM communicator_moment_reactions WHERE moment_id = ? AND pet_id = ?",
                (moment_id, pet_id),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE communicator_moment_reactions
                    SET reaction = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (reaction.value, iso(now), existing["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO communicator_moment_reactions (id, moment_id, pet_id, reaction, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (f"reaction_{uuid.uuid4().hex}", moment_id, pet_id, reaction.value, iso(now), iso(now)),
                )
        self.add_moment(updated)
        return updated


def new_moment_id(source_type: MomentSourceType) -> str:
    return f"moment_{source_type.value}_{uuid.uuid4().hex[:12]}"
