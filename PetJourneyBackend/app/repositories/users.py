"""用户聚合 Repository mixin：账号、宠物归属（claim）。

方法从原 app/storage.py 原样搬移，`self.connect()` / `self.get_pet()` 在
JourneyStorage 多重继承下于运行时解析。
"""

from __future__ import annotations

import sqlite3
import uuid

from ..utils import iso, parse_dt, utcnow
from .records import PetOwnershipConflict, PetRecord, UserRecord


class UserRepositoryMixin:
    def upsert_user_by_apple_sub(
        self,
        apple_sub: str,
        email: str | None,
        display_name: str | None,
    ) -> tuple[UserRecord, bool]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE apple_sub = ?", (apple_sub,)
            ).fetchone()
            if row is not None:
                # Apple 只在首次授权时返回姓名/邮箱，后续登录补全缺失字段
                if (display_name and not row["display_name"]) or (email and not row["email"]):
                    conn.execute(
                        "UPDATE users SET display_name = COALESCE(display_name, ?), email = COALESCE(email, ?) WHERE user_id = ?",
                        (display_name, email, row["user_id"]),
                    )
                    row = conn.execute(
                        "SELECT * FROM users WHERE user_id = ?", (row["user_id"],)
                    ).fetchone()
                return self._user_from_row(row), False

            user_id = f"PU-{uuid.uuid4().hex[:8].upper()}"
            created_at = utcnow()
            conn.execute(
                "INSERT INTO users (user_id, apple_sub, email, display_name, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, apple_sub, email, display_name, iso(created_at)),
            )
            return (
                UserRecord(
                    user_id=user_id,
                    apple_sub=apple_sub,
                    email=email,
                    display_name=display_name,
                    created_at=created_at,
                ),
                True,
            )

    def get_user(self, user_id: str) -> UserRecord | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        return None if row is None else self._user_from_row(row)

    def list_pets_for_user(self, user_id: str) -> list[PetRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM pets WHERE owner_user_id = ? ORDER BY created_at",
                (user_id,),
            ).fetchall()
        return [self._pet_from_row(row) for row in rows]

    def claim_pet(self, pet_id: str, user_id: str) -> PetRecord:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM pets WHERE pet_id = ?", (pet_id,)
            ).fetchone()
            if row is None:
                raise KeyError(pet_id)
            current_owner = row["owner_user_id"]
            if current_owner is not None and current_owner != user_id:
                raise PetOwnershipConflict(
                    f"pet {pet_id} already belongs to another user"
                )
            if current_owner is None:
                conn.execute(
                    "UPDATE pets SET owner_user_id = ? WHERE pet_id = ?",
                    (user_id, pet_id),
                )
        pet = self.get_pet(pet_id)
        assert pet is not None
        return pet

    @staticmethod
    def _user_from_row(row: sqlite3.Row) -> UserRecord:
        return UserRecord(
            user_id=row["user_id"],
            apple_sub=row["apple_sub"],
            email=row["email"],
            display_name=row["display_name"],
            created_at=parse_dt(row["created_at"]),
        )
