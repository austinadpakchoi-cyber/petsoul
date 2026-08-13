"""旅行聚合 Repository mixin：travel_quests / travel_bags / souvenirs 的 CRUD。

`souvenirs` 的底层写辅助（_upsert_souvenir 等）位于 economy mixin，
`save_souvenirs` 通过 `self._upsert_souvenir` 复用（多重继承下运行时解析）。
"""

from __future__ import annotations

import json

from ..schemas import ItemStatus, SouvenirItem, TravelBag, TravelQuest
from ..utils import iso


class TravelRepositoryMixin:
    def save_travel_quest(self, quest: TravelQuest) -> TravelQuest:
        payload = quest.model_dump(mode="json", by_alias=True)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO travel_quests (id, pet_id, status, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    quest.id,
                    quest.pet_id,
                    quest.status.value,
                    json.dumps(payload, ensure_ascii=False),
                    iso(quest.created_at),
                    iso(quest.updated_at),
                ),
            )
        return quest

    def get_travel_quest(self, pet_id: str, quest_id: str) -> TravelQuest | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM travel_quests WHERE pet_id = ? AND id = ?",
                (pet_id, quest_id),
            ).fetchone()
        if not row:
            return None
        return TravelQuest.model_validate(json.loads(row["payload_json"]))

    def list_travel_quests(self, pet_id: str, limit: int = 20) -> list[TravelQuest]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM travel_quests
                WHERE pet_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (pet_id, max(1, min(100, limit))),
            ).fetchall()
        return [TravelQuest.model_validate(json.loads(row["payload_json"])) for row in rows]

    def save_travel_bag(self, bag: TravelBag) -> TravelBag:
        payload = bag.model_dump(mode="json", by_alias=True)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO travel_bags (id, pet_id, quest_id, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    quest_id = excluded.quest_id,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    bag.id,
                    bag.pet_id,
                    bag.quest_id,
                    json.dumps(payload, ensure_ascii=False),
                    iso(bag.updated_at),
                ),
            )
        return bag

    def get_travel_bag(self, pet_id: str, quest_id: str | None = None) -> TravelBag | None:
        bag_id = self.travel_bag_id(pet_id, quest_id)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM travel_bags WHERE pet_id = ? AND id = ?",
                (pet_id, bag_id),
            ).fetchone()
        if not row:
            return None
        return TravelBag.model_validate(json.loads(row["payload_json"]))

    def save_souvenirs(self, souvenirs: list[SouvenirItem]) -> list[SouvenirItem]:
        if not souvenirs:
            return []
        with self.connect() as conn:
            for item in souvenirs:
                self._upsert_souvenir(conn, item)
        return souvenirs

    def list_souvenirs(self, pet_id: str, limit: int = 50) -> list[SouvenirItem]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM souvenirs
                WHERE pet_id = ?
                ORDER BY obtained_at DESC
                LIMIT ?
                """,
                (pet_id, max(1, min(200, limit))),
            ).fetchall()
        return [SouvenirItem.model_validate(json.loads(row["payload_json"])) for row in rows]

    def list_souvenirs_for_quest(self, pet_id: str, quest_id: str) -> list[SouvenirItem]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM souvenirs
                WHERE pet_id = ? AND quest_id = ?
                ORDER BY obtained_at ASC
                """,
                (pet_id, quest_id),
            ).fetchall()
        return [SouvenirItem.model_validate(json.loads(row["payload_json"])) for row in rows]

    def get_souvenir(self, pet_id: str, item_id: str) -> SouvenirItem | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM souvenirs WHERE pet_id = ? AND id = ?",
                (pet_id, item_id),
            ).fetchone()
        return SouvenirItem.model_validate(json.loads(row["payload_json"])) if row else None

    def list_inventory(self, pet_id: str, status: ItemStatus | None = ItemStatus.owned, limit: int = 50) -> list[SouvenirItem]:
        with self.connect() as conn:
            if status is None:
                rows = conn.execute(
                    """
                    SELECT payload_json FROM souvenirs
                    WHERE pet_id = ?
                    ORDER BY obtained_at DESC
                    LIMIT ?
                    """,
                    (pet_id, max(1, min(200, limit))),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT payload_json FROM souvenirs
                    WHERE pet_id = ? AND status = ?
                    ORDER BY obtained_at DESC
                    LIMIT ?
                    """,
                    (pet_id, status.value, max(1, min(200, limit))),
                ).fetchall()
        return [SouvenirItem.model_validate(json.loads(row["payload_json"])) for row in rows]

    def travel_bag_id(self, pet_id: str, quest_id: str | None = None) -> str:
        key = quest_id or "main"
        return f"TB-{pet_id}-{key}"
