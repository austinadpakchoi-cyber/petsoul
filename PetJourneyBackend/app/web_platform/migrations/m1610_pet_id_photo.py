"""1610：每只宠物一张证件照（CR-6C2B-IDPHOTO，用户 2026-09-24 定：新宠物自动生成、默认开；存量不批量补）。

用在护照、居民证、驾照等全部证件上：正面头肩、浅色纯底、写实，与 TA 本人一致。
**不覆盖主人原照**，单独保存、带版本；参考照换了才重画。1600–1699 是分给角色模块的编号区间。

与 1600 分开建表而不是加一种"姿态"：证件照**不透明**、有纯色底，过不了角色图的透明校验；
没有照片的宠物没有角色形象，却也要有证件照（复用插画链路那张基准照，不另付费，那种情况不落这张表）。

两张表各管一件事：

  - `web_pet_id_photos`：每一次尝试一行。三份文件：
      `source_rel_path` 供应商给的原图（透明路线下是**透明原图，私下保留**：将来换底色只需重新合成，不必重画、不再花钱）；
      `rel_path` 合成到底色（`backdrop`，现为 `#DCE8F2`）并从上方裁成竖幅 3:4 的证件用图；
      `avatar_rel_path` 从上方正方形缩成 256×256 的地图头像；
  - `web_pet_id_photo_active`：**已生效**的那一张。发布＝改这一张表的一行，upsert 带 `WHERE excluded.revision > 现有 revision`，
    过期任务在 SQL 层就覆盖不了新证件照（与 1600 的 active 同一个做法）。

参考照的整数版本复用 1600 的 `web_pet_character_references`——同一只宠物的同一张照片，角色与证件照拿到的是同一个号。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_pet_id_photos (
            asset_id TEXT PRIMARY KEY,
            pet_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            state TEXT NOT NULL CHECK (state IN ('queued', 'running', 'ready', 'failed')),
            reason TEXT,
            task_id TEXT NOT NULL,
            revision INTEGER NOT NULL,
            reference_key TEXT NOT NULL,
            reference_version INTEGER NOT NULL,
            reference_digest TEXT,
            style_version TEXT NOT NULL,
            rel_path TEXT,
            avatar_rel_path TEXT,
            source_rel_path TEXT,
            backdrop TEXT,
            content_type TEXT,
            provider TEXT,
            model TEXT,
            sha256 TEXT,
            width INTEGER,
            height INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    # 同一只宠物、同一张参考照、同一风格、同一轮次**只登记一次**：刷新、重复点击、进程恢复都撞在这条上
    conn.execute(
        "CREATE UNIQUE INDEX web_pet_id_photos_take ON web_pet_id_photos (pet_id, reference_version, style_version, revision)"
    )
    conn.execute("CREATE INDEX web_pet_id_photos_task ON web_pet_id_photos (task_id)")
    conn.execute(
        """
        CREATE TABLE web_pet_id_photo_active (
            pet_id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            revision INTEGER NOT NULL,
            published_at TEXT NOT NULL
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="1610_pet_id_photo",
    module="character",
    description="per-pet ID photo for passports and cards: attempt rows plus the one published active photo",
    apply=_apply,
)
