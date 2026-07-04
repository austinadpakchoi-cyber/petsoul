from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
import json
from math import sqrt
from typing import Protocol

from .config import Settings
from .schemas import MemoryConsolidationResult, MemoryRecord
from .storage import JourneyStorage, utcnow


class EmbeddingProvider(Protocol):
    provider_name: str

    def embed(self, text: str) -> list[float]:
        ...


class MemoryStore(Protocol):
    provider_name: str

    def add_memory(
        self,
        *,
        pet_id: str,
        kind: str,
        title: str,
        content: str,
        salience: float,
        source: str,
        metadata: dict[str, object] | None = None,
        memory_type: str = "episodic",
        importance: float | None = None,
        emotional_valence: float = 0.0,
        confidence: float = 1.0,
        source_event_id: str | None = None,
        structured_payload: dict[str, object] | None = None,
    ) -> MemoryRecord:
        ...

    def list_memories(self, pet_id: str, limit: int = 50) -> list[MemoryRecord]:
        ...

    def update_memory(
        self,
        *,
        pet_id: str,
        memory_id: str,
        kind: str | None = None,
        title: str | None = None,
        content: str | None = None,
        salience: float | None = None,
        source: str | None = None,
        metadata: dict[str, object] | None = None,
        memory_type: str | None = None,
        importance: float | None = None,
        emotional_valence: float | None = None,
        confidence: float | None = None,
        source_event_id: str | None = None,
        structured_payload: dict[str, object] | None = None,
    ) -> MemoryRecord:
        ...

    def delete_memory(self, pet_id: str, memory_id: str) -> bool:
        ...

    def search_memories(self, pet_id: str, query: str, limit: int = 8) -> list[MemoryRecord]:
        ...

    def consolidate_daily_memories(self, pet_id: str, target_date: date) -> MemoryConsolidationResult:
        ...

    def config_snapshot(self) -> dict[str, str | bool | int]:
        ...


class HashEmbeddingProvider:
    provider_name = "hash-embedding-provider"

    def __init__(self, dimensions: int = 64):
        self.dimensions = max(8, dimensions)

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = [token for token in self._tokens(text) if token]
        if not tokens:
            return vector
        for token in tokens:
            digest = sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = sqrt(sum(value * value for value in vector)) or 1.0
        return [round(value / norm, 6) for value in vector]

    def _tokens(self, text: str) -> list[str]:
        compact = text.lower().strip()
        if not compact:
            return []
        words = compact.replace("，", " ").replace("。", " ").replace("、", " ").split()
        if words:
            tokens = words
        else:
            tokens = []
        tokens.extend(compact[index : index + 2] for index in range(max(0, len(compact) - 1)))
        return tokens


class SQLiteMemoryStore:
    provider_name = "sqlite-memory-store"

    def __init__(self, storage: JourneyStorage, settings: Settings):
        self.storage = storage
        self.settings = settings
        self.embedding_provider = HashEmbeddingProvider(settings.memory_embedding_dimensions)

    def add_memory(
        self,
        *,
        pet_id: str,
        kind: str,
        title: str,
        content: str,
        salience: float,
        source: str,
        metadata: dict[str, object] | None = None,
        memory_type: str = "episodic",
        importance: float | None = None,
        emotional_valence: float = 0.0,
        confidence: float = 1.0,
        source_event_id: str | None = None,
        structured_payload: dict[str, object] | None = None,
    ) -> MemoryRecord:
        clipped_salience = max(0.0, min(1.0, salience))
        clipped_importance = max(0.0, min(1.0, clipped_salience if importance is None else importance))
        embedding = self.embedding_provider.embed(f"{kind}\n{title}\n{content}")
        item = self.storage.add_memory(
            pet_id=pet_id,
            kind=kind,
            title=title,
            content=content,
            salience=clipped_salience,
            source=source,
            embedding=embedding,
            metadata=metadata,
            memory_type=memory_type or kind or "episodic",
            importance=clipped_importance,
            emotional_valence=max(-1.0, min(1.0, emotional_valence)),
            confidence=max(0.0, min(1.0, confidence)),
            source_event_id=source_event_id,
            structured_payload=structured_payload,
        )
        return self._record(item)

    def list_memories(self, pet_id: str, limit: int = 50) -> list[MemoryRecord]:
        return [self._record(item) for item in self.storage.list_memories(pet_id, limit=limit)]

    def update_memory(
        self,
        *,
        pet_id: str,
        memory_id: str,
        kind: str | None = None,
        title: str | None = None,
        content: str | None = None,
        salience: float | None = None,
        source: str | None = None,
        metadata: dict[str, object] | None = None,
        memory_type: str | None = None,
        importance: float | None = None,
        emotional_valence: float | None = None,
        confidence: float | None = None,
        source_event_id: str | None = None,
        structured_payload: dict[str, object] | None = None,
    ) -> MemoryRecord:
        current = self.storage.get_memory(pet_id, memory_id, include_embedding=True)
        if not current:
            raise KeyError(memory_id)

        next_kind = self._non_empty(kind, current["kind"])
        next_title = self._non_empty(title, current["title"])
        next_content = self._non_empty(content, current["content"])
        next_salience = self._clip_01(float(current["salience"]) if salience is None else salience)
        next_importance = self._clip_01(float(current.get("importance", next_salience)) if importance is None else importance)
        next_valence = self._clip_signed(
            float(current.get("emotional_valence", 0.0)) if emotional_valence is None else emotional_valence
        )
        next_confidence = self._clip_01(float(current.get("confidence", 1.0)) if confidence is None else confidence)
        text_changed = any(value is not None for value in (kind, title, content))
        embedding = (
            self.embedding_provider.embed(f"{next_kind}\n{next_title}\n{next_content}")
            if text_changed
            else list(current.get("embedding") or self.embedding_provider.embed(f"{next_kind}\n{next_title}\n{next_content}"))
        )

        updated = self.storage.update_memory(
            pet_id=pet_id,
            memory_id=memory_id,
            kind=next_kind,
            title=next_title,
            content=next_content,
            salience=next_salience,
            source=self._non_empty(source, current["source"]),
            embedding=embedding,
            metadata=current.get("metadata", {}) if metadata is None else metadata,
            memory_type=self._non_empty(memory_type, current.get("memory_type") or next_kind),
            importance=next_importance,
            emotional_valence=next_valence,
            confidence=next_confidence,
            source_event_id=current.get("source_event_id") if source_event_id is None else source_event_id,
            structured_payload=current.get("structured_payload", {}) if structured_payload is None else structured_payload,
        )
        if not updated:
            raise KeyError(memory_id)
        return self._record(updated)

    def delete_memory(self, pet_id: str, memory_id: str) -> bool:
        return self.storage.delete_memory(pet_id, memory_id)

    def search_memories(self, pet_id: str, query: str, limit: int = 8) -> list[MemoryRecord]:
        query_embedding = self.embedding_provider.embed(query)
        candidates = self.storage.list_memories(pet_id, limit=200)
        scored = [
            (
                self._rank_score(query=query, query_embedding=query_embedding, item=item),
                item,
            )
            for item in candidates
        ]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        for _, item in scored[:limit]:
            self.storage.touch_memory(str(item["id"]))
        return [self._record(item) for _, item in scored[:limit]]

    def config_snapshot(self) -> dict[str, str | bool | int]:
        return {
            "provider": self.provider_name,
            "embedding_provider": self.embedding_provider.provider_name,
            "dimensions": self.embedding_provider.dimensions,
            "postgres_configured": bool(self.settings.postgres_dsn),
            "pgvector_active": False,
        }

    def consolidate_daily_memories(self, pet_id: str, target_date: date) -> MemoryConsolidationResult:
        memories = [
            memory
            for memory in self.list_memories(pet_id, limit=200)
            if memory.created_at.astimezone().date() == target_date
        ]
        if not memories:
            return MemoryConsolidationResult(
                pet_id=pet_id,
                date=target_date,
                provider=self.provider_name,
                source_memory_count=0,
                created_memories=[],
                relationship_summary="今天没有新的可整理记忆。",
                place_affect={},
                preference_updates=[],
                tomorrow_bias=["保持慢节奏", "优先真实路线"],
            )

        important = sorted(memories, key=lambda memory: (memory.importance, memory.salience), reverse=True)[:8]
        titles = "、".join(memory.title for memory in important[:5])
        relationship_summary = f"这一天最值得保留的片段：{titles}。"
        place_affect: dict[str, float] = {}
        preference_updates: list[str] = []
        tomorrow_bias: list[str] = ["优先靠近安静、可停留的真实地点"]
        for memory in important:
            city = str(memory.metadata.get("city") or memory.structured_payload.get("city") or "")
            place_name = str(memory.metadata.get("place_name") or memory.structured_payload.get("place_name") or "")
            place_key = place_name or city
            if place_key:
                place_affect[place_key] = round(
                    place_affect.get(place_key, 0.0) + memory.importance * max(0.2, memory.emotional_valence + 0.8),
                    3,
                )
            if memory.kind in {"owner_preference", "travel_bag", "feedback"}:
                preference_updates.append(memory.title)
            if memory.kind in {"postcard", "souvenir"}:
                tomorrow_bias.append("如果路线允许，多选择有照片潜力的温柔地点")

        created = [
            self.add_memory(
                pet_id=pet_id,
                kind="daily_consolidation",
                title=f"{target_date.isoformat()} 的关系整理",
                content=relationship_summary,
                salience=0.82,
                source="memory_consolidation",
                memory_type="relationship",
                importance=0.84,
                emotional_valence=0.35,
                confidence=0.8,
                structured_payload={
                    "date": target_date.isoformat(),
                    "source_memory_ids": [memory.id for memory in important],
                    "preference_updates": preference_updates,
                    "tomorrow_bias": tomorrow_bias,
                },
            ),
            self.add_memory(
                pet_id=pet_id,
                kind="place_affect",
                title=f"{target_date.isoformat()} 的地点情绪",
                content="；".join(f"{place}: {score:.2f}" for place, score in place_affect.items()) or "今天没有明确地点情绪。",
                salience=0.7,
                source="memory_consolidation",
                memory_type="place_affect",
                importance=0.72,
                emotional_valence=0.25,
                confidence=0.74,
                structured_payload={"date": target_date.isoformat(), "place_affect": place_affect},
            ),
        ]
        return MemoryConsolidationResult(
            pet_id=pet_id,
            date=target_date,
            provider=self.provider_name,
            source_memory_count=len(memories),
            created_memories=created,
            relationship_summary=relationship_summary,
            place_affect=place_affect,
            preference_updates=preference_updates,
            tomorrow_bias=tomorrow_bias,
        )

    def _similarity(self, left: list[float], right: list[float]) -> float:
        if not left or not right:
            return 0.0
        size = min(len(left), len(right))
        return sum(left[index] * right[index] for index in range(size))

    def _rank_score(self, *, query: str, query_embedding: list[float], item: dict[str, object]) -> float:
        similarity = self._similarity(query_embedding, item.get("embedding") or [])
        importance = float(item.get("importance") or item.get("salience") or 0.0)
        salience = float(item.get("salience") or 0.0)
        recency = self._recency_score(item.get("last_seen_at") or item.get("created_at"))
        emotional = self._emotional_relevance(query=query, item=item)
        type_boost = self._memory_type_boost(str(item.get("memory_type") or item.get("kind") or "episodic"))
        return similarity * 0.62 + importance * 0.2 + salience * 0.08 + recency * 0.06 + emotional * 0.08 + type_boost

    def _recency_score(self, value: object) -> float:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value)
            except ValueError:
                return 0.0
        else:
            return 0.0
        age_days = max(0.0, (utcnow() - dt).total_seconds() / 86400)
        return max(0.0, min(1.0, 1.0 / (1.0 + age_days)))

    def _emotional_relevance(self, *, query: str, item: dict[str, object]) -> float:
        valence = float(item.get("emotional_valence") or 0.0)
        text = f"{query} {item.get('title') or ''} {item.get('content') or ''}".lower()
        warm_words = ("想", "爱", "抱", "开心", "温柔", "回家", "陪", "安心", "慢")
        heavy_words = ("难过", "害怕", "孤单", "累", "痛", "哭")
        if any(word in text for word in warm_words):
            return max(0.0, valence) + 0.2
        if any(word in text for word in heavy_words):
            return abs(valence) + 0.15
        return max(0.0, valence) * 0.3

    def _memory_type_boost(self, memory_type: str) -> float:
        if memory_type in {"relationship", "preference", "place_affect"}:
            return 0.05
        if memory_type == "recent_episodic":
            return 0.03
        return 0.0

    def _clip_01(self, value: float) -> float:
        return max(0.0, min(1.0, value))

    def _clip_signed(self, value: float) -> float:
        return max(-1.0, min(1.0, value))

    def _non_empty(self, value: object | None, fallback: object) -> str:
        if value is None:
            return str(fallback)
        text = str(value).strip()
        return text or str(fallback)

    def _record(self, item: dict[str, object]) -> MemoryRecord:
        return MemoryRecord.model_validate(
            {
                key: value
                for key, value in item.items()
                if key
                in {
                    "id",
                    "pet_id",
                    "kind",
                    "title",
                    "content",
                    "salience",
                    "source",
                    "created_at",
                    "last_seen_at",
                    "metadata",
                    "memory_type",
                    "importance",
                    "emotional_valence",
                    "confidence",
                    "source_event_id",
                    "structured_payload",
                }
            }
        )


class PostgresPgVectorMemoryStore(SQLiteMemoryStore):
    provider_name = "postgres-pgvector-memory-store"

    def __init__(self, storage: JourneyStorage, settings: Settings):
        super().__init__(storage, settings)
        self.pgvector_active = False
        self.last_postgres_error = ""
        self._psycopg = None
        self._initialize_postgres()

    def add_memory(
        self,
        *,
        pet_id: str,
        kind: str,
        title: str,
        content: str,
        salience: float,
        source: str,
        metadata: dict[str, object] | None = None,
        memory_type: str = "episodic",
        importance: float | None = None,
        emotional_valence: float = 0.0,
        confidence: float = 1.0,
        source_event_id: str | None = None,
        structured_payload: dict[str, object] | None = None,
    ) -> MemoryRecord:
        if not self.pgvector_active:
            return super().add_memory(
                pet_id=pet_id,
                kind=kind,
                title=title,
                content=content,
                salience=salience,
                source=source,
                metadata=metadata,
                memory_type=memory_type,
                importance=importance,
                emotional_valence=emotional_valence,
                confidence=confidence,
                source_event_id=source_event_id,
                structured_payload=structured_payload,
            )

        now = utcnow()
        embedding = self.embedding_provider.embed(f"{kind}\n{title}\n{content}")
        clipped_salience = max(0.0, min(1.0, salience))
        clipped_importance = max(0.0, min(1.0, clipped_salience if importance is None else importance))
        payload = {
            "id": self._uuid(),
            "pet_id": pet_id,
            "kind": kind,
            "title": title,
            "content": content,
            "salience": clipped_salience,
            "source": source,
            "metadata": metadata or {},
            "memory_type": memory_type or kind or "episodic",
            "importance": clipped_importance,
            "emotional_valence": max(-1.0, min(1.0, emotional_valence)),
            "confidence": max(0.0, min(1.0, confidence)),
            "source_event_id": source_event_id,
            "structured_payload": structured_payload or {},
            "created_at": now,
            "last_seen_at": now,
        }
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO pet_memories (
                        id, pet_id, kind, title, content, salience, source,
                        embedding, metadata_json, memory_type, importance,
                        emotional_valence, confidence, source_event_id, structured_payload_json,
                        created_at, last_seen_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector, %s::jsonb, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                    """,
                    (
                        payload["id"],
                        pet_id,
                        kind,
                        title,
                        content,
                        payload["salience"],
                        source,
                        self._vector_literal(embedding),
                        json.dumps(payload["metadata"], ensure_ascii=False),
                        payload["memory_type"],
                        payload["importance"],
                        payload["emotional_valence"],
                        payload["confidence"],
                        payload["source_event_id"],
                        json.dumps(payload["structured_payload"], ensure_ascii=False),
                        now,
                        now,
                    ),
                )
            return self._record(payload)
        except Exception as exc:
            self.last_postgres_error = str(exc)
            return super().add_memory(
                pet_id=pet_id,
                kind=kind,
                title=title,
                content=content,
                salience=salience,
                source=source,
                metadata=metadata,
                memory_type=memory_type,
                importance=importance,
                emotional_valence=emotional_valence,
                confidence=confidence,
                source_event_id=source_event_id,
                structured_payload=structured_payload,
            )

    def list_memories(self, pet_id: str, limit: int = 50) -> list[MemoryRecord]:
        if not self.pgvector_active:
            return super().list_memories(pet_id, limit=limit)
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, pet_id, kind, title, content, salience, source,
                           metadata_json, memory_type, importance, emotional_valence,
                           confidence, source_event_id, structured_payload_json,
                           created_at, last_seen_at
                    FROM pet_memories
                    WHERE pet_id = %s
                    ORDER BY salience DESC, last_seen_at DESC
                    LIMIT %s
                    """,
                    (pet_id, limit),
                ).fetchall()
            return [self._record_from_pg(row) for row in rows]
        except Exception as exc:
            self.last_postgres_error = str(exc)
            return super().list_memories(pet_id, limit=limit)

    def search_memories(self, pet_id: str, query: str, limit: int = 8) -> list[MemoryRecord]:
        if not self.pgvector_active:
            return super().search_memories(pet_id, query=query, limit=limit)
        vector = self._vector_literal(self.embedding_provider.embed(query))
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, pet_id, kind, title, content, salience, source,
                           metadata_json, memory_type, importance, emotional_valence,
                           confidence, source_event_id, structured_payload_json,
                           created_at, last_seen_at
                    FROM pet_memories
                    WHERE pet_id = %s
                    ORDER BY (embedding <=> %s::vector) ASC, salience DESC
                    LIMIT %s
                    """,
                    (pet_id, vector, limit),
                ).fetchall()
                memory_ids = [str(row["id"]) for row in rows]
                if memory_ids:
                    conn.execute(
                        "UPDATE pet_memories SET last_seen_at = %s WHERE id = ANY(%s)",
                        (utcnow(), memory_ids),
                    )
            return [self._record_from_pg(row) for row in rows]
        except Exception as exc:
            self.last_postgres_error = str(exc)
            return super().search_memories(pet_id, query=query, limit=limit)

    def update_memory(
        self,
        *,
        pet_id: str,
        memory_id: str,
        kind: str | None = None,
        title: str | None = None,
        content: str | None = None,
        salience: float | None = None,
        source: str | None = None,
        metadata: dict[str, object] | None = None,
        memory_type: str | None = None,
        importance: float | None = None,
        emotional_valence: float | None = None,
        confidence: float | None = None,
        source_event_id: str | None = None,
        structured_payload: dict[str, object] | None = None,
    ) -> MemoryRecord:
        if not self.pgvector_active:
            return super().update_memory(
                pet_id=pet_id,
                memory_id=memory_id,
                kind=kind,
                title=title,
                content=content,
                salience=salience,
                source=source,
                metadata=metadata,
                memory_type=memory_type,
                importance=importance,
                emotional_valence=emotional_valence,
                confidence=confidence,
                source_event_id=source_event_id,
                structured_payload=structured_payload,
            )
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT id, pet_id, kind, title, content, salience, source,
                           metadata_json, memory_type, importance, emotional_valence,
                           confidence, source_event_id, structured_payload_json,
                           created_at, last_seen_at
                    FROM pet_memories
                    WHERE pet_id = %s AND id = %s
                    """,
                    (pet_id, memory_id),
                ).fetchone()
                if not row:
                    raise KeyError(memory_id)
                current = self._record_from_pg(row)
                next_kind = self._non_empty(kind, current.kind)
                next_title = self._non_empty(title, current.title)
                next_content = self._non_empty(content, current.content)
                next_salience = self._clip_01(current.salience if salience is None else salience)
                next_importance = self._clip_01(current.importance if importance is None else importance)
                next_valence = self._clip_signed(
                    current.emotional_valence if emotional_valence is None else emotional_valence
                )
                next_confidence = self._clip_01(current.confidence if confidence is None else confidence)
                embedding = self.embedding_provider.embed(f"{next_kind}\n{next_title}\n{next_content}")
                now = utcnow()
                next_metadata = current.metadata if metadata is None else metadata
                next_payload = current.structured_payload if structured_payload is None else structured_payload
                next_source_event_id = current.source_event_id if source_event_id is None else source_event_id

                conn.execute(
                    """
                    UPDATE pet_memories
                    SET kind = %s,
                        title = %s,
                        content = %s,
                        salience = %s,
                        source = %s,
                        embedding = %s::vector,
                        metadata_json = %s::jsonb,
                        memory_type = %s,
                        importance = %s,
                        emotional_valence = %s,
                        confidence = %s,
                        source_event_id = %s,
                        structured_payload_json = %s::jsonb,
                        last_seen_at = %s
                    WHERE pet_id = %s AND id = %s
                    """,
                    (
                        next_kind,
                        next_title,
                        next_content,
                        next_salience,
                        self._non_empty(source, current.source),
                        self._vector_literal(embedding),
                        json.dumps(next_metadata, ensure_ascii=False),
                        self._non_empty(memory_type, current.memory_type),
                        next_importance,
                        next_valence,
                        next_confidence,
                        next_source_event_id,
                        json.dumps(next_payload, ensure_ascii=False),
                        now,
                        pet_id,
                        memory_id,
                    ),
                )
            return self._record(
                {
                    "id": memory_id,
                    "pet_id": pet_id,
                    "kind": next_kind,
                    "title": next_title,
                    "content": next_content,
                    "salience": next_salience,
                    "source": self._non_empty(source, current.source),
                    "metadata": next_metadata,
                    "memory_type": self._non_empty(memory_type, current.memory_type),
                    "importance": next_importance,
                    "emotional_valence": next_valence,
                    "confidence": next_confidence,
                    "source_event_id": next_source_event_id,
                    "structured_payload": next_payload,
                    "created_at": current.created_at,
                    "last_seen_at": now,
                }
            )
        except KeyError:
            raise
        except Exception as exc:
            self.last_postgres_error = str(exc)
            return super().update_memory(
                pet_id=pet_id,
                memory_id=memory_id,
                kind=kind,
                title=title,
                content=content,
                salience=salience,
                source=source,
                metadata=metadata,
                memory_type=memory_type,
                importance=importance,
                emotional_valence=emotional_valence,
                confidence=confidence,
                source_event_id=source_event_id,
                structured_payload=structured_payload,
            )

    def delete_memory(self, pet_id: str, memory_id: str) -> bool:
        if not self.pgvector_active:
            return super().delete_memory(pet_id, memory_id)
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    DELETE FROM pet_memories
                    WHERE pet_id = %s AND id = %s
                    """,
                    (pet_id, memory_id),
                )
                return cursor.rowcount > 0
        except Exception as exc:
            self.last_postgres_error = str(exc)
            return super().delete_memory(pet_id, memory_id)

    def config_snapshot(self) -> dict[str, str | bool | int]:
        payload = super().config_snapshot()
        payload.update(
            {
                "provider": self.provider_name,
                "postgres_configured": bool(self.settings.postgres_dsn),
                "pgvector_active": self.pgvector_active,
                "last_postgres_error": self.last_postgres_error,
            }
        )
        return payload

    def _initialize_postgres(self) -> None:
        if not self.settings.postgres_dsn:
            self.last_postgres_error = "postgres dsn is not configured"
            return
        try:
            import psycopg  # type: ignore
            from psycopg.rows import dict_row  # type: ignore
        except Exception as exc:
            self.last_postgres_error = f"psycopg is not installed: {exc}"
            return
        self._psycopg = psycopg
        self._dict_row = dict_row
        try:
            dimensions = self.embedding_provider.dimensions
            with self._connect() as conn:
                conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS pet_memories (
                        id TEXT PRIMARY KEY,
                        pet_id TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        title TEXT NOT NULL,
                        content TEXT NOT NULL,
                        salience DOUBLE PRECISION NOT NULL,
                        source TEXT NOT NULL,
                        embedding vector({dimensions}) NOT NULL,
                        metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        memory_type TEXT NOT NULL DEFAULT 'episodic',
                        importance DOUBLE PRECISION NOT NULL DEFAULT 0.5,
                        emotional_valence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                        confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                        source_event_id TEXT,
                        structured_payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL,
                        last_seen_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                conn.execute("ALTER TABLE pet_memories ADD COLUMN IF NOT EXISTS memory_type TEXT NOT NULL DEFAULT 'episodic'")
                conn.execute("ALTER TABLE pet_memories ADD COLUMN IF NOT EXISTS importance DOUBLE PRECISION NOT NULL DEFAULT 0.5")
                conn.execute("ALTER TABLE pet_memories ADD COLUMN IF NOT EXISTS emotional_valence DOUBLE PRECISION NOT NULL DEFAULT 0.0")
                conn.execute("ALTER TABLE pet_memories ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0")
                conn.execute("ALTER TABLE pet_memories ADD COLUMN IF NOT EXISTS source_event_id TEXT")
                conn.execute("ALTER TABLE pet_memories ADD COLUMN IF NOT EXISTS structured_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb")
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_pet_memories_pet_seen
                    ON pet_memories (pet_id, last_seen_at DESC)
                    """
                )
                try:
                    conn.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_pet_memories_embedding
                        ON pet_memories USING hnsw (embedding vector_cosine_ops)
                        """
                    )
                except Exception as index_exc:
                    self.last_postgres_error = f"pgvector table ready, hnsw index skipped: {index_exc}"
            self.pgvector_active = True
            if not self.last_postgres_error.startswith("pgvector table ready"):
                self.last_postgres_error = ""
        except Exception as exc:
            self.pgvector_active = False
            self.last_postgres_error = str(exc)

    def _connect(self):
        if not self._psycopg or not self.settings.postgres_dsn:
            raise RuntimeError("postgres is not configured")
        return self._psycopg.connect(self.settings.postgres_dsn, row_factory=self._dict_row)

    def _vector_literal(self, embedding: list[float]) -> str:
        return "[" + ",".join(str(value) for value in embedding) + "]"

    def _record_from_pg(self, row: dict[str, object]) -> MemoryRecord:
        return MemoryRecord.model_validate(
            {
                "id": row["id"],
                "pet_id": row["pet_id"],
                "kind": row["kind"],
                "title": row["title"],
                "content": row["content"],
                "salience": row["salience"],
                "source": row["source"],
                "metadata": row.get("metadata_json") or {},
                "memory_type": row.get("memory_type") or row["kind"],
                "importance": row.get("importance") or row["salience"],
                "emotional_valence": row.get("emotional_valence") or 0.0,
                "confidence": row.get("confidence") or 1.0,
                "source_event_id": row.get("source_event_id"),
                "structured_payload": row.get("structured_payload_json") or {},
                "created_at": row["created_at"],
                "last_seen_at": row["last_seen_at"],
            }
        )

    def _uuid(self) -> str:
        import uuid

        return str(uuid.uuid4())


def build_memory_store(storage: JourneyStorage, settings: Settings) -> MemoryStore:
    if settings.memory_provider == "postgres" and settings.postgres_dsn:
        return PostgresPgVectorMemoryStore(storage, settings)
    return SQLiteMemoryStore(storage, settings)
