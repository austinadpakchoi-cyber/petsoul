"""记忆存储：SQLite / Postgres pgvector 双实现 + 门面 re-export。

历史导入面保持不变：
    from app.memory_store import MemoryStore, build_memory_store
"""

from .factory import build_memory_store
from .hash_embedding import HashEmbeddingProvider
from .postgres import PostgresPgVectorMemoryStore
from .protocols import EmbeddingProvider, MemoryStore
from .sqlite import SQLiteMemoryStore

__all__ = [
    "EmbeddingProvider",
    "MemoryStore",
    "HashEmbeddingProvider",
    "SQLiteMemoryStore",
    "PostgresPgVectorMemoryStore",
    "build_memory_store",
]
