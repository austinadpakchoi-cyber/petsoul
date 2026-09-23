"""0030：世界任务进程的租约与运行状态、供应商“实际验证过”的记录（平台共享）。

- web_worker_leases：同一时刻只有一个进程推进世界（旅程事件、自主生活、到点回复、主动消息、驾校），
  API 进程内嵌与独立 worker 进程都先拿租约再干活；租约过期（持有进程挂了）后其他进程接手。所有任务本身幂等，
  所以接手时重跑一轮不会重复发工资、重复扣钱或重复发消息；
- web_provider_health：每个供应商最近一次成功/失败的时间与脱敏错误摘要——“配置了”和“真的调通过”分开报告。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_worker_leases (
            name TEXT PRIMARY KEY,
            holder TEXT NOT NULL,
            pid INTEGER,
            host TEXT,
            role TEXT,
            started_at TEXT NOT NULL,
            heartbeat_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            last_tick_at TEXT,
            last_ok_at TEXT,
            last_error TEXT,
            ticks INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE web_provider_health (
            provider TEXT PRIMARY KEY,
            last_success_at TEXT,
            last_failure_at TEXT,
            last_error TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )


MIGRATION = WebMigration(
    migration_id="0030_worker_status",
    module="platform",
    description="single-runner lease for the world ticker (embedded or separate worker) and provider last-success/failure health",
    apply=_apply,
)
