"""宠物聚合 Repository mixin：宠物生命周期 CRUD。"""

from __future__ import annotations

import json
import sqlite3
import uuid

from ..schemas import PetDNA, PetType
from ..utils import iso, parse_dt, utcnow
from .records import PetRecord


class PetRepositoryMixin:
    def create_pet(self, name: str, pet_type: PetType, dna: PetDNA, photo_path: str | None) -> PetRecord:
        pet_id = f"PJ-{uuid.uuid4().hex[:8].upper()}"
        created_at = utcnow()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO pets (pet_id, name, pet_type, dna_json, created_at, photo_path)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    pet_id,
                    name,
                    pet_type.value,
                    dna.model_dump_json(by_alias=True),
                    iso(created_at),
                    photo_path,
                ),
            )
        return PetRecord(pet_id=pet_id, name=name, pet_type=pet_type, dna=dna, created_at=created_at, photo_path=photo_path)

    def get_pet(self, pet_id: str) -> PetRecord | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM pets WHERE pet_id = ?", (pet_id,)).fetchone()
        if not row:
            return None
        return self._pet_from_row(row)

    def update_pet_dna(self, pet_id: str, dna: PetDNA) -> PetRecord | None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE pets
                SET dna_json = ?
                WHERE pet_id = ?
                """,
                (dna.model_dump_json(by_alias=True), pet_id),
            )
        return self.get_pet(pet_id)

    def list_pets(self) -> list[PetRecord]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM pets ORDER BY created_at ASC").fetchall()
        return [self._pet_from_row(row) for row in rows]

    def _pet_from_row(self, row: sqlite3.Row) -> PetRecord:
        return PetRecord(
            pet_id=row["pet_id"],
            name=row["name"],
            pet_type=PetType(row["pet_type"]),
            dna=PetDNA.model_validate(json.loads(row["dna_json"])),
            created_at=parse_dt(row["created_at"]),
            photo_path=row["photo_path"],
            owner_user_id=row["owner_user_id"],
        )
