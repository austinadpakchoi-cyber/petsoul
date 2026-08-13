"""记忆 CRUD 编排：记忆读写检索、DNA 维护与内心独白翻译。"""

from __future__ import annotations

from datetime import date

from ..schemas import (
    MemoryConsolidationResult,
    MemoryRecord,
    PetDNA,
    ThoughtTranslation,
)
from .exceptions import PetNotFoundError, ThoughtNotFoundError


class MemoryMixin:
    def list_memories(self, pet_id: str, limit: int = 50) -> list[MemoryRecord]:
        self._pet(pet_id)
        return self.memory_store.list_memories(pet_id, limit=max(1, min(100, limit)))

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
        self._pet(pet_id)
        return self.memory_store.add_memory(
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
        self._pet(pet_id)
        return self.memory_store.update_memory(
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
        self._pet(pet_id)
        deleted = self.memory_store.delete_memory(pet_id, memory_id)
        if not deleted:
            raise KeyError(memory_id)
        return deleted

    def search_memories(self, pet_id: str, query: str, limit: int = 8) -> list[MemoryRecord]:
        self._pet(pet_id)
        return self.memory_store.search_memories(pet_id, query=query, limit=max(1, min(30, limit)))

    def consolidate_daily_memories(self, pet_id: str, target_date: date) -> MemoryConsolidationResult:
        self._pet(pet_id)
        return self.memory_store.consolidate_daily_memories(pet_id, target_date)

    def pet_dna(self, pet_id: str):
        return self._pet(pet_id).dna

    def update_pet_dna(self, pet_id: str, dna: PetDNA) -> PetDNA:
        self._pet(pet_id)
        updated = self.storage.update_pet_dna(pet_id, dna)
        if not updated:
            raise PetNotFoundError(pet_id)
        self.memory_store.add_memory(
            pet_id=pet_id,
            kind="dna_update",
            title=f"{updated.name} 的通讯 DNA 更新",
            content=(
                f"主人称呼：{dna.owner_title}；性格：{dna.personality}；"
                f"喜欢的地方：{'、'.join(dna.favorite_places)}；爱好：{'、'.join(dna.hobby)}；"
                f"口头禅：{dna.catchphrase}；说话风格：{dna.voice_style}。"
            ),
            salience=0.82,
            source="owner_dna_editor",
            memory_type="preference",
            importance=0.86,
            emotional_valence=0.25,
            confidence=1.0,
            structured_payload=dna.model_dump(by_alias=True),
        )
        return updated.dna

    def thought_translation(self, pet_id: str, thought_id: str) -> ThoughtTranslation:
        self._pet(pet_id)
        thought = self.storage.get_thought(pet_id, thought_id, include_translation=True)
        if not thought or not thought["translation"]:
            raise ThoughtNotFoundError(thought_id)
        return ThoughtTranslation(
            thought_id=thought["id"],
            pet_id=pet_id,
            animal_text=thought["animal_text"] or thought["text"],
            translation=thought["translation"],
            tone=thought["tone"],
            language_style=thought["language_style"],
            model=thought["model"],
        )
