"""1900：到站欢迎（用户 2026-09-24：每个用户注册完成后，都会收到宠物在聊天框和明信片里发来的一张到站自拍）。

TA 第一次住进家（入住＝到站）时，入住接口在这里**登记一行**；认知线的后台轮次再去写话、排自拍、
发家庭频道消息和到站明信片（见 `app/web_arrival/`）。一只宠物只有一行、只发一次。

  · state：pending（等后台发）/ delivered（消息与明信片已发出）/ skipped（发之前 TA 已不在这个家）/
    abandoned（反复出错、不再自动重试——运营可见 last_error）。
  · user_id：接 TA 入住的那位家人；自拍任务记在这位名下（与旅行明信片记在发起旅程的家人名下同理）。
  · 功能上线前就已入住的宠物没有行：**不补发**（隔几天突然收到「我到站啦」反而奇怪，也不该替旧账号花生图额度）。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_pet_arrivals (
            pet_id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            registered_at TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'delivered', 'skipped', 'abandoned')),
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TEXT NOT NULL,
            delivered_at TEXT,
            photo_task_id TEXT,
            note_composed_by TEXT,
            last_error TEXT
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_pet_arrivals_due ON web_pet_arrivals (state, next_attempt_at)")


MIGRATION = WebMigration(
    migration_id="1900_pet_arrivals",
    module="arrival",
    description="arrival welcome: one pending row per pet at first move-in; background sends the selfie message and postcard",
    apply=_apply,
)
