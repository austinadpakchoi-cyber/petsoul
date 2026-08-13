"""记忆存储协议：嵌入 Provider 与 MemoryStore 的公共接口。"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from ..schemas import MemoryConsolidationResult, MemoryRecord


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
