"""SQLite 记忆存储：默认实现，落盘于本地 sqlite 数据库。"""

from __future__ import annotations

from datetime import date, datetime, timezone

from ..config import Settings
from ..schemas import MemoryConsolidationResult, MemoryRecord
from ..storage import JourneyStorage, utcnow
from .hash_embedding import HashEmbeddingProvider


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
            if memory.created_at.astimezone(timezone.utc).date() == target_date
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
