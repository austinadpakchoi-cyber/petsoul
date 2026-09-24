"""家庭：查询与访问裁定（谁对哪只宠物 / 哪个家庭能做什么）。不是成员 404，角色不够 403，没指明而又不止一只 409 pet_required。"""

from __future__ import annotations

import sqlite3

from ..utils import parse_dt
from .model import Action, HouseholdAccess, HouseholdError, Membership, PetAccess, Role


def _not_found(what: str = "pet") -> HouseholdError:
    return HouseholdError(f"{what}_not_found", "没有找到，或者你还不是这个家庭的成员。", 404)


class HouseholdAccessMixin:
    """需要 self.storage。"""

    # 组合根注入：在调用方的连接上读某人的个人设置（`identity.prefs_in`）。
    # 没接上时按"读不到就当没开"处理——宁可少发一张图，也不要在授权不明时发出付费调用。
    prefs_in = None

    # ---- 授权复核（在调用方的事务里读，给写事务做最终确认用）----
    def generated_photos_in(self, conn: sqlite3.Connection, pet_id: str | None) -> bool:
        """在调用方的写事务连接上读"这只宠物现在还能不能生成照片"。

        语义：家庭的显式设置优先；从没设置过就沿用建立这个家的人当初的个人选择；
        **没有家庭的居民一律 False**。

        **【现状更正 2026-09-24】这里原先写的是「语义与组合根的 `generated_photos_of` 完全一致
        （那边现在就委托到这里）」——`generated_photos_of` 已随取消逐次授权询问被摘除
        （用户 2026-09-23 决定，见 `web_composition.py` 那处【已摘除】注释），全仓只剩注释提到它。
        留着这句会让人去找一个不存在的对照物。**

        **本函数现在没有生产调用方**（只有 `tests/test_web_consent_same_connection.py` 在读）。
        它没被删掉是因为「同连接读」这个做法本身仍然正确、而且将来任何
        「写事务里做最终确认」的闸都该照它来——见下面那段理由。是否清理由 c84a 定。

        为什么要有同连接版本：付费生图的最终写入发生在一个写事务里，
        如果这时另开连接去读授权，读到的是**事务外**的旧值——主人刚撤销的许可看不见，图还是会被发布出去；
        在 SQLite 上另开连接还可能自锁。所以这里**不另开连接、不 BEGIN、不 commit**，只在传进来的 conn 上读。

        注意它是**家庭级**的授权，不区分是哪位家人；"某位家人被移出家庭后立刻失效"属于成员资格那条线（membership_epoch），
        两件事不要合成一个开关。
        """
        if not pet_id:
            return False
        row = conn.execute("SELECT household_id FROM web_household_pets WHERE pet_id = ?", (pet_id,)).fetchone()
        if row is None:
            return False
        household = conn.execute("SELECT * FROM web_households WHERE household_id = ?", (row["household_id"],)).fetchone()
        if household is None:
            return False
        if "generated_photos" in household.keys() and household["generated_photos"] is not None:
            return bool(household["generated_photos"])
        if self.prefs_in is None:
            return False
        return bool(self.prefs_in(conn, household["created_by"])["generated_photos"])

    # ---- 查询 ----
    def memberships(self, user_id: str, *, active_only: bool = True) -> list[Membership]:
        sql = "SELECT * FROM web_household_members WHERE user_id = ?" + (" AND status = 'active'" if active_only else "") + " ORDER BY joined_at, household_id"
        with self.storage.connect() as conn:
            rows = conn.execute(sql, (user_id,)).fetchall()
        return [Membership(r["household_id"], r["user_id"], Role(r["role"]), r["status"], parse_dt(r["joined_at"])) for r in rows]

    def household_row(self, household_id: str) -> sqlite3.Row | None:
        with self.storage.connect() as conn:
            return conn.execute("SELECT * FROM web_households WHERE household_id = ?", (household_id,)).fetchone()

    def home_id_of(self, household_id: str) -> str | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT home_id FROM web_homes WHERE household_id = ?", (household_id,)).fetchone()
        return row["home_id"] if row else None

    def household_of_pet(self, pet_id: str) -> str | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT household_id FROM web_household_pets WHERE pet_id = ?", (pet_id,)).fetchone()
        return row["household_id"] if row else None

    def household_of_home(self, home_id: str) -> str | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT household_id FROM web_homes WHERE home_id = ?", (home_id,)).fetchone()
        return row["household_id"] if row else None

    def pets_of(self, household_id: str) -> list[str]:
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT pet_id FROM web_household_pets WHERE household_id = ? ORDER BY position, joined_at, pet_id", (household_id,)).fetchall()
        return [r["pet_id"] for r in rows]

    def members_of(self, household_id: str, *, active_only: bool = True) -> list[Membership]:
        sql = "SELECT * FROM web_household_members WHERE household_id = ?" + (" AND status = 'active'" if active_only else "") + " ORDER BY joined_at, user_id"
        with self.storage.connect() as conn:
            rows = conn.execute(sql, (household_id,)).fetchall()
        return [Membership(r["household_id"], r["user_id"], Role(r["role"]), r["status"], parse_dt(r["joined_at"])) for r in rows]

    def member_ids(self, household_id: str) -> list[str]:
        return [m.user_id for m in self.members_of(household_id)]

    def primary_admin(self, household_id: str) -> str | None:
        admins = [m.user_id for m in self.members_of(household_id) if m.role is Role.admin]
        return admins[0] if admins else None

    def setting(self, household_id: str, key: str) -> object:
        row = self.household_row(household_id)
        return row[key] if row is not None and key in row.keys() else None

    # ---- 访问裁定 ----
    def _access(self, conn: sqlite3.Connection, user_id: str, household_id: str) -> HouseholdAccess | None:
        row = conn.execute(
            "SELECT m.role, h.caregivers_can_spend, homes.home_id FROM web_household_members m JOIN web_households h ON h.household_id = m.household_id "
            "JOIN web_homes homes ON homes.household_id = m.household_id WHERE m.household_id = ? AND m.user_id = ? AND m.status = 'active'",
            (household_id, user_id),
        ).fetchone()
        if row is None:
            return None
        return HouseholdAccess(user_id=user_id, household_id=household_id, home_id=row["home_id"], role=Role(row["role"]),
                               caregivers_can_spend=bool(row["caregivers_can_spend"]))

    def access_household(self, user_id: str, household_id: str) -> HouseholdAccess | None:
        with self.storage.connect() as conn:
            return self._access(conn, user_id, household_id)

    def access_pet(self, user_id: str, pet_id: str) -> PetAccess | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT household_id FROM web_household_pets WHERE pet_id = ?", (pet_id,)).fetchone()
            if row is None:
                return None
            access = self._access(conn, user_id, row["household_id"])
        if access is None:
            return None
        return PetAccess(user_id=user_id, household_id=access.household_id, home_id=access.home_id, role=access.role,
                         caregivers_can_spend=access.caregivers_can_spend, pet_id=pet_id)

    @staticmethod
    def _check(access: HouseholdAccess, action: Action) -> None:
        if not access.allows(action):
            if action is Action.manage:
                raise HouseholdError("admin_required", "这一步需要家庭管理员来做。", 403)
            raise HouseholdError("spend_not_allowed", "家庭设置里没有允许共同照顾者使用宠物的星球账户。", 403)

    def require_pet(self, user_id: str, pet_id: str, action: Action = Action.view) -> PetAccess:
        access = self.access_pet(user_id, pet_id)
        if access is None:
            raise _not_found("pet")
        self._check(access, action)
        return access

    def require_household(self, user_id: str, household_id: str, action: Action = Action.view) -> HouseholdAccess:
        access = self.access_household(user_id, household_id)
        if access is None:
            raise _not_found("household")
        self._check(access, action)
        return access

    def accessible_pets(self, user_id: str) -> list[tuple[str, str]]:
        """(pet_id, household_id)：当前有效成员关系能照顾的全部宠物（按加入家庭与宠物进家的先后）。"""
        with self.storage.connect() as conn:
            rows = conn.execute(
                "SELECT p.pet_id, p.household_id FROM web_household_members m JOIN web_household_pets p ON p.household_id = m.household_id "
                "WHERE m.user_id = ? AND m.status = 'active' ORDER BY m.joined_at, m.household_id, p.position, p.joined_at, p.pet_id",
                (user_id,),
            ).fetchall()
        return [(r["pet_id"], r["household_id"]) for r in rows]

    def resolve_pet(self, user_id: str, pet_id: str | None, action: Action = Action.view) -> PetAccess:
        """显式 pet_id 优先；没有给出时，只有“能照顾的宠物恰好一只”才默认它，否则要求前端指明（409 pet_required）。"""
        if pet_id:
            return self.require_pet(user_id, pet_id, action)
        pets = self.accessible_pets(user_id)
        if not pets:
            raise HouseholdError("needs_companion", "你还没有加入任何家庭：可以接自己的宠物入住、领养一位伙伴，或者接受家人的邀请。", 409)
        if len(pets) > 1:
            raise HouseholdError("pet_required", "你照顾的宠物不止一只，请指明是哪一只（pet_id）。", 409,
                                 {"pets": [{"pet_id": p, "household_id": h} for p, h in pets]})
        return self.require_pet(user_id, pets[0][0], action)

    def resolve_household(self, user_id: str, household_id: str | None, pet_id: str | None = None, action: Action = Action.view) -> HouseholdAccess:
        if household_id:
            return self.require_household(user_id, household_id, action)
        if pet_id:
            access = self.require_pet(user_id, pet_id, action)
            return HouseholdAccess(user_id, access.household_id, access.home_id, access.role, access.caregivers_can_spend)
        memberships = self.memberships(user_id)
        if not memberships:
            raise HouseholdError("needs_companion", "你还没有加入任何家庭。", 409)
        if len(memberships) > 1:
            raise HouseholdError("household_required", "你在不止一个家庭里，请指明是哪一个（household_id）。", 409,
                                 {"households": [m.household_id for m in memberships]})
        return self.require_household(user_id, memberships[0].household_id, action)
