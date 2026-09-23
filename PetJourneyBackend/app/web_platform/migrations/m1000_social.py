"""1000：星球圈（公开动态/点赞/评论/关注/屏蔽/举报）、1100 通讯与 1200 收藏共用一次建表会导致模块区间混用，
因此本迁移只建社交表；通讯与收藏见 m1100 / m1200。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_posts (
            post_id TEXT PRIMARY KEY,
            author_pet_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            text TEXT NOT NULL,
            media_json TEXT NOT NULL,
            source_event_id TEXT NOT NULL UNIQUE,
            visit_id TEXT,
            visibility TEXT NOT NULL CHECK (visibility IN ('public', 'followers', 'removed')),
            created_at TEXT NOT NULL,
            removed_at TEXT
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_posts_feed ON web_posts (visibility, created_at DESC)")
    conn.execute(
        """
        CREATE TABLE web_reactions (
            post_id TEXT NOT NULL REFERENCES web_posts(post_id) ON DELETE CASCADE,
            actor_kind TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            user_id TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (post_id, actor_kind, actor_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE web_comments (
            comment_id TEXT PRIMARY KEY,
            post_id TEXT NOT NULL REFERENCES web_posts(post_id) ON DELETE CASCADE,
            actor_kind TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            user_id TEXT,
            reply_to_comment_id TEXT,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            removed_at TEXT
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_comments_post ON web_comments (post_id, created_at)")
    conn.execute(
        "CREATE TABLE web_follows (follower_pet_id TEXT NOT NULL, followee_pet_id TEXT NOT NULL, created_at TEXT NOT NULL, "
        "PRIMARY KEY (follower_pet_id, followee_pet_id))"
    )
    conn.execute("CREATE TABLE web_blocks (user_id TEXT NOT NULL, blocked_user_id TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (user_id, blocked_user_id))")
    conn.execute(
        "CREATE TABLE web_reports (report_id TEXT PRIMARY KEY, reporter_user_id TEXT NOT NULL, target_kind TEXT NOT NULL, target_id TEXT NOT NULL, "
        "reason TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE (reporter_user_id, target_kind, target_id))"
    )


MIGRATION = WebMigration(
    migration_id="1000_social",
    module="social",
    description="public posts from world events, reactions/comments with explicit actors, follows, blocks, reports",
    apply=_apply,
)
