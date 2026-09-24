"""用户 / 家庭 / 宠物的**只读**投影。

这里一行业务数据都不写。SQL 只 SELECT 既有表（users、web_accounts、web_households、web_household_members、
web_household_pets、pets、web_pet_profiles、web_homes、admin_account_flags），不复制第二套真相，也不缓存。

脱敏在投影层就做掉，不靠界面自觉：DNA 正文、私聊、叮嘱、参考图路径、口令哈希一律不出现在返回值里。
需要看这些要 `private.read`，本批没有任何角色带它（见 permissions.py），所以后台里根本取不到。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..storage import JourneyStorage
from ..utils import parse_dt
from ..web_identity.service import DEFAULT_TIMEZONE, MODEL_REPLIES_DEFAULT


@dataclass(frozen=True, slots=True)
class UserHit:
    user_id: str
    username: str | None
    display_name: str | None
    account_status: str          # active / frozen（平台处置状态）
    created_at: datetime | None
    household_count: int
    pet_count: int
    matched_on: str              # user_id / username / display_name / pet


@dataclass(frozen=True, slots=True)
class PetBrief:
    pet_id: str
    name: str
    species: str
    origin: str | None
    household_id: str | None
    home_activated: bool


@dataclass(frozen=True, slots=True)
class HouseholdBrief:
    household_id: str
    name: str | None
    role: str                    # 这位用户在这个家里的角色
    member_status: str
    created_at: datetime | None
    members: list[dict] = field(default_factory=list)
    pets: list[PetBrief] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class UserDetail:
    user: UserHit
    prefs: dict[str, Any]        # 用途授权（布尔）与时区；不含私人内容
    sessions: list[dict]
    households: list[HouseholdBrief]
    freeze: dict[str, Any] | None


def _dt(value) -> datetime | None:
    return parse_dt(value) if value else None


def owner_of_pet(conn: sqlite3.Connection, pet_id: str) -> str | None:
    """照顾这只宠物的人（管理员优先）。给授权复核与账本筛选用，同一份口径只写一次。"""
    row = conn.execute(CAREGIVERS_OF_PET, (pet_id,)).fetchone()
    return row["user_id"] if row else None


# 一位用户"有哪些宠物"的唯一口径：他参与照顾的家 → 那些家里的宠物。
# **不能用 `web_pet_profiles.user_id`**：领养来的居民那一列停在星球居民驿站的系统账号上
# （领养不改居民身份），用它算会得到 0 只宠物，也会把所有领养宠物都算到系统账号名下。
PETS_OF_USER = (
    "SELECT hp.pet_id FROM web_household_pets hp JOIN web_household_members m ON m.household_id = hp.household_id "
    "WHERE m.user_id = ? AND m.status = 'active'"
)
# 反过来：这只宠物属于哪个家，谁在照顾它（管理员优先）。
CAREGIVERS_OF_PET = (
    "SELECT m.user_id, m.role FROM web_household_pets hp JOIN web_household_members m ON m.household_id = hp.household_id "
    "WHERE hp.pet_id = ? AND m.status = 'active' ORDER BY CASE m.role WHEN 'admin' THEN 0 ELSE 1 END, m.joined_at"
)


class AdminDirectory:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage

    # ---- 检索 ----
    def search_users(self, query: str, limit: int = 25) -> list[UserHit]:
        term = (query or "").strip()
        if not term:
            return []
        like = f"%{term}%"
        with self.storage.connect() as conn:
            rows = conn.execute(
                """
                SELECT u.user_id,
                       CASE WHEN u.user_id = ? THEN 'user_id'
                            WHEN a.username_key = lower(?) THEN 'username'
                            WHEN a.username LIKE ? THEN 'username'
                            WHEN u.display_name LIKE ? THEN 'display_name'
                            ELSE 'pet' END AS matched_on
                FROM users u
                LEFT JOIN web_accounts a ON a.user_id = u.user_id
                WHERE u.user_id = ?
                   OR a.username LIKE ?
                   OR u.display_name LIKE ?
                   OR EXISTS (
                        SELECT 1 FROM web_household_pets hp
                        JOIN web_household_members m ON m.household_id = hp.household_id AND m.status = 'active'
                        LEFT JOIN pets pt ON pt.pet_id = hp.pet_id
                        WHERE m.user_id = u.user_id AND (hp.pet_id = ? OR pt.name LIKE ?)
                   )
                ORDER BY u.created_at DESC
                LIMIT ?
                """,
                (term, term, like, like, term, like, like, term, like, max(1, min(100, limit))),
            ).fetchall()
            return [self._hit(conn, row["user_id"], row["matched_on"]) for row in rows]

    def search_pets(self, query: str, limit: int = 25) -> list[dict]:
        term = (query or "").strip()
        if not term:
            return []
        like = f"%{term}%"
        with self.storage.connect() as conn:
            rows = conn.execute(
                """
                SELECT pt.pet_id, pt.name, COALESCE(p.species, pt.pet_type) AS species, p.origin, p.user_id,
                       hp.household_id
                FROM pets pt
                LEFT JOIN web_pet_profiles p ON p.pet_id = pt.pet_id
                LEFT JOIN web_household_pets hp ON hp.pet_id = pt.pet_id
                WHERE pt.pet_id = ? OR pt.name LIKE ?
                ORDER BY pt.created_at DESC LIMIT ?
                """,
                (term, like, max(1, min(100, limit))),
            ).fetchall()
            return [dict(row) for row in rows]

    # ---- 详情 ----
    def user_detail(self, user_id: str) -> UserDetail | None:
        with self.storage.connect() as conn:
            if conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone() is None:
                return None
            hit = self._hit(conn, user_id, "user_id")
            prefs_row = conn.execute(
                "SELECT model_replies, generated_photos, pet_messages, timezone, last_active_at FROM web_user_prefs WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            prefs = {
                # 没有偏好行＝从没选过，按身份模块的默认值显示（2026-09-24 起默认开启），与玩家设置页一致
                "model_replies": MODEL_REPLIES_DEFAULT if prefs_row is None else bool(prefs_row["model_replies"]),
                "generated_photos": bool(prefs_row and prefs_row["generated_photos"]),
                "pet_messages": True if prefs_row is None else bool(prefs_row["pet_messages"]),
                "timezone": (prefs_row["timezone"] if prefs_row else None) or DEFAULT_TIMEZONE,
                "last_active_at": _dt(prefs_row["last_active_at"]) if prefs_row else None,
            }
            sessions = [
                {"session_id": r["session_id"], "created_at": _dt(r["created_at"]), "expires_at": _dt(r["expires_at"]),
                 "revoked_at": _dt(r["revoked_at"])}
                for r in conn.execute(
                    "SELECT session_id, created_at, expires_at, revoked_at FROM web_sessions WHERE user_id = ? ORDER BY created_at DESC LIMIT 20",
                    (user_id,),
                )
            ]
            households = self._households_of(conn, user_id)
            flag = conn.execute("SELECT status, reason, changed_at, changed_by, version FROM admin_account_flags WHERE user_id = ?",
                                (user_id,)).fetchone()
            freeze = None if flag is None else {"status": flag["status"], "reason": flag["reason"], "changed_at": _dt(flag["changed_at"]),
                                                "changed_by": flag["changed_by"], "version": int(flag["version"])}
        return UserDetail(user=hit, prefs=prefs, sessions=sessions, households=households, freeze=freeze)

    def pet_owner(self, pet_id: str) -> str | None:
        """照顾这只宠物的人（家庭管理员优先）。没有家庭的待领养居民返回 None——它本来就没有主人。"""
        with self.storage.connect() as conn:
            return owner_of_pet(conn, pet_id)

    def caregivers(self, pet_id: str) -> list[dict]:
        with self.storage.connect() as conn:
            return [{"user_id": r["user_id"], "role": r["role"]} for r in conn.execute(CAREGIVERS_OF_PET, (pet_id,))]

    def pet_brief(self, pet_id: str) -> PetBrief | None:
        with self.storage.connect() as conn:
            row = conn.execute(
                """
                SELECT pt.pet_id, pt.name, COALESCE(p.species, pt.pet_type) AS species, p.origin, hp.household_id
                FROM pets pt LEFT JOIN web_pet_profiles p ON p.pet_id = pt.pet_id
                LEFT JOIN web_household_pets hp ON hp.pet_id = pt.pet_id WHERE pt.pet_id = ?
                """,
                (pet_id,),
            ).fetchone()
            if row is None:
                return None
            return self._pet(conn, row)

    # ---- 内部 ----
    def _hit(self, conn: sqlite3.Connection, user_id: str, matched_on: str) -> UserHit:
        row = conn.execute(
            "SELECT u.user_id, u.display_name, u.created_at, a.username FROM users u LEFT JOIN web_accounts a ON a.user_id = u.user_id "
            "WHERE u.user_id = ?", (user_id,)).fetchone()
        households = conn.execute("SELECT COUNT(*) AS n FROM web_household_members WHERE user_id = ? AND status = 'active'", (user_id,)).fetchone()["n"]
        pets = conn.execute(f"SELECT COUNT(*) AS n FROM ({PETS_OF_USER})", (user_id,)).fetchone()["n"]
        flag = conn.execute("SELECT status FROM admin_account_flags WHERE user_id = ?", (user_id,)).fetchone()
        return UserHit(user_id=user_id, username=row["username"] if row else None, display_name=row["display_name"] if row else None,
                       account_status=(flag["status"] if flag else "active"), created_at=_dt(row["created_at"]) if row else None,
                       household_count=int(households), pet_count=int(pets), matched_on=matched_on)

    def _households_of(self, conn: sqlite3.Connection, user_id: str) -> list[HouseholdBrief]:
        briefs: list[HouseholdBrief] = []
        for row in conn.execute(
            "SELECT h.household_id, h.name, h.created_at, m.role, m.status FROM web_household_members m "
            "JOIN web_households h ON h.household_id = m.household_id WHERE m.user_id = ? ORDER BY m.joined_at",
            (user_id,),
        ):
            members = [
                {"user_id": r["user_id"], "role": r["role"], "status": r["status"], "display_name": r["display_name"], "username": r["username"]}
                for r in conn.execute(
                    "SELECT m.user_id, m.role, m.status, u.display_name, a.username FROM web_household_members m "
                    "LEFT JOIN users u ON u.user_id = m.user_id LEFT JOIN web_accounts a ON a.user_id = m.user_id "
                    "WHERE m.household_id = ? ORDER BY m.joined_at",
                    (row["household_id"],),
                )
            ]
            pets = [
                self._pet(conn, r)
                for r in conn.execute(
                    "SELECT pt.pet_id, pt.name, COALESCE(p.species, pt.pet_type) AS species, p.origin, hp.household_id "
                    "FROM web_household_pets hp JOIN pets pt ON pt.pet_id = hp.pet_id "
                    "LEFT JOIN web_pet_profiles p ON p.pet_id = hp.pet_id WHERE hp.household_id = ? ORDER BY hp.position",
                    (row["household_id"],),
                )
            ]
            briefs.append(HouseholdBrief(household_id=row["household_id"], name=row["name"], role=row["role"], member_status=row["status"],
                                         created_at=_dt(row["created_at"]), members=members, pets=pets))
        return briefs

    def _pet(self, conn: sqlite3.Connection, row) -> PetBrief:
        home = conn.execute("SELECT activated_at FROM web_homes WHERE household_id = ?", (row["household_id"],)).fetchone() \
            if row["household_id"] else None
        return PetBrief(pet_id=row["pet_id"], name=row["name"], species=row["species"], origin=row["origin"],
                        household_id=row["household_id"], home_activated=bool(home and home["activated_at"]))
