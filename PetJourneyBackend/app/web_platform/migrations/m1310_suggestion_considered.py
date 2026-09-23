"""1310：家人的建议多记一个"这次考虑过了"的时刻（平台共享）。

原来 TA 一出门就把所有还在考虑中的建议一股脑标成 accepted / passed：
选中的那条算采纳没问题，其余的其实只是"这次没选它"，24 小时窗口内 TA 还可能去。
把它们留在 pending、只记 considered_at，窗口过了再由世界线统一置成 passed（验收 CR-C4）。
编号排在 1300（建这张表的那条）之后。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    # 开发库里可能已经被更早一版（编号排错、排在建表之前的那条）加过这一列，照样要能跑过去
    columns = [row[1] for row in conn.execute("PRAGMA table_info(web_owner_suggestions)")]
    if "considered_at" not in columns:
        conn.execute("ALTER TABLE web_owner_suggestions ADD COLUMN considered_at TEXT")


MIGRATION = WebMigration(
    migration_id="1310_suggestion_considered",
    module="platform",
    description="record when a still-pending owner suggestion was considered, instead of closing it on the first outing",
    apply=_apply,
)
