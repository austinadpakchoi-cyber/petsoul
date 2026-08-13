"""记忆存储工厂：按配置选择 Postgres pgvector 或本地 SQLite。"""

from __future__ import annotations

from ..config import Settings
from ..storage import JourneyStorage
from .postgres import PostgresPgVectorMemoryStore
from .protocols import MemoryStore
from .sqlite import SQLiteMemoryStore


def build_memory_store(storage: JourneyStorage, settings: Settings) -> MemoryStore:
    if settings.memory_provider == "postgres" and settings.postgres_dsn:
        return PostgresPgVectorMemoryStore(storage, settings)
    return SQLiteMemoryStore(storage, settings)
