"""领域记录与异常：从 storage.py 顶部抽离，供各 Repository mixin 共享。

单独成文件是为了避免 storage.py（聚合门面）与各 mixin 之间产生循环 import。
这些符号会由 storage.py 重新导出，历史调用方 `from app.storage import PetRecord` 不受影响。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..schemas import PetDNA, PetType


@dataclass(slots=True)
class PetRecord:
    pet_id: str
    name: str
    pet_type: PetType
    dna: PetDNA
    created_at: datetime
    photo_path: str | None
    owner_user_id: str | None = None


class EconomyStorageConflict(Exception):
    pass


class PetOwnershipConflict(Exception):
    pass


@dataclass(slots=True)
class UserRecord:
    user_id: str
    apple_sub: str | None
    email: str | None
    display_name: str | None
    created_at: datetime
