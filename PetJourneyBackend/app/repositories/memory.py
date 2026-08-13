"""记忆聚合 Repository mixin：memories 表 CRUD 与 touch。"""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any
import uuid

from ..utils import iso, parse_dt, utcnow


class MemoryRepositoryMixin:
    def add_memory(
        self,
        *,
        pet_id: str,
        kind: str,
        title: str,
        content: str,
        salience: float,
        source: str,
        embedding: list[float],
        metadata: dict[str, Any] | None = None,
        memory_type: str = "episodic",
        importance: float | None = None,
        emotional_valence: float = 0.0,
        confidence: float = 1.0,
        source_event_id: str | None = None,
        structured_payload: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> dict[str, Any]:
        now = timestamp or utcnow()
        effective_importance = salience if importance is None else importance
        item = {
            "id": str(uuid.uuid4()),
            "pet_id": pet_id,
            "kind": kind,
            "title": title,
            "content": content,
            "salience": salience,
            "source": source,
            "embedding": embedding,
            "metadata": metadata or {},
            "memory_type": memory_type or "episodic",
            "importance": effective_importance,
            "emotional_valence": emotional_valence,
            "confidence": confidence,
            "source_event_id": source_event_id,
            "structured_payload": structured_payload or {},
            "created_at": now,
            "last_seen_at": now,
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    id, pet_id, kind, title, content, salience, source,
                    embedding_json, metadata_json, memory_type, importance,
                    emotional_valence, confidence, source_event_id, structured_payload_json,
                    created_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["id"],
                    pet_id,
                    kind,
                    title,
                    content,
                    salience,
                    source,
                    json.dumps(embedding),
                    json.dumps(item["metadata"], ensure_ascii=False),
                    item["memory_type"],
                    item["importance"],
                    item["emotional_valence"],
                    item["confidence"],
                    item["source_event_id"],
                    json.dumps(item["structured_payload"], ensure_ascii=False),
                    iso(now),
                    iso(now),
                ),
            )
        return item

    def list_memories(self, pet_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memories
                WHERE pet_id = ?
                ORDER BY salience DESC, last_seen_at DESC
                LIMIT ?
                """,
                (pet_id, limit),
            ).fetchall()
        return [self._memory_from_row(row, include_embedding=True) for row in rows]

    def get_memory(self, pet_id: str, memory_id: str, include_embedding: bool = True) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM memories
                WHERE pet_id = ? AND id = ?
                """,
                (pet_id, memory_id),
            ).fetchone()
        return self._memory_from_row(row, include_embedding=include_embedding) if row else None

    def update_memory(
        self,
        *,
        pet_id: str,
        memory_id: str,
        kind: str,
        title: str,
        content: str,
        salience: float,
        source: str,
        embedding: list[float],
        metadata: dict[str, Any] | None = None,
        memory_type: str = "episodic",
        importance: float = 0.5,
        emotional_valence: float = 0.0,
        confidence: float = 1.0,
        source_event_id: str | None = None,
        structured_payload: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> dict[str, Any] | None:
        now = timestamp or utcnow()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE memories
                SET kind = ?,
                    title = ?,
                    content = ?,
                    salience = ?,
                    source = ?,
                    embedding_json = ?,
                    metadata_json = ?,
                    memory_type = ?,
                    importance = ?,
                    emotional_valence = ?,
                    confidence = ?,
                    source_event_id = ?,
                    structured_payload_json = ?,
                    last_seen_at = ?
                WHERE pet_id = ? AND id = ?
                """,
                (
                    kind,
                    title,
                    content,
                    salience,
                    source,
                    json.dumps(embedding),
                    json.dumps(metadata or {}, ensure_ascii=False),
                    memory_type or "episodic",
                    importance,
                    emotional_valence,
                    confidence,
                    source_event_id,
                    json.dumps(structured_payload or {}, ensure_ascii=False),
                    iso(now),
                    pet_id,
                    memory_id,
                ),
            )
        return self.get_memory(pet_id, memory_id, include_embedding=True)

    def delete_memory(self, pet_id: str, memory_id: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM memories
                WHERE pet_id = ? AND id = ?
                """,
                (pet_id, memory_id),
            )
            return cursor.rowcount > 0

    def touch_memory(self, memory_id: str, timestamp: datetime | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE memories SET last_seen_at = ? WHERE id = ?",
                (iso(timestamp or utcnow()), memory_id),
            )

    def _memory_from_row(self, row, include_embedding: bool = False) -> dict[str, Any]:
        item = {
            "id": row["id"],
            "pet_id": row["pet_id"],
            "kind": row["kind"],
            "title": row["title"],
            "content": row["content"],
            "salience": float(row["salience"]),
            "source": row["source"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "created_at": parse_dt(row["created_at"]),
            "last_seen_at": parse_dt(row["last_seen_at"]),
            "memory_type": row["memory_type"] if "memory_type" in row.keys() else row["kind"],
            "importance": float(row["importance"]) if "importance" in row.keys() else float(row["salience"]),
            "emotional_valence": float(row["emotional_valence"]) if "emotional_valence" in row.keys() else 0.0,
            "confidence": float(row["confidence"]) if "confidence" in row.keys() else 1.0,
            "source_event_id": row["source_event_id"] if "source_event_id" in row.keys() else None,
            "structured_payload": json.loads(row["structured_payload_json"] or "{}")
            if "structured_payload_json" in row.keys()
            else {},
        }
        if include_embedding:
            item["embedding"] = json.loads(row["embedding_json"] or "[]")
        return item
