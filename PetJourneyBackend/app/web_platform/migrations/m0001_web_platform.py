"""0001：网页平台共用表——幂等记录与可恢复任务。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_idempotency_keys (
            user_id TEXT NOT NULL,
            scope TEXT NOT NULL,
            idem_key TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('in_progress', 'completed')),
            response_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, scope, idem_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE web_tasks (
            task_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            dedupe_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'superseded')),
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            payload_json TEXT NOT NULL,
            source_version TEXT,
            run_after TEXT NOT NULL,
            locked_by TEXT,
            locked_until TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_tasks_status_run_after ON web_tasks (status, run_after)")


MIGRATION = WebMigration(
    migration_id="0001_web_platform",
    module="platform",
    description="web idempotency keys + recoverable task records",
    apply=_apply,
)
