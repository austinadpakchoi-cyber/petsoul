"""0180：注册入口与待确认的选择（先逛逛 / 接我的宠物入住 / 认识新伙伴 / 家庭邀请直达）。

注册不再等于“立刻建立一只宠物”。注册前在访客页选中的待领养伙伴、或打开的家庭邀请，记在这里，登录后由页面恢复并请用户确认；
服务端不会在注册完成时替用户自动领养或自动加入家庭。邀请只记邀请编号，不保存令牌原文。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_user_entry (
            user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK (kind IN ('browse', 'own_pet', 'adopt', 'invite')),
            target_pet_id TEXT,
            invite_id TEXT,
            created_at TEXT NOT NULL,
            resolved_at TEXT
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="0180_user_entry",
    module="identity",
    description="registration entry intent (browse / own pet / adopt a selected resident / accept a household invite), confirmed later by the user",
    apply=_apply,
)
