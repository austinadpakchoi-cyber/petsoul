"""宠物记忆端点。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends

from ..dependencies import get_engine, get_memory_store
from ..http_utils import with_not_found
from ..schemas import (
    MemoryConsolidationResult,
    MemoryCreateRequest,
    MemoryDeleteResponse,
    MemoryRecord,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryUpdateRequest,
)

router = APIRouter()


@router.get("/api/v1/pets/{pet_id}/memories", response_model=list[MemoryRecord])
def memories(pet_id: str, limit: int = 50, engine=Depends(get_engine)) -> list[MemoryRecord]:
    return with_not_found(lambda: engine.list_memories(pet_id, limit=limit))


@router.post("/api/v1/pets/{pet_id}/memories", response_model=MemoryRecord)
def add_memory(pet_id: str, request: MemoryCreateRequest, engine=Depends(get_engine)) -> MemoryRecord:
    return with_not_found(
        lambda: engine.add_memory(
            pet_id=pet_id,
            kind=request.kind,
            title=request.title,
            content=request.content,
            salience=request.salience,
            source=request.source,
            metadata=request.metadata,
            memory_type=request.memory_type,
            importance=request.importance,
            emotional_valence=request.emotional_valence,
            confidence=request.confidence,
            source_event_id=request.source_event_id,
            structured_payload=request.structured_payload,
        )
    )


@router.patch("/api/v1/pets/{pet_id}/memories/{memory_id}", response_model=MemoryRecord)
def update_memory(
    pet_id: str,
    memory_id: str,
    request: MemoryUpdateRequest,
    engine=Depends(get_engine),
) -> MemoryRecord:
    return with_not_found(
        lambda: engine.update_memory(
            pet_id=pet_id,
            memory_id=memory_id,
            kind=request.kind,
            title=request.title,
            content=request.content,
            salience=request.salience,
            source=request.source,
            metadata=request.metadata,
            memory_type=request.memory_type,
            importance=request.importance,
            emotional_valence=request.emotional_valence,
            confidence=request.confidence,
            source_event_id=request.source_event_id,
            structured_payload=request.structured_payload,
        )
    )


@router.delete("/api/v1/pets/{pet_id}/memories/{memory_id}", response_model=MemoryDeleteResponse)
def delete_memory(pet_id: str, memory_id: str, engine=Depends(get_engine)) -> MemoryDeleteResponse:
    with_not_found(lambda: engine.delete_memory(pet_id, memory_id))
    return MemoryDeleteResponse(success=True, memory_id=memory_id)


@router.post("/api/v1/pets/{pet_id}/memories/search", response_model=MemorySearchResponse)
def search_memories(
    pet_id: str,
    request: MemorySearchRequest,
    engine=Depends(get_engine),
    memory_store=Depends(get_memory_store),
) -> MemorySearchResponse:
    items = with_not_found(lambda: engine.search_memories(pet_id, query=request.query, limit=request.limit))
    return MemorySearchResponse(
        pet_id=pet_id,
        query=request.query,
        provider=memory_store.provider_name,
        items=items,
    )


@router.post("/api/v1/pets/{pet_id}/memories/consolidate", response_model=MemoryConsolidationResult)
def consolidate_memories(
    pet_id: str,
    target_date: date | None = None,
    engine=Depends(get_engine),
) -> MemoryConsolidationResult:
    return with_not_found(lambda: engine.consolidate_daily_memories(pet_id, target_date or date.today()))
