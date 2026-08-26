"""底层 SQLite 连接与 schema 管理，从 storage.py 抽离。

- StorageBaseMixin：连接原语（connect / _ensure_column）。
- SchemaInitializerMixin：建表 + 迁移 + 索引（init_schema）。

JourneyStorage 多重继承这两个 mixin，`self.connect()` / `self._ensure_column()`
在运行时从 StorageBaseMixin 解析。
"""

from __future__ import annotations

from pathlib import Path
import sqlite3


class _ClosingConnection(sqlite3.Connection):
    """退出 `with` 块时额外 close 的 SQLite 连接。

    Python 的 ``sqlite3.Connection`` 上下文管理器只 commit/rollback，不会 close；
    在 Windows 上这会让数据库文件一直被占用（WinError 32），直到连接对象被
    循环 GC 回收。这里在退出 `with` 时显式 close，保证文件句柄立即释放。
    """

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            super().__exit__(exc_type, exc_val, exc_tb)
        finally:
            self.close()


class StorageBaseMixin:
    """提供底层 SQLite 连接与 schema 迁移原语。"""

    database_path: Path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path, factory=_ClosingConnection)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        if any(row["name"] == column for row in rows):
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


class SchemaInitializerMixin:
    """建表 + 列迁移 + 索引。依赖 StorageBaseMixin 的 connect / _ensure_column。"""

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

                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    apple_sub TEXT UNIQUE,
                    email TEXT,
                    display_name TEXT,
                    created_at TEXT NOT NULL
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
            self._ensure_column(conn, "pets", "owner_user_id", "TEXT")
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
            self._ensure_column(conn, "communicator_messages", "client_message_id", "TEXT")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_communicator_messages_pet_client "
                "ON communicator_messages (pet_id, client_message_id) WHERE client_message_id IS NOT NULL"
            )
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
