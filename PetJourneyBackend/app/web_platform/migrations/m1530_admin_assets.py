"""1530：运营素材库（原件、缩略图、来源、使用范围、哈希）。

方案 §4 P1 要求素材"记录原件、缩略图、来源、使用范围、哈希；用户参考照不能被运营随手复用成公共素材"。
这张表把前四项记成**必填**（来源与使用范围没有默认值，上传时必须说清楚），
最后一条由 `app/web_admin/assets.py` 在入库前按哈希比对玩家参考照来挡，不是靠约定。

`sha256` 唯一：同一张图不会入库两次，也让"这张图是不是玩家的参考照"可以按哈希直接判。
文件本身不放在公开挂载的 `/media` 目录下，也**不放**玩家私有媒体目录（那是参考照的地方）；
公开素材由 `/api/v1/web/assets/{asset_id}` 这一个受控入口提供，内部素材只有带权限的员工能取。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE admin_assets (
            asset_id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL,
            byte_size INTEGER NOT NULL,
            sha256 TEXT NOT NULL UNIQUE,
            width INTEGER,
            height INTEGER,
            rel_path TEXT NOT NULL,
            thumb_rel_path TEXT,
            thumb_note TEXT,
            source TEXT NOT NULL,
            source_note TEXT NOT NULL,
            license TEXT,
            usage_scope TEXT NOT NULL CHECK (usage_scope IN ('public', 'internal')),
            status TEXT NOT NULL CHECK (status IN ('active', 'retired')),
            version INTEGER NOT NULL DEFAULT 1,
            uploaded_by TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            retired_at TEXT,
            retired_by TEXT,
            retired_reason TEXT
        )
        """
    )
    conn.execute("CREATE INDEX idx_admin_assets_scope ON admin_assets (usage_scope, status, uploaded_at DESC)")


MIGRATION = WebMigration(
    migration_id="1530_admin_assets",
    module="web_admin",
    description="operations asset library: original + thumbnail, source, usage scope, sha256",
    apply=_apply,
)
