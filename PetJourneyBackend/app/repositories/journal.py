"""旅程日记聚合 Repository mixin：thoughts / events / postcards / feedback。"""

from __future__ import annotations

from datetime import datetime, timedelta
import sqlite3
from typing import Any
import uuid

from ..meal_rules import is_time_inconsistent_postcard
from ..utils import iso, parse_dt, utcnow


class JournalRepositoryMixin:
    def append_thought(
        self,
        pet_id: str,
        text: str,
        tone: str,
        timestamp: datetime | None = None,
        animal_text: str | None = None,
        translation: str | None = None,
        language_style: str = "human",
        model: str | None = None,
    ) -> dict[str, Any]:
        item = {
            "id": str(uuid.uuid4()),
            "pet_id": pet_id,
            "text": text,
            "tone": tone,
            "timestamp": timestamp or utcnow(),
            "animal_text": animal_text,
            "translation": translation,
            "translation_available": bool(translation),
            "language_style": language_style,
            "model": model,
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO thoughts (
                    id, pet_id, text, tone, timestamp, animal_text, translation,
                    translation_available, language_style, model
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["id"],
                    pet_id,
                    text,
                    tone,
                    iso(item["timestamp"]),
                    animal_text,
                    translation,
                    1 if translation else 0,
                    language_style,
                    model,
                ),
            )
        return item

    def list_thoughts(self, pet_id: str, limit: int = 18, include_translation: bool = False) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM thoughts WHERE pet_id = ? ORDER BY timestamp DESC LIMIT ?",
                (pet_id, limit),
            ).fetchall()
        return [self._thought_from_row(row, include_translation=include_translation) for row in reversed(rows)]

    def get_thought(self, pet_id: str, thought_id: str, include_translation: bool = False) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM thoughts WHERE pet_id = ? AND id = ?",
                (pet_id, thought_id),
            ).fetchone()
        if not row:
            return None
        return self._thought_from_row(row, include_translation=include_translation)

    def append_event(self, pet_id: str, title: str, detail: str, timestamp: datetime | None = None) -> dict[str, Any]:
        item = {
            "id": str(uuid.uuid4()),
            "pet_id": pet_id,
            "title": title,
            "detail": detail,
            "timestamp": timestamp or utcnow(),
        }
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO events (id, pet_id, title, detail, timestamp) VALUES (?, ?, ?, ?, ?)",
                (item["id"], pet_id, title, detail, iso(item["timestamp"])),
            )
        return item

    def list_events(self, pet_id: str, limit: int = 24) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE pet_id = ? ORDER BY timestamp DESC LIMIT ?",
                (pet_id, limit),
            ).fetchall()
        return [self._event_from_row(row) for row in reversed(rows)]

    def add_postcard(
        self,
        pet_id: str,
        location: str,
        text: str,
        weather: str,
        happiness: int,
        image_url: str | None = None,
        timestamp: datetime | None = None,
        mission_id: str | None = None,
    ) -> dict[str, Any]:
        item = {
            "id": str(uuid.uuid4()),
            "pet_id": pet_id,
            "location": location,
            "text": text,
            "weather": weather,
            "happiness": happiness,
            "timestamp": timestamp or utcnow(),
            "image_url": image_url,
            "is_new": True,
            "mission_id": mission_id,
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO postcards (
                    id, pet_id, location, text, weather, happiness, timestamp, image_url, is_new, mission_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["id"],
                    pet_id,
                    location,
                    text,
                    weather,
                    happiness,
                    iso(item["timestamp"]),
                    image_url,
                    1,
                    mission_id,
                ),
            )
        return item

    def list_postcards(self, pet_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM postcards WHERE pet_id = ? ORDER BY timestamp DESC LIMIT ?",
                (pet_id, max(limit * 4, 40)),
            ).fetchall()
        return self._dedupe_postcards([self._postcard_from_row(row) for row in rows], limit=limit)

    def find_postcard_by_mission(self, pet_id: str, mission_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM postcards
                WHERE pet_id = ? AND mission_id = ?
                ORDER BY timestamp DESC
                """,
                (pet_id, mission_id),
            ).fetchall()
        for row in rows:
            postcard = self._postcard_from_row(row)
            if not self._is_time_inconsistent_postcard(postcard):
                return postcard
        return None

    def latest_postcard(self, pet_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM postcards WHERE pet_id = ? ORDER BY timestamp DESC LIMIT 20",
                (pet_id,),
            ).fetchall()
        for row in rows:
            postcard = self._postcard_from_row(row)
            if not self._is_time_inconsistent_postcard(postcard):
                return postcard
        return None

    def count_postcards(self, pet_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM postcards WHERE pet_id = ?", (pet_id,)).fetchone()
        return int(row["count"])

    def save_feedback(self, pet_id: str, city: str, liked: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO feedback (id, pet_id, city, liked, timestamp) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), pet_id, city, 1 if liked else 0, iso(utcnow())),
            )

    def _thought_from_row(self, row: sqlite3.Row, include_translation: bool = False) -> dict[str, Any]:
        return {
            "id": row["id"],
            "text": row["text"],
            "tone": row["tone"],
            "timestamp": parse_dt(row["timestamp"]),
            "animal_text": row["animal_text"],
            "translation_available": bool(row["translation_available"]),
            "translation": row["translation"] if include_translation else None,
            "language_style": row["language_style"] or "human",
            "model": row["model"],
        }

    def _event_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "detail": row["detail"],
            "timestamp": parse_dt(row["timestamp"]),
        }

    def _postcard_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "location": row["location"],
            "text": row["text"],
            "weather": row["weather"],
            "happiness": int(row["happiness"]),
            "timestamp": parse_dt(row["timestamp"]),
            "image_url": row["image_url"],
            "is_new": bool(row["is_new"]),
            "mission_id": row["mission_id"] if "mission_id" in row.keys() else None,
        }

    def _dedupe_postcards(self, postcards: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen_missions: set[str] = set()
        recent_gap = timedelta(minutes=20)
        for postcard in postcards:
            if self._is_time_inconsistent_postcard(postcard):
                continue
            mission_id = postcard.get("mission_id")
            if isinstance(mission_id, str) and mission_id:
                if mission_id in seen_missions:
                    continue
                seen_missions.add(mission_id)
            timestamp = postcard["timestamp"]
            if any(abs(existing["timestamp"] - timestamp) < recent_gap for existing in deduped):
                continue
            deduped.append(postcard)
            if len(deduped) >= limit:
                break
        return deduped

    def _is_time_inconsistent_postcard(self, postcard: dict[str, Any]) -> bool:
        return is_time_inconsistent_postcard(
            str(postcard.get("location") or ""),
            str(postcard.get("text") or ""),
            postcard["timestamp"],
        )
