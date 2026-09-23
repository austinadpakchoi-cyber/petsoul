"""1420：驾考一致性（独立核查 P1/P2 修复）——陪练批次与驾考消息发件箱。

- web_driving_practice_sets：每组陪练题一条记录；交卷在同一事务里结算掌握程度并记下结果，
  同一组题重复提交（网络重试、重复点击）不重复加分；想再练就拿一组新的；
- web_driving_notes：驾考消息（愿望、报名、考试结果、拿证）与状态变更在同一事务写入，提交后再投递；
  投递失败不影响考试与驾驶资格，世界定时器会重试（按去重键，不会重复发）。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_driving_practice_sets (
            practice_id TEXT PRIMARY KEY,
            pet_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            part TEXT NOT NULL,
            question_ids_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            submitted_at TEXT,
            answers_json TEXT,
            result_json TEXT
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_driving_practice_sets_open ON web_driving_practice_sets (pet_id, part, submitted_at)")
    conn.execute(
        """
        CREATE TABLE web_driving_notes (
            dedupe_key TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            pet_id TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            delivered_at TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_driving_notes_pending ON web_driving_notes (delivered_at, created_at)")


MIGRATION = WebMigration(
    migration_id="1420_driving_consistency",
    module="driving",
    description="driving consistency: practice sets settled once per submission; transactional outbox for driving notes",
    apply=_apply,
)
