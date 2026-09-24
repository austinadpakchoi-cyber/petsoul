"""1600：宠物的世界角色资产（私有）。有授权的原照上传成功后自动生成，家园与后续场景复用同一份。

与 `web_illustrations`（0660）分开建表，不是嫌麻烦：那是"某次冒险画了一张图"，一次性、带场景；
这是一份**长期身份资产**——透明、无背景、跨场景复用、有生效版本与在建版本之分。
两件事共用一张表会把"这次画的"和"现在是谁"搅在一起。

三张表各管一件事：

  - `web_pet_character_references`：给每只宠物见过的每一张参考照一个**单调递增的整数版本**。
    契约要的 `source_reference_version` 是整数（比大小就能判"是不是换过照片"），
    而 `web_pet_profiles.photo_ref` 是个 uuid 文件名，比不出先后，所以在这里建号。
  - `web_pet_characters`：每一次尝试（candidate）一行，含校验测出来的边界与锚点。
  - `web_pet_character_active`：**已生效**的那一套。发布＝改这一张表的一行，所以切换是原子的；
    upsert 带 `WHERE excluded.revision > 现有 revision`，**过期任务在 SQL 层就覆盖不了新形象**。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_pet_character_references (
            pet_id TEXT NOT NULL,
            reference_key TEXT NOT NULL,
            version INTEGER NOT NULL,
            first_seen_at TEXT NOT NULL,
            PRIMARY KEY (pet_id, reference_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE web_pet_characters (
            asset_id TEXT PRIMARY KEY,
            set_id TEXT NOT NULL,
            pet_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            pose TEXT NOT NULL,
            state TEXT NOT NULL CHECK (state IN ('queued', 'running', 'ready', 'failed')),
            reason TEXT,
            task_id TEXT NOT NULL,
            revision INTEGER NOT NULL,
            reference_key TEXT NOT NULL,
            reference_version INTEGER NOT NULL,
            reference_digest TEXT,
            style_version TEXT NOT NULL,
            rel_path TEXT,
            content_type TEXT,
            provider TEXT,
            model TEXT,
            sha256 TEXT,
            width INTEGER,
            height INTEGER,
            content_left INTEGER,
            content_top INTEGER,
            content_right INTEGER,
            content_bottom INTEGER,
            anchor_x REAL,
            anchor_y REAL,
            opaque_ratio REAL,
            has_alpha INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    # 同一只宠物、同一姿态、同一张参考照、同一风格、同一轮次**只登记一次**：
    # 刷新、重复点击、进程恢复都撞在这条上，不会多排一张要花钱的图。
    conn.execute(
        "CREATE UNIQUE INDEX web_pet_characters_take ON web_pet_characters "
        "(pet_id, pose, reference_version, style_version, revision)"
    )
    conn.execute("CREATE INDEX web_pet_characters_task ON web_pet_characters (task_id)")
    conn.execute("CREATE INDEX web_pet_characters_set ON web_pet_characters (set_id)")
    conn.execute(
        """
        CREATE TABLE web_pet_character_active (
            pet_id TEXT PRIMARY KEY,
            set_id TEXT NOT NULL,
            revision INTEGER NOT NULL,
            published_at TEXT NOT NULL
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="1600_pet_character",
    module="character",
    description="per-pet world character assets: candidate takes plus the one atomically published active set",
    apply=_apply,
)
