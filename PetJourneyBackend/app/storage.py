from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
import uuid

from .meal_rules import is_time_inconsistent_postcard
from .schemas import (
    CurrencyAmounts,
    EconomySnapshot,
    EconomyTransaction,
    EconomyTransactionType,
    JourneyEngineTrace,
    ItemStatus,
    OwnerFund,
    PetDNA,
    PetType,
    SouvenirItem,
    TradePolicy,
    TravelBag,
    TravelQuest,
    Wallet,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass(slots=True)
class PetRecord:
    pet_id: str
    name: str
    pet_type: PetType
    dna: PetDNA
    created_at: datetime
    photo_path: str | None


class EconomyStorageConflict(Exception):
    pass


class JourneyStorage:
    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS pets (
                    pet_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    pet_type TEXT NOT NULL,
                    dna_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    photo_path TEXT
                );

                CREATE TABLE IF NOT EXISTS thoughts (
                    id TEXT PRIMARY KEY,
                    pet_id TEXT NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
                    text TEXT NOT NULL,
                    tone TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    animal_text TEXT,
                    translation TEXT,
                    translation_available INTEGER NOT NULL DEFAULT 0,
                    language_style TEXT NOT NULL DEFAULT 'human',
                    model TEXT
                );

                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    pet_id TEXT NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS postcards (
                    id TEXT PRIMARY KEY,
                    pet_id TEXT NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
                    location TEXT NOT NULL,
                    text TEXT NOT NULL,
                    weather TEXT NOT NULL,
                    happiness INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    image_url TEXT,
                    is_new INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS feedback (
                    id TEXT PRIMARY KEY,
                    pet_id TEXT NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
                    city TEXT NOT NULL,
                    liked INTEGER NOT NULL,
                    timestamp TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS device_tokens (
                    id TEXT PRIMARY KEY,
                    pet_id TEXT NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
                    device_token TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(device_token, platform, environment)
                );

                CREATE TABLE IF NOT EXISTS notification_deliveries (
                    id TEXT PRIMARY KEY,
                    pet_id TEXT NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
                    device_token TEXT,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    category TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    status TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    error TEXT
                );

                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    pet_id TEXT NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    salience REAL NOT NULL,
                    source TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS engine_traces (
                    id TEXT PRIMARY KEY,
                    pet_id TEXT NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
                    operation TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    state_before_json TEXT NOT NULL DEFAULT '{}',
                    state_after_json TEXT NOT NULL DEFAULT '{}',
                    errors_json TEXT NOT NULL DEFAULT '[]',
                    fallbacks_json TEXT NOT NULL DEFAULT '[]'
                );

                CREATE TABLE IF NOT EXISTS scheduler_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS travel_quests (
                    id TEXT PRIMARY KEY,
                    pet_id TEXT NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS travel_bags (
                    id TEXT PRIMARY KEY,
                    pet_id TEXT NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
                    quest_id TEXT,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS souvenirs (
                    id TEXT PRIMARY KEY,
                    pet_id TEXT NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
                    quest_id TEXT,
                    item_type TEXT NOT NULL,
                    city TEXT NOT NULL,
                    place_name TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    obtained_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'owned',
                    trade_policy TEXT NOT NULL DEFAULT 'tradable',
                    market_value INTEGER NOT NULL DEFAULT 0,
                    emotional_value INTEGER NOT NULL DEFAULT 0,
                    honor_value INTEGER NOT NULL DEFAULT 0,
                    lock_until TEXT,
                    version INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT,
                    origin_event_id TEXT
                );

                CREATE TABLE IF NOT EXISTS pet_wallets (
                    pet_id TEXT PRIMARY KEY REFERENCES pets(pet_id) ON DELETE CASCADE,
                    travel_coin INTEGER NOT NULL DEFAULT 0,
                    star_dust INTEGER NOT NULL DEFAULT 0,
                    merit INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS owner_funds (
                    pet_id TEXT PRIMARY KEY REFERENCES pets(pet_id) ON DELETE CASCADE,
                    star_dust INTEGER NOT NULL DEFAULT 0,
                    project_budget INTEGER NOT NULL DEFAULT 0,
                    cosmetic_budget INTEGER NOT NULL DEFAULT 0,
                    travel_opportunity_budget INTEGER NOT NULL DEFAULT 0,
                    daily_coin_limit INTEGER NOT NULL DEFAULT 300,
                    coin_inflow_today INTEGER NOT NULL DEFAULT 0,
                    coin_inflow_date TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS economy_snapshots (
                    pet_id TEXT PRIMARY KEY REFERENCES pets(pet_id) ON DELETE CASCADE,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS economy_transactions (
                    tx_id TEXT PRIMARY KEY,
                    pet_id TEXT NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
                    type TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    amounts_json TEXT NOT NULL,
                    item_ids_json TEXT NOT NULL,
                    before_json TEXT NOT NULL,
                    after_json TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS communicator_messages (
                    id TEXT PRIMARY KEY,
                    pet_id TEXT NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
                    sender TEXT NOT NULL,
                    intent TEXT,
                    message_state TEXT NOT NULL,
                    text TEXT NOT NULL,
                    related_message_id TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS communicator_pending_requests (
                    id TEXT PRIMARY KEY,
                    pet_id TEXT NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
                    source_message_id TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    pending_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    scene_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    available_after TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS communicator_moments (
                    id TEXT PRIMARY KEY,
                    pet_id TEXT NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
                    source_type TEXT NOT NULL,
                    source_event_id TEXT,
                    text TEXT NOT NULL,
                    city TEXT,
                    place_name TEXT,
                    lat REAL,
                    lng REAL,
                    mood TEXT,
                    scene_hash TEXT,
                    attachments_json TEXT NOT NULL,
                    reactions_json TEXT NOT NULL,
                    owner_reaction TEXT,
                    is_read INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS communicator_moment_reactions (
                    id TEXT PRIMARY KEY,
                    moment_id TEXT NOT NULL REFERENCES communicator_moments(id) ON DELETE CASCADE,
                    pet_id TEXT NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
                    reaction TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(moment_id, pet_id)
                );
                """
            )
            self._ensure_column(conn, "thoughts", "animal_text", "TEXT")
            self._ensure_column(conn, "thoughts", "translation", "TEXT")
            self._ensure_column(conn, "thoughts", "translation_available", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "thoughts", "language_style", "TEXT NOT NULL DEFAULT 'human'")
            self._ensure_column(conn, "thoughts", "model", "TEXT")
            self._ensure_column(conn, "postcards", "mission_id", "TEXT")
            self._ensure_column(conn, "memories", "memory_type", "TEXT NOT NULL DEFAULT 'episodic'")
            self._ensure_column(conn, "memories", "importance", "REAL NOT NULL DEFAULT 0.5")
            self._ensure_column(conn, "memories", "emotional_valence", "REAL NOT NULL DEFAULT 0.0")
            self._ensure_column(conn, "memories", "confidence", "REAL NOT NULL DEFAULT 1.0")
            self._ensure_column(conn, "memories", "source_event_id", "TEXT")
            self._ensure_column(conn, "memories", "structured_payload_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "souvenirs", "status", "TEXT NOT NULL DEFAULT 'owned'")
            self._ensure_column(conn, "souvenirs", "trade_policy", "TEXT NOT NULL DEFAULT 'tradable'")
            self._ensure_column(conn, "souvenirs", "market_value", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "souvenirs", "emotional_value", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "souvenirs", "honor_value", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "souvenirs", "lock_until", "TEXT")
            self._ensure_column(conn, "souvenirs", "version", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "souvenirs", "updated_at", "TEXT")
            self._ensure_column(conn, "souvenirs", "origin_event_id", "TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_postcards_pet_mission ON postcards (pet_id, mission_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_pet_type_seen ON memories (pet_id, memory_type, last_seen_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_engine_traces_pet_started ON engine_traces (pet_id, started_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_travel_quests_pet_updated ON travel_quests (pet_id, updated_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_travel_bags_pet_quest ON travel_bags (pet_id, quest_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_souvenirs_pet_obtained ON souvenirs (pet_id, obtained_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_souvenirs_pet_status ON souvenirs (pet_id, status, obtained_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_souvenirs_pet_trade ON souvenirs (pet_id, trade_policy, status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_souvenirs_pet_value ON souvenirs (pet_id, market_value DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_economy_transactions_pet_created ON economy_transactions (pet_id, created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_economy_transactions_pet_type ON economy_transactions (pet_id, type, created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_communicator_messages_pet_created ON communicator_messages (pet_id, created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_communicator_pending_pet_status ON communicator_pending_requests (pet_id, status, available_after)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_communicator_moments_pet_created ON communicator_moments (pet_id, created_at)")

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        if any(row["name"] == column for row in rows):
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

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

    def get_wallet(self, pet_id: str) -> Wallet | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM pet_wallets WHERE pet_id = ?", (pet_id,)).fetchone()
        return self._wallet_from_row(row) if row else None

    def ensure_wallet(self, pet_id: str, now: datetime | None = None) -> Wallet:
        timestamp = now or utcnow()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM pet_wallets WHERE pet_id = ?", (pet_id,)).fetchone()
            if not row:
                wallet = Wallet(pet_id=pet_id, updated_at=timestamp)
                self._upsert_wallet(conn, wallet)
                return wallet
        return self._wallet_from_row(row)

    def get_owner_fund(self, pet_id: str) -> OwnerFund | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM owner_funds WHERE pet_id = ?", (pet_id,)).fetchone()
        return self._owner_fund_from_row(row) if row else None

    def ensure_owner_fund(self, pet_id: str, daily_coin_limit: int = 300, now: datetime | None = None) -> OwnerFund:
        timestamp = now or utcnow()
        today = timestamp.date()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM owner_funds WHERE pet_id = ?", (pet_id,)).fetchone()
            if not row:
                fund = OwnerFund(
                    pet_id=pet_id,
                    daily_coin_limit=daily_coin_limit,
                    coin_inflow_date=today,
                    updated_at=timestamp,
                )
                self._upsert_owner_fund(conn, fund)
                return fund
        return self._owner_fund_from_row(row)

    def get_economy_snapshot(self, pet_id: str) -> EconomySnapshot | None:
        with self.connect() as conn:
            row = conn.execute("SELECT payload_json FROM economy_snapshots WHERE pet_id = ?", (pet_id,)).fetchone()
        return EconomySnapshot.model_validate(json.loads(row["payload_json"])) if row else None

    def save_economy_snapshot(self, snapshot: EconomySnapshot) -> EconomySnapshot:
        with self.connect() as conn:
            self._upsert_economy_snapshot(conn, snapshot)
        return snapshot

    def get_transaction_by_idempotency_key(self, idempotency_key: str) -> EconomyTransaction | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM economy_transactions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        return self._economy_transaction_from_row(row) if row else None

    def list_economy_transactions(self, pet_id: str, limit: int = 20) -> list[EconomyTransaction]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM economy_transactions
                WHERE pet_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (pet_id, max(1, min(100, limit))),
            ).fetchall()
        return [self._economy_transaction_from_row(row) for row in rows]

    def list_all_economy_transactions(self, pet_id: str) -> list[EconomyTransaction]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM economy_transactions
                WHERE pet_id = ?
                ORDER BY created_at ASC, tx_id ASC
                """,
                (pet_id,),
            ).fetchall()
        return [self._economy_transaction_from_row(row) for row in rows]

    def save_economy_derived_state(
        self,
        *,
        wallet: Wallet,
        owner_fund: OwnerFund,
        snapshot: EconomySnapshot,
    ) -> None:
        with self.connect() as conn:
            self._upsert_wallet(conn, wallet)
            self._upsert_owner_fund(conn, owner_fund)
            self._upsert_economy_snapshot(conn, snapshot)

    def clear_economy_derived_state(self, pet_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM pet_wallets WHERE pet_id = ?", (pet_id,))
            conn.execute("DELETE FROM owner_funds WHERE pet_id = ?", (pet_id,))
            conn.execute("DELETE FROM economy_snapshots WHERE pet_id = ?", (pet_id,))

    def commit_economy_state(
        self,
        *,
        transaction: EconomyTransaction,
        wallet: Wallet | None = None,
        owner_fund: OwnerFund | None = None,
        snapshot: EconomySnapshot | None = None,
        souvenirs: list[SouvenirItem] | None = None,
        expected_item_versions: dict[str, int] | None = None,
    ) -> EconomyTransaction:
        with self.connect() as conn:
            self._insert_economy_transaction(conn, transaction)
            if wallet is not None:
                self._upsert_wallet(conn, wallet)
            if owner_fund is not None:
                self._upsert_owner_fund(conn, owner_fund)
            for item in souvenirs or []:
                expected_version = (expected_item_versions or {}).get(item.id)
                if expected_version is None:
                    self._upsert_souvenir(conn, item)
                else:
                    self._update_souvenir_with_version(conn, item, expected_version=expected_version)
            if snapshot is not None:
                self._upsert_economy_snapshot(conn, snapshot)
        return transaction

    def travel_bag_id(self, pet_id: str, quest_id: str | None = None) -> str:
        key = quest_id or "main"
        return f"TB-{pet_id}-{key}"

    def upsert_device_token(self, pet_id: str, device_token: str, platform: str, environment: str) -> dict[str, Any]:
        now = utcnow()
        device_id = str(uuid.uuid4())
        with self.connect() as conn:
            existing = conn.execute(
                """
                SELECT id FROM device_tokens
                WHERE device_token = ? AND platform = ? AND environment = ?
                """,
                (device_token, platform, environment),
            ).fetchone()
            if existing:
                device_id = existing["id"]
                conn.execute(
                    """
                    UPDATE device_tokens
                    SET pet_id = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (pet_id, iso(now), device_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO device_tokens (
                        id, pet_id, device_token, platform, environment, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (device_id, pet_id, device_token, platform, environment, iso(now), iso(now)),
                )
        return {
            "id": device_id,
            "pet_id": pet_id,
            "device_token": device_token,
            "platform": platform,
            "environment": environment,
            "created_at": now,
            "updated_at": now,
        }

    def remove_device_token(self, device_token: str, platform: str = "ios") -> None:
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM device_tokens WHERE device_token = ? AND platform = ?",
                (device_token, platform),
            )

    def list_device_tokens(self, pet_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM device_tokens WHERE pet_id = ? ORDER BY updated_at DESC",
                (pet_id,),
            ).fetchall()
        return [self._device_token_from_row(row) for row in rows]

    def record_notification_delivery(
        self,
        *,
        pet_id: str,
        device_token: str | None,
        title: str,
        body: str,
        category: str,
        provider: str,
        status: str,
        error: str | None = None,
        timestamp: datetime | None = None,
    ) -> dict[str, Any]:
        item = {
            "id": str(uuid.uuid4()),
            "pet_id": pet_id,
            "device_token": device_token,
            "title": title,
            "body": body,
            "category": category,
            "provider": provider,
            "status": status,
            "timestamp": timestamp or utcnow(),
            "error": error,
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO notification_deliveries (
                    id, pet_id, device_token, title, body, category, provider, status, timestamp, error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["id"],
                    pet_id,
                    device_token,
                    title,
                    body,
                    category,
                    provider,
                    status,
                    iso(item["timestamp"]),
                    error,
                ),
            )
        return item

    def list_notification_deliveries(self, pet_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM notification_deliveries
                WHERE pet_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (pet_id, limit),
            ).fetchall()
        return [self._notification_from_row(row) for row in rows]

    def save_engine_trace(self, trace: JourneyEngineTrace) -> JourneyEngineTrace:
        payload = trace.model_dump(mode="json")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO engine_traces (
                    id, pet_id, operation, status, started_at, finished_at,
                    steps_json, state_before_json, state_after_json, errors_json, fallbacks_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace.id,
                    trace.pet_id,
                    trace.operation,
                    trace.status,
                    iso(trace.started_at),
                    iso(trace.finished_at),
                    json.dumps(payload["steps"], ensure_ascii=False),
                    json.dumps(payload["state_before"], ensure_ascii=False),
                    json.dumps(payload["state_after"], ensure_ascii=False),
                    json.dumps(payload["errors"], ensure_ascii=False),
                    json.dumps(payload["fallbacks"], ensure_ascii=False),
                ),
            )
        return trace

    def list_engine_traces(self, pet_id: str, limit: int = 20) -> list[JourneyEngineTrace]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM engine_traces
                WHERE pet_id = ?
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (pet_id, max(1, min(200, limit))),
            ).fetchall()
        return [self._engine_trace_from_row(row) for row in rows]

    def get_engine_trace(self, pet_id: str, trace_id: str) -> JourneyEngineTrace | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM engine_traces
                WHERE pet_id = ? AND id = ?
                """,
                (pet_id, trace_id),
            ).fetchone()
        return self._engine_trace_from_row(row) if row else None

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

    def set_scheduler_state(self, key: str, value: str, timestamp: datetime | None = None) -> None:
        now = timestamp or utcnow()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO scheduler_state (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, value, iso(now)),
            )

    def get_scheduler_state(self, key: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM scheduler_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def _upsert_souvenir(self, conn: sqlite3.Connection, item: SouvenirItem) -> None:
        payload = item.model_dump(mode="json", by_alias=True)
        updated_at = item.updated_at or item.obtained_at
        conn.execute(
            """
            INSERT INTO souvenirs (
                id, pet_id, quest_id, item_type, city, place_name, payload_json, obtained_at,
                status, trade_policy, market_value, emotional_value, honor_value,
                lock_until, version, updated_at, origin_event_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                item_type = excluded.item_type,
                city = excluded.city,
                place_name = excluded.place_name,
                payload_json = excluded.payload_json,
                obtained_at = excluded.obtained_at,
                status = excluded.status,
                trade_policy = excluded.trade_policy,
                market_value = excluded.market_value,
                emotional_value = excluded.emotional_value,
                honor_value = excluded.honor_value,
                lock_until = excluded.lock_until,
                version = excluded.version,
                updated_at = excluded.updated_at,
                origin_event_id = excluded.origin_event_id
            """,
            self._souvenir_sql_values(item, payload=payload, updated_at=updated_at),
        )

    def _update_souvenir_with_version(self, conn: sqlite3.Connection, item: SouvenirItem, expected_version: int) -> None:
        payload = item.model_dump(mode="json", by_alias=True)
        updated_at = item.updated_at or utcnow()
        cursor = conn.execute(
            """
            UPDATE souvenirs
            SET item_type = ?,
                city = ?,
                place_name = ?,
                payload_json = ?,
                obtained_at = ?,
                status = ?,
                trade_policy = ?,
                market_value = ?,
                emotional_value = ?,
                honor_value = ?,
                lock_until = ?,
                version = ?,
                updated_at = ?,
                origin_event_id = ?
            WHERE id = ? AND pet_id = ? AND version = ?
            """,
            (
                item.item_type.value,
                item.city,
                item.place_name,
                json.dumps(payload, ensure_ascii=False),
                iso(item.obtained_at),
                item.status.value,
                item.trade_policy.value,
                item.market_value,
                item.emotional_value,
                item.honor_value,
                iso(item.lock_until) if item.lock_until else None,
                item.version,
                iso(updated_at),
                item.origin_event_id,
                item.id,
                item.pet_id,
                expected_version,
            ),
        )
        if cursor.rowcount != 1:
            raise EconomyStorageConflict(item.id)

    def _souvenir_sql_values(self, item: SouvenirItem, *, payload: dict[str, Any], updated_at: datetime) -> tuple[Any, ...]:
        return (
            item.id,
            item.pet_id,
            item.quest_id,
            item.item_type.value,
            item.city,
            item.place_name,
            json.dumps(payload, ensure_ascii=False),
            iso(item.obtained_at),
            item.status.value,
            item.trade_policy.value,
            item.market_value,
            item.emotional_value,
            item.honor_value,
            iso(item.lock_until) if item.lock_until else None,
            item.version,
            iso(updated_at),
            item.origin_event_id,
        )

    def _upsert_wallet(self, conn: sqlite3.Connection, wallet: Wallet) -> None:
        conn.execute(
            """
            INSERT INTO pet_wallets (pet_id, travel_coin, star_dust, merit, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(pet_id) DO UPDATE SET
                travel_coin = excluded.travel_coin,
                star_dust = excluded.star_dust,
                merit = excluded.merit,
                updated_at = excluded.updated_at
            """,
            (wallet.pet_id, wallet.travel_coin, wallet.star_dust, wallet.merit, iso(wallet.updated_at)),
        )

    def _upsert_owner_fund(self, conn: sqlite3.Connection, fund: OwnerFund) -> None:
        conn.execute(
            """
            INSERT INTO owner_funds (
                pet_id, star_dust, project_budget, cosmetic_budget, travel_opportunity_budget,
                daily_coin_limit, coin_inflow_today, coin_inflow_date, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(pet_id) DO UPDATE SET
                star_dust = excluded.star_dust,
                project_budget = excluded.project_budget,
                cosmetic_budget = excluded.cosmetic_budget,
                travel_opportunity_budget = excluded.travel_opportunity_budget,
                daily_coin_limit = excluded.daily_coin_limit,
                coin_inflow_today = excluded.coin_inflow_today,
                coin_inflow_date = excluded.coin_inflow_date,
                updated_at = excluded.updated_at
            """,
            (
                fund.pet_id,
                fund.star_dust,
                fund.project_budget,
                fund.cosmetic_budget,
                fund.travel_opportunity_budget,
                fund.daily_coin_limit,
                fund.coin_inflow_today,
                fund.coin_inflow_date.isoformat(),
                iso(fund.updated_at),
            ),
        )

    def _upsert_economy_snapshot(self, conn: sqlite3.Connection, snapshot: EconomySnapshot) -> None:
        payload = snapshot.model_dump(mode="json", by_alias=True)
        conn.execute(
            """
            INSERT INTO economy_snapshots (pet_id, payload_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(pet_id) DO UPDATE SET
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (snapshot.pet_id, json.dumps(payload, ensure_ascii=False), iso(snapshot.updated_at)),
        )

    def _insert_economy_transaction(self, conn: sqlite3.Connection, transaction: EconomyTransaction) -> None:
        payload = transaction.model_dump(mode="json", by_alias=True)
        conn.execute(
            """
            INSERT INTO economy_transactions (
                tx_id, pet_id, type, idempotency_key, amounts_json, item_ids_json,
                before_json, after_json, reason, operator, source, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transaction.tx_id,
                transaction.pet_id,
                transaction.type.value,
                transaction.idempotency_key,
                json.dumps(payload["amounts"], ensure_ascii=False),
                json.dumps(payload["item_ids"], ensure_ascii=False),
                json.dumps(payload["before"], ensure_ascii=False),
                json.dumps(payload["after"], ensure_ascii=False),
                transaction.reason,
                transaction.operator,
                transaction.source,
                transaction.status,
                iso(transaction.created_at),
            ),
        )

    def _wallet_from_row(self, row: sqlite3.Row) -> Wallet:
        return Wallet(
            pet_id=row["pet_id"],
            travel_coin=int(row["travel_coin"]),
            star_dust=int(row["star_dust"]),
            merit=int(row["merit"]),
            updated_at=parse_dt(row["updated_at"]),
        )

    def _owner_fund_from_row(self, row: sqlite3.Row) -> OwnerFund:
        return OwnerFund(
            pet_id=row["pet_id"],
            star_dust=int(row["star_dust"]),
            project_budget=int(row["project_budget"]),
            cosmetic_budget=int(row["cosmetic_budget"]),
            travel_opportunity_budget=int(row["travel_opportunity_budget"]),
            daily_coin_limit=int(row["daily_coin_limit"]),
            coin_inflow_today=int(row["coin_inflow_today"]),
            coin_inflow_date=datetime.fromisoformat(row["coin_inflow_date"]).date(),
            updated_at=parse_dt(row["updated_at"]),
        )

    def _economy_transaction_from_row(self, row: sqlite3.Row) -> EconomyTransaction:
        return EconomyTransaction(
            tx_id=row["tx_id"],
            pet_id=row["pet_id"],
            type=EconomyTransactionType(row["type"]),
            idempotency_key=row["idempotency_key"],
            amounts=CurrencyAmounts.model_validate(json.loads(row["amounts_json"] or "{}")),
            item_ids=list(json.loads(row["item_ids_json"] or "[]")),
            before=json.loads(row["before_json"] or "{}"),
            after=json.loads(row["after_json"] or "{}"),
            reason=row["reason"],
            operator=row["operator"],
            source=row["source"],
            status=row["status"],
            created_at=parse_dt(row["created_at"]),
        )

    def _pet_from_row(self, row: sqlite3.Row) -> PetRecord:
        return PetRecord(
            pet_id=row["pet_id"],
            name=row["name"],
            pet_type=PetType(row["pet_type"]),
            dna=PetDNA.model_validate(json.loads(row["dna_json"])),
            created_at=parse_dt(row["created_at"]),
            photo_path=row["photo_path"],
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

    def _device_token_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "pet_id": row["pet_id"],
            "device_token": row["device_token"],
            "platform": row["platform"],
            "environment": row["environment"],
            "created_at": parse_dt(row["created_at"]),
            "updated_at": parse_dt(row["updated_at"]),
        }

    def _notification_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "pet_id": row["pet_id"],
            "device_token": row["device_token"],
            "title": row["title"],
            "body": row["body"],
            "category": row["category"],
            "provider": row["provider"],
            "status": row["status"],
            "timestamp": parse_dt(row["timestamp"]),
            "error": row["error"],
        }

    def _engine_trace_from_row(self, row: sqlite3.Row) -> JourneyEngineTrace:
        return JourneyEngineTrace.model_validate(
            {
                "id": row["id"],
                "pet_id": row["pet_id"],
                "operation": row["operation"],
                "status": row["status"],
                "started_at": parse_dt(row["started_at"]),
                "finished_at": parse_dt(row["finished_at"]),
                "steps": json.loads(row["steps_json"] or "[]"),
                "state_before": json.loads(row["state_before_json"] or "{}"),
                "state_after": json.loads(row["state_after_json"] or "{}"),
                "errors": json.loads(row["errors_json"] or "[]"),
                "fallbacks": json.loads(row["fallbacks_json"] or "[]"),
            }
        )

    def _memory_from_row(self, row: sqlite3.Row, include_embedding: bool = False) -> dict[str, Any]:
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
