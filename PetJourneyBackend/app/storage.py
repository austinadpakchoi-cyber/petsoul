"""聚合门面：`JourneyStorage` 通过多重继承组合各 Repository mixin。

拆分原因：原文件单类 1672 行 / 90 方法 / 22 表，属于 God File 反模式。
方法按聚合根拆分到 `app/repositories/` 下的多个 mixin，本文件仅做聚合与符号
re-export，对外 API 保持不变——历史调用方 `from app.storage import JourneyStorage`
（以及 `PetRecord` / `UserRecord` / `EconomyStorageConflict` / `PetOwnershipConflict`
/ `utcnow` / `iso` / `parse_dt`）继续可用。
"""

from __future__ import annotations

from pathlib import Path

from .repositories.base import SchemaInitializerMixin, StorageBaseMixin
from .repositories.economy import EconomyRepositoryMixin
from .repositories.engine_trace import EngineTraceRepositoryMixin
from .repositories.journal import JournalRepositoryMixin
from .repositories.memory import MemoryRepositoryMixin
from .repositories.notifications import NotificationRepositoryMixin
from .repositories.pets import PetRepositoryMixin
from .repositories.records import (
    EconomyStorageConflict,
    PetOwnershipConflict,
    PetRecord,
    UserRecord,
)
from .repositories.scheduler import SchedulerRepositoryMixin
from .repositories.travel import TravelRepositoryMixin
from .repositories.users import UserRepositoryMixin
from .utils import iso, parse_dt, utcnow  # noqa: F401  透传给历史调用方


class JourneyStorage(
    StorageBaseMixin,
    SchemaInitializerMixin,
    UserRepositoryMixin,
    PetRepositoryMixin,
    JournalRepositoryMixin,
    TravelRepositoryMixin,
    EconomyRepositoryMixin,
    NotificationRepositoryMixin,
    MemoryRepositoryMixin,
    EngineTraceRepositoryMixin,
    SchedulerRepositoryMixin,
):
    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()
