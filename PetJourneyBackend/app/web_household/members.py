"""家庭：建家庭与添宠物（在调用方的事务里）、每只宠物的入住进度、成员角色与移除、家庭设置、关系称呼。"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime

from ..utils import iso, parse_dt, utcnow
from ..web_platform.runtime_epochs import bump_many_in, household_pets_in
from .model import Action, HouseholdError, Role
from .access import _not_found


class HouseholdMembersMixin:
    """需要 self.storage 与 HouseholdAccessMixin 的裁定方法。"""

    # ---- 建家庭与添宠物（调用方在自己的事务里） ----
    def created_household_of(self, conn: sqlite3.Connection, user_id: str) -> str | None:
        row = conn.execute("SELECT household_id FROM web_homes WHERE user_id = ?", (user_id,)).fetchone()
        return row["household_id"] if row else None

    def create_with_pet(self, conn: sqlite3.Connection, user_id: str, pet_id: str, via: str, now: datetime, name: str | None = None) -> tuple[str, str]:
        """新家庭 + 管理员 + 第一只宠物 + 一个家（尚未入住）。一个账号只能建立一个家庭（可以加入多个）。"""
        existing = self.created_household_of(conn, user_id)
        if existing is not None:
            raise HouseholdError("household_exists", "你已经建立过一个家，新的伙伴可以加进这个家。", 409, {"household_id": existing})
        household_id = f"hh-{uuid.uuid4().hex[:12]}"
        home_id = f"home-{pet_id}"
        conn.execute("INSERT INTO web_households (household_id, name, created_by, created_at) VALUES (?, ?, ?, ?)", (household_id, name, user_id, iso(now)))
        conn.execute("INSERT INTO web_household_members (household_id, user_id, role, status, joined_at) VALUES (?, ?, 'admin', 'active', ?)",
                     (household_id, user_id, iso(now)))
        conn.execute("INSERT INTO web_homes (home_id, user_id, pet_id, created_at, household_id) VALUES (?, ?, ?, ?, ?)",
                     (home_id, user_id, pet_id, iso(now), household_id))
        self._attach(conn, household_id, pet_id, user_id, via, now)
        return household_id, home_id

    def add_pet(self, conn: sqlite3.Connection, household_id: str, pet_id: str, user_id: str, via: str, now: datetime) -> None:
        self._attach(conn, household_id, pet_id, user_id, via, now)

    @staticmethod
    def _attach(conn: sqlite3.Connection, household_id: str, pet_id: str, user_id: str, via: str, now: datetime) -> None:
        position = conn.execute("SELECT COUNT(*) AS n FROM web_household_pets WHERE household_id = ?", (household_id,)).fetchone()["n"]
        conn.execute("INSERT INTO web_household_pets (pet_id, household_id, joined_at, added_by, via, position) VALUES (?, ?, ?, ?, ?, ?)",
                     (pet_id, household_id, iso(now), user_id, via, position))
        conn.execute("INSERT INTO web_pet_onboarding (pet_id, household_id, added_by, created_at) VALUES (?, ?, ?, ?)",
                     (pet_id, household_id, user_id, iso(now)))
        conn.execute("UPDATE web_households SET version = version + 1 WHERE household_id = ?", (household_id,))

    # ---- 每只宠物的入住进度 ----
    def onboarding_row(self, pet_id: str) -> sqlite3.Row | None:
        with self.storage.connect() as conn:
            return conn.execute("SELECT * FROM web_pet_onboarding WHERE pet_id = ?", (pet_id,)).fetchone()

    def record_reception(self, pet_id: str, session_id: str, skipped: bool) -> None:
        with self.storage.connect() as conn:
            conn.execute("UPDATE web_pet_onboarding SET reception_session_id = ?, reception_skipped = CASE WHEN ? THEN 1 ELSE reception_skipped END "
                         "WHERE pet_id = ? AND moved_in_at IS NULL", (session_id, 1 if skipped else 0, pet_id))

    def mark_moved_in(self, pet_id: str, now: datetime) -> bool:
        with self.storage.connect() as conn:
            return conn.execute("UPDATE web_pet_onboarding SET moved_in_at = ? WHERE pet_id = ? AND moved_in_at IS NULL", (iso(now), pet_id)).rowcount == 1

    # ---- 成员与角色 ----
    def _active_admins(self, conn: sqlite3.Connection, household_id: str) -> list[str]:
        rows = conn.execute("SELECT user_id FROM web_household_members WHERE household_id = ? AND status = 'active' AND role = 'admin'", (household_id,)).fetchall()
        return [r["user_id"] for r in rows]

    def set_role(self, actor: str, household_id: str, target: str, role: Role, now: datetime) -> None:
        self.require_household(actor, household_id, Action.manage)
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            member = conn.execute("SELECT * FROM web_household_members WHERE household_id = ? AND user_id = ? AND status = 'active'", (household_id, target)).fetchone()
            if member is None:
                raise _not_found("member")
            if role is Role.caregiver and member["role"] == "admin" and self._active_admins(conn, household_id) == [target]:
                raise HouseholdError("last_admin", "家庭至少要有一位管理员：请先把管理员交给另一位成员。", 409)
            conn.execute("UPDATE web_household_members SET role = ?, version = version + 1 WHERE household_id = ? AND user_id = ?", (role.value, household_id, target))
            conn.execute("UPDATE web_households SET version = version + 1 WHERE household_id = ?", (household_id,))
            bump_many_in(conn, household_pets_in(conn, household_id), "membership_epoch", now)

    def remove(self, actor: str, household_id: str, target: str, now: datetime) -> None:
        """管理员移除成员，或成员自己退出（actor == target）。被移除后立即失去该家庭全部宠物的私有访问权。"""
        if actor != target:
            self.require_household(actor, household_id, Action.manage)
        else:
            self.require_household(actor, household_id, Action.view)
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            member = conn.execute("SELECT * FROM web_household_members WHERE household_id = ? AND user_id = ? AND status = 'active'", (household_id, target)).fetchone()
            if member is None:
                raise _not_found("member")
            if member["role"] == "admin" and self._active_admins(conn, household_id) == [target]:
                raise HouseholdError("last_admin", "家庭至少要有一位管理员：请先把管理员交给另一位成员，再退出或被移除。", 409)
            conn.execute("UPDATE web_household_members SET status = ?, ended_at = ?, ended_by = ?, version = version + 1 WHERE household_id = ? AND user_id = ?",
                         ("left" if actor == target else "removed", iso(now), actor, household_id, target))
            conn.execute("UPDATE web_households SET version = version + 1 WHERE household_id = ?", (household_id,))
            # 成员少了一位：这个家所有宠物换代，在途的思考与还没发布的内容都要按新权限复核
            bump_many_in(conn, household_pets_in(conn, household_id), "membership_epoch", now)

    def update_settings(self, actor: str, household_id: str, *, name: str | None = None, caregivers_can_spend: bool | None = None,
                        generated_photos: bool | None = None, pet_messages: bool | None = None) -> None:
        self.require_household(actor, household_id, Action.manage)
        now = utcnow()
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            before = conn.execute("SELECT generated_photos, pet_messages FROM web_households WHERE household_id = ?", (household_id,)).fetchone()
            conn.execute(
                "UPDATE web_households SET name = COALESCE(?, name), caregivers_can_spend = COALESCE(?, caregivers_can_spend), "
                "generated_photos = COALESCE(?, generated_photos), pet_messages = COALESCE(?, pet_messages), version = version + 1 WHERE household_id = ?",
                ((name or "").strip()[:24] or None if name is not None else None,
                 None if caregivers_can_spend is None else int(caregivers_can_spend),
                 None if generated_photos is None else int(generated_photos), None if pet_messages is None else int(pet_messages), household_id),
            )
            # 家庭级的用途授权（写实照片、TA 能不能主动来信）变了：在**同一个事务**里让这家宠物换代，
            # 在途的提案与表达要按新授权重新复核。改名字、改能不能花钱不算用途授权（验收 CR-Q13 的家庭这一半）。
            changed = ((generated_photos is not None and before is not None and bool(before["generated_photos"]) != bool(generated_photos))
                       or (pet_messages is not None and before is not None and bool(before["pet_messages"]) != bool(pet_messages)))
            if changed:
                bump_many_in(conn, household_pets_in(conn, household_id), "privacy_epoch", now)

    # ---- 关系层：每位成员与每只宠物之间的称呼 ----
    def relationship(self, pet_id: str, user_id: str) -> dict | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_pet_relationships WHERE pet_id = ? AND user_id = ?", (pet_id, user_id)).fetchone()
        return None if row is None else {"owner_title": row["owner_title"], "relation_label": row["relation_label"], "updated_at": parse_dt(row["updated_at"])}

    def set_relationship(self, user_id: str, pet_id: str, owner_title: str | None, relation_label: str | None, now: datetime) -> dict:
        self.require_pet(user_id, pet_id, Action.care)
        title = (owner_title or "").strip()[:12] or None
        label = (relation_label or "").strip()[:12] or None
        with self.storage.connect() as conn:
            conn.execute(
                "INSERT INTO web_pet_relationships (pet_id, user_id, owner_title, relation_label, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(pet_id, user_id) DO UPDATE SET owner_title = excluded.owner_title, relation_label = excluded.relation_label, updated_at = excluded.updated_at",
                (pet_id, user_id, title, label, iso(now), iso(now)),
            )
        return self.relationship(pet_id, user_id) or {}
