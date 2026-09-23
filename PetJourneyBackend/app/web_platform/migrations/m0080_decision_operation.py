"""0080：把"这一轮自主决策"的逻辑编号持久化（平台共享）。

原来编号是 `life:{pet}:{到分钟}:{随机}`：同一轮思考崩溃后重试会生成新编号，额度按两次算，
包 A 的重放保护（同编号在途 → 拒绝；已结算 → 原样返回）永远触发不了（验收 CR-A2）。
存下来之后，重试、重启、跨分钟恢复都复用同一个编号；这一轮有了明确结果才清掉，下一轮才是新编号。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE web_entity_runtime ADD COLUMN decision_operation_id TEXT")
    conn.execute("ALTER TABLE web_entity_runtime ADD COLUMN decision_started_at TEXT")


MIGRATION = WebMigration(
    migration_id="0080_decision_operation",
    module="platform",
    description="persist the in-flight autonomous decision operation id so retries and restarts reuse it",
    apply=_apply,
)
