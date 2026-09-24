"""家庭：邀请（令牌只存 HMAC 摘要；有有效期、可撤销、只能用一次；接受在一个事务里完成，并发/重放不重复建立成员关系）。"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta

from ..utils import iso, parse_dt, utcnow
from ..web_platform.runtime_epochs import bump_many_in, household_pets_in
from .model import Action, HouseholdError, Role
from .access import _not_found

INVITE_TTL = timedelta(hours=72)
MAX_INVITE_TTL = timedelta(days=14)


class HouseholdInvitesMixin:
    """需要 self.storage、self._secret 与 HouseholdAccessMixin 的裁定方法。"""

    # ---- 邀请 ----
    def _hash(self, token: str) -> str:
        return hmac.new(self._secret, token.encode("utf-8"), hashlib.sha256).hexdigest()

    def create_invite(self, user_id: str, household_id: str, role: Role, relation_hint: str | None, now: datetime,
                      ttl: timedelta = INVITE_TTL) -> tuple[dict, str]:
        self.require_household(user_id, household_id, Action.manage)
        ttl = min(max(ttl, timedelta(minutes=10)), MAX_INVITE_TTL)
        token = secrets.token_urlsafe(24)
        invite_id = f"inv-{uuid.uuid4().hex[:12]}"
        with self.storage.connect() as conn:
            conn.execute(
                "INSERT INTO web_household_invites (invite_id, household_id, token_hash, role, relation_hint, created_by, created_at, expires_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')",
                (invite_id, household_id, self._hash(token), role.value, (relation_hint or "").strip()[:24] or None, user_id, iso(now), iso(now + ttl)),
            )
        return self.invite(invite_id), token

    def invite(self, invite_id: str) -> dict:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_household_invites WHERE invite_id = ?", (invite_id,)).fetchone()
        if row is None:
            raise _not_found("invite")
        return self._invite_view(row)

    @staticmethod
    def _invite_view(row: sqlite3.Row, now: datetime | None = None) -> dict:
        now = now or utcnow()
        status = row["status"]
        if status == "pending" and parse_dt(row["expires_at"]) <= now:
            status = "expired"
        return {"invite_id": row["invite_id"], "household_id": row["household_id"], "role": row["role"], "relation_hint": row["relation_hint"],
                "created_by": row["created_by"], "created_at": parse_dt(row["created_at"]), "expires_at": parse_dt(row["expires_at"]), "status": status,
                "accepted_by": row["accepted_by"], "accepted_at": parse_dt(row["accepted_at"]) if row["accepted_at"] else None}

    def invites_of(self, user_id: str, household_id: str) -> list[dict]:
        self.require_household(user_id, household_id, Action.manage)
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT * FROM web_household_invites WHERE household_id = ? ORDER BY created_at DESC LIMIT 50", (household_id,)).fetchall()
        return [self._invite_view(r) for r in rows]

    def invite_by_token(self, token: str) -> dict:
        """按令牌找到邀请（只比对摘要）。找不到与已撤销一样返回 404，不区分令牌是否存在过。"""
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_household_invites WHERE token_hash = ?", (self._hash((token or "").strip()),)).fetchone()
        if row is None or row["status"] == "revoked":
            raise HouseholdError("invite_not_found", "这个邀请不存在或已经被撤销。", 404)
        return self._invite_view(row)

    def accept(self, user_id: str, token: str, now: datetime) -> dict:
        invite = self.invite_by_token(token)
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM web_household_invites WHERE invite_id = ?", (invite["invite_id"],)).fetchone()
            view = self._invite_view(row, now)
            member = conn.execute("SELECT * FROM web_household_members WHERE household_id = ? AND user_id = ?", (row["household_id"], user_id)).fetchone()
            if view["status"] == "accepted":
                if row["accepted_by"] == user_id:
                    return view  # 重放：同一个人再点一次，返回原结果
                raise HouseholdError("invite_used", "这个邀请已经被接受过了（每个邀请只能用一次）。", 409)
            if view["status"] == "expired":
                raise HouseholdError("invite_expired", "这个邀请已经过期，请家人重新发一个。", 409)
            if view["status"] == "revoked":
                raise HouseholdError("invite_not_found", "这个邀请不存在或已经被撤销。", 404)
            if member is not None and member["status"] == "active":
                raise HouseholdError("already_member", "你已经是这个家庭的成员了。", 409, {"household_id": row["household_id"]})
            if member is None:
                conn.execute("INSERT INTO web_household_members (household_id, user_id, role, status, joined_at, invite_id) VALUES (?, ?, ?, 'active', ?, ?)",
                             (row["household_id"], user_id, row["role"], iso(now), row["invite_id"]))
            else:  # 以前退出或被移除，重新受邀加入
                conn.execute("UPDATE web_household_members SET role = ?, status = 'active', joined_at = ?, ended_at = NULL, ended_by = NULL, invite_id = ?, "
                             "version = version + 1 WHERE household_id = ? AND user_id = ?", (row["role"], iso(now), row["invite_id"], row["household_id"], user_id))
            # 多了一位家人：这个家所有宠物换代，思考中的提案与还没发布的内容都按新成员关系复核
            bump_many_in(conn, household_pets_in(conn, row["household_id"]), "membership_epoch", now)
            won = conn.execute("UPDATE web_household_invites SET status = 'accepted', accepted_by = ?, accepted_at = ? WHERE invite_id = ? AND status = 'pending'",
                               (user_id, iso(now), row["invite_id"])).rowcount
            if won != 1:
                conn.rollback()
                raise HouseholdError("invite_used", "这个邀请已经被接受过了（每个邀请只能用一次）。", 409)
            if row["relation_hint"]:
                for pet in conn.execute("SELECT pet_id FROM web_household_pets WHERE household_id = ?", (row["household_id"],)).fetchall():
                    conn.execute("INSERT OR IGNORE INTO web_pet_relationships (pet_id, user_id, owner_title, relation_label, created_at, updated_at) "
                                 "VALUES (?, ?, NULL, ?, ?, ?)", (pet["pet_id"], user_id, row["relation_hint"], iso(now), iso(now)))
            conn.execute("UPDATE web_households SET version = version + 1 WHERE household_id = ?", (row["household_id"],))
        return self.invite(invite["invite_id"])

    def revoke_invite(self, user_id: str, invite_id: str, now: datetime) -> dict:
        invite = self.invite(invite_id)
        self.require_household(user_id, invite["household_id"], Action.manage)
        with self.storage.connect() as conn:
            conn.execute("UPDATE web_household_invites SET status = 'revoked', revoked_by = ?, revoked_at = ? WHERE invite_id = ? AND status = 'pending'",
                         (user_id, iso(now), invite_id))
        return self.invite(invite_id)
