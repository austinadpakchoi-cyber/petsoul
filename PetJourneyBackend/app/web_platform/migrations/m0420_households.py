"""0420：家庭共同照顾（用户 2026-09-22 的新决定）。

一只宠物只有一个稳定身份、只归属一个家庭；一个家庭可以有多位成员（家庭管理员 / 共同照顾者）、多只宠物，共用一个家。
禁止的是把同一只宠物复制给不同家庭，不是禁止一家人共同陪伴。

- web_households：家庭；家（web_homes）一户一个，新增 household_id 关联；
- web_household_members：成员关系与权限角色（称呼与权限分开，称呼在 web_pet_relationships）；
- web_household_pets：宠物 → 唯一家庭（主键 pet_id）；
- web_household_invites：邀请只存令牌摘要，一次接受、可撤销、有有效期；
- web_pet_onboarding：每只宠物自己的接待与入住进度（原先记在 web_homes 上，只能容纳一只宠物）；
- 旧数据：每个旧家迁成“一个家庭 + 一位管理员 + 原来的宠物”，保留原 pet_id、home_id、资产、证件与历史，不复制余额、不补发奖励。
- 不重建旧表：web_homes 的 user_id / pet_id 保留为“建立者 / 第一只宠物”，归属一律以本迁移的关系表为准。
"""

from __future__ import annotations

import hashlib
import sqlite3

from . import WebMigration


def household_id_for_home(home_id: str) -> str:
    return "hh-" + hashlib.sha1(home_id.encode("utf-8")).hexdigest()[:12]


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_households (
            household_id TEXT PRIMARY KEY,
            name TEXT,
            created_by TEXT NOT NULL REFERENCES users(user_id),
            created_at TEXT NOT NULL,
            caregivers_can_spend INTEGER NOT NULL DEFAULT 1,
            generated_photos INTEGER,
            pet_messages INTEGER,
            version INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE web_household_members (
            household_id TEXT NOT NULL REFERENCES web_households(household_id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('admin', 'caregiver')),
            status TEXT NOT NULL CHECK (status IN ('active', 'removed', 'left')),
            joined_at TEXT NOT NULL,
            ended_at TEXT,
            ended_by TEXT,
            invite_id TEXT,
            version INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (household_id, user_id)
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_household_members_user ON web_household_members (user_id, status)")
    conn.execute(
        """
        CREATE TABLE web_household_pets (
            pet_id TEXT PRIMARY KEY REFERENCES pets(pet_id) ON DELETE CASCADE,
            household_id TEXT NOT NULL REFERENCES web_households(household_id) ON DELETE CASCADE,
            joined_at TEXT NOT NULL,
            added_by TEXT,
            via TEXT NOT NULL CHECK (via IN ('upload', 'adoption', 'migration')),
            position INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_household_pets_household ON web_household_pets (household_id, position)")
    conn.execute(
        """
        CREATE TABLE web_household_invites (
            invite_id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL REFERENCES web_households(household_id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL CHECK (role IN ('admin', 'caregiver')),
            relation_hint TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'accepted', 'revoked')),
            accepted_by TEXT,
            accepted_at TEXT,
            revoked_by TEXT,
            revoked_at TEXT
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_household_invites_household ON web_household_invites (household_id, status)")
    conn.execute(
        """
        CREATE TABLE web_pet_relationships (
            pet_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            owner_title TEXT,
            relation_label TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (pet_id, user_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE web_pet_onboarding (
            pet_id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            added_by TEXT,
            reception_session_id TEXT,
            reception_skipped INTEGER NOT NULL DEFAULT 0,
            moved_in_at TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("ALTER TABLE web_homes ADD COLUMN household_id TEXT")
    conn.execute("CREATE UNIQUE INDEX idx_web_homes_household ON web_homes (household_id)")

    # ---- 旧数据：一个旧家 → 一个家庭 + 一位管理员 + 原来的宠物（保留 pet_id / home_id，不动资产与历史） ----
    for row in conn.execute("SELECT * FROM web_homes").fetchall():
        household_id = household_id_for_home(row["home_id"])
        conn.execute(
            "INSERT INTO web_households (household_id, name, created_by, created_at, generated_photos, pet_messages) VALUES (?, NULL, ?, ?, NULL, NULL)",
            (household_id, row["user_id"], row["created_at"]),
        )
        conn.execute(
            "INSERT INTO web_household_members (household_id, user_id, role, status, joined_at) VALUES (?, ?, 'admin', 'active', ?)",
            (household_id, row["user_id"], row["created_at"]),
        )
        conn.execute(
            "INSERT INTO web_household_pets (pet_id, household_id, joined_at, added_by, via, position) VALUES (?, ?, ?, ?, 'migration', 0)",
            (row["pet_id"], household_id, row["created_at"], row["user_id"]),
        )
        conn.execute(
            "INSERT INTO web_pet_onboarding (pet_id, household_id, added_by, reception_session_id, reception_skipped, moved_in_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (row["pet_id"], household_id, row["user_id"], row["reception_session_id"], row["reception_skipped"], row["activated_at"], row["created_at"]),
        )
        conn.execute("UPDATE web_homes SET household_id = ? WHERE home_id = ?", (household_id, row["home_id"]))


MIGRATION = WebMigration(
    migration_id="0420_households",
    module="home",
    description="households with members (admin/caregiver), pets (one household per pet), invites, per-pet onboarding; legacy homes become single-member households",
    apply=_apply,
)
