"""1410：驾考——学车阶段、各项掌握程度、陪练/自学记录、考试尝试（规则版本、题目、作答、分项结果、错题）。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_driving (
            pet_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            wish_text TEXT,
            wish_at TEXT,
            enrolled_at TEXT,
            mastery_json TEXT NOT NULL,
            last_study_at TEXT,
            needs_practice INTEGER NOT NULL DEFAULT 0,
            theory_passed_at TEXT,
            licensed_at TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE web_exam_attempts (
            attempt_id TEXT PRIMARY KEY,
            pet_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            part TEXT NOT NULL,
            attempt_no INTEGER NOT NULL,
            rules_version TEXT NOT NULL,
            question_ids_json TEXT NOT NULL,
            answers_json TEXT NOT NULL,
            score INTEGER NOT NULL,
            max_score INTEGER NOT NULL,
            passed INTEGER NOT NULL,
            errors_json TEXT NOT NULL,
            pet_says TEXT NOT NULL,
            taken_at TEXT NOT NULL,
            UNIQUE (pet_id, part, attempt_no)
        )
        """
    )
    conn.execute("CREATE TABLE web_driving_practice (practice_id TEXT PRIMARY KEY, pet_id TEXT NOT NULL, by_whom TEXT NOT NULL, mastery_json TEXT NOT NULL, created_at TEXT NOT NULL)")


MIGRATION = WebMigration(
    migration_id="1410_driving",
    module="driving",
    description="driving school: stage, topic mastery, owner/self practice, server-scored exam attempts with errors",
    apply=_apply,
)
