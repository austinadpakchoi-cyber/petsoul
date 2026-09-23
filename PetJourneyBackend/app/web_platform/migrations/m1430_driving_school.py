"""1430：爪爪驾校（主人陪考，宠物拿证；规格见 docs/contracts/DRIVING-SCHOOL-v1.md）。

- web_school_subjects：每只宠物每科一行——轮次、本轮失败次数、冷却截止时间（第二次失败结算时间＋7×24 小时）、通过记录、练习次数；
- web_school_sessions：练习与正式考局——配置（题目或场地）、作答或操作记录与模拟快照、结果与状态时间；
  部分唯一索引保证同一只宠物同一时间最多一场未结束的正式考局；
- web_driving 追加 ceremony_at（领证仪式只做一次）。
旧的 web_exam_attempts / web_driving_practice_sets 保留不删，不再写入。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_school_subjects (
            pet_id TEXT NOT NULL,
            subject TEXT NOT NULL,
            user_id TEXT NOT NULL,
            round_no INTEGER NOT NULL DEFAULT 1,
            fails_in_round INTEGER NOT NULL DEFAULT 0,
            cooldown_until TEXT,
            cooldown_noted INTEGER NOT NULL DEFAULT 0,
            passed_at TEXT,
            passed_session_id TEXT,
            passed_score INTEGER,
            practice_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (pet_id, subject)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE web_school_sessions (
            session_id TEXT PRIMARY KEY,
            pet_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            subject TEXT NOT NULL,
            mode TEXT NOT NULL,
            item TEXT,
            attempt_kind TEXT,
            round_no INTEGER,
            paper_no INTEGER NOT NULL,
            rules_version TEXT NOT NULL,
            content_version TEXT NOT NULL,
            config_json TEXT NOT NULL,
            state TEXT NOT NULL,
            item_index INTEGER NOT NULL DEFAULT 0,
            progress_json TEXT NOT NULL,
            result_json TEXT,
            passed INTEGER,
            score INTEGER,
            created_at TEXT NOT NULL,
            begun_at TEXT,
            paused_at TEXT,
            last_active_at TEXT NOT NULL,
            settled_at TEXT,
            void_reason TEXT
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_school_sessions_pet ON web_school_sessions (pet_id, subject, mode, state)")
    conn.execute("CREATE UNIQUE INDEX idx_web_school_one_open_formal ON web_school_sessions (pet_id) WHERE mode = 'formal' AND state IN ('preparing', 'running')")
    conn.execute("ALTER TABLE web_driving ADD COLUMN ceremony_at TEXT")


MIGRATION = WebMigration(
    migration_id="1430_driving_school",
    module="driving",
    description="paw driving school: per-subject rounds and cooldowns, practice/formal sessions with server-side replay, ceremony",
    apply=_apply,
)
