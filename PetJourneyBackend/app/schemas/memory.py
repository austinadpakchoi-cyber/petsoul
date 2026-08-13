from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import Field

from .base import PetJourneyBaseModel


class MemoryRecord(PetJourneyBaseModel):
    id: str
    pet_id: str
    kind: str
    title: str
    content: str
    salience: float
    source: str
    created_at: datetime
    last_seen_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    memory_type: str = "episodic"
    importance: float = 0.5
    emotional_valence: float = 0.0
    confidence: float = 1.0
    source_event_id: str | None = None
    structured_payload: dict[str, Any] = Field(default_factory=dict)


class MemoryCreateRequest(PetJourneyBaseModel):
    kind: str = "note"
    title: str
    content: str
    salience: float = 0.5
    source: str = "manual"
    metadata: dict[str, Any] = Field(default_factory=dict)
    memory_type: str = "episodic"
    importance: float | None = None
    emotional_valence: float = 0.0
    confidence: float = 1.0
    source_event_id: str | None = None
    structured_payload: dict[str, Any] = Field(default_factory=dict)


class MemoryUpdateRequest(PetJourneyBaseModel):
    kind: str | None = None
    title: str | None = None
    content: str | None = None
    salience: float | None = None
    source: str | None = None
    metadata: dict[str, Any] | None = None
    memory_type: str | None = None
    importance: float | None = None
    emotional_valence: float | None = None
    confidence: float | None = None
    source_event_id: str | None = None
    structured_payload: dict[str, Any] | None = None


class MemoryDeleteResponse(PetJourneyBaseModel):
    success: bool
    memory_id: str


class MemorySearchRequest(PetJourneyBaseModel):
    query: str
    limit: int = 8


class MemorySearchResponse(PetJourneyBaseModel):
    pet_id: str
    query: str
    provider: str
    items: list[MemoryRecord]


class MemoryConsolidationResult(PetJourneyBaseModel):
    pet_id: str
    date: date
    provider: str
    source_memory_count: int
    created_memories: list[MemoryRecord] = Field(default_factory=list)
    relationship_summary: str
    place_affect: dict[str, float] = Field(default_factory=dict)
    preference_updates: list[str] = Field(default_factory=list)
    tomorrow_bias: list[str] = Field(default_factory=list)


__all__ = [
    "MemoryRecord",
    "MemoryCreateRequest",
    "MemoryUpdateRequest",
    "MemoryDeleteResponse",
    "MemorySearchRequest",
    "MemorySearchResponse",
    "MemoryConsolidationResult",
]
