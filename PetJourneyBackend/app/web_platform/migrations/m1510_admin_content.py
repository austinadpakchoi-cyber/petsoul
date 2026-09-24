"""1510：运营内容的草稿 / 不可变版本 / 发布历史。

三张表各自只做一件事：
- admin_content_items    当前状态（草稿号、已发布号、乐观锁版本）；
- admin_content_revisions 不可变版本正文，写下去就不再改（回退＝复制旧正文成**新版本号**，不改历史）；
- admin_content_publications 发布与撤下的流水，仅追加，带操作者、原因、幂等操作号与差异摘要。

玩家侧按 `live_revision` 消费；已经发生过的事件（已入账的奖励、已登记的冒险故事）保存在各自的业务表里，
不随新版本改写——这是"回滚不改历史"的实现依据，不是口号。

修订说明（同一批交付内的修正，2026-09-23 运营后台窗口 adm1）：`content_type` 原来带
`CHECK (content_type IN ('announcement','adventure'))`，扩到作物/打工/居民时改成不带 CHECK，
取值由 `app/web_admin/content.py` 的 `CONTENT_TYPES` 与 `validate()` 逐项校验（那里本来就要判字段，
CHECK 只是重复一遍，还挡住了后续扩展）。本迁移**尚未提交、尚未部署**，只有本窗口的演示库应用过；
如果你手上有更早建过 `admin_content_items` 的本地库，跑 `python scripts/seed_admin_demo.py --reset` 重建。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE admin_content_items (
            item_id TEXT PRIMARY KEY,
            content_type TEXT NOT NULL,
            slug TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('draft', 'published', 'withdrawn')),
            live_revision INTEGER,
            draft_revision INTEGER,
            version INTEGER NOT NULL DEFAULT 1,
            effective_at TEXT,
            expires_at TEXT,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            UNIQUE (content_type, slug)
        )
        """
    )
    conn.execute("CREATE INDEX idx_admin_content_live ON admin_content_items (content_type, status, live_revision)")
    conn.execute(
        """
        CREATE TABLE admin_content_revisions (
            item_id TEXT NOT NULL REFERENCES admin_content_items(item_id) ON DELETE CASCADE,
            revision INTEGER NOT NULL,
            body_json TEXT NOT NULL,
            body_hash TEXT NOT NULL,
            note TEXT,
            source_revision INTEGER,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            PRIMARY KEY (item_id, revision)
        )
        """
    )
    conn.execute(
        "CREATE TRIGGER admin_content_revisions_no_update BEFORE UPDATE ON admin_content_revisions "
        "BEGIN SELECT RAISE(ABORT, 'content revisions are immutable'); END"
    )
    conn.execute(
        """
        CREATE TABLE admin_content_publications (
            publication_id TEXT PRIMARY KEY,
            item_id TEXT NOT NULL REFERENCES admin_content_items(item_id) ON DELETE CASCADE,
            revision INTEGER NOT NULL,
            action TEXT NOT NULL CHECK (action IN ('publish', 'withdraw')),
            effective_at TEXT NOT NULL,
            expires_at TEXT,
            reason TEXT NOT NULL,
            staff_id TEXT NOT NULL,
            operation_id TEXT NOT NULL UNIQUE,
            diff_summary TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX idx_admin_content_publications_item ON admin_content_publications (item_id, created_at DESC)")
    conn.execute(
        "CREATE TRIGGER admin_content_publications_no_update BEFORE UPDATE ON admin_content_publications "
        "BEGIN SELECT RAISE(ABORT, 'publication history is append-only'); END"
    )


MIGRATION = WebMigration(
    migration_id="1510_admin_content",
    module="web_admin",
    description="operations content drafts, immutable revisions and append-only publication history",
    apply=_apply,
)
