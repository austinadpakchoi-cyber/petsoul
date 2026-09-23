"""1110：消息来源与附图状态（诚实标注：事件/模板/模型写的回信；插画处理中/完成/失败）。"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE web_messages ADD COLUMN composed_by TEXT")
    conn.execute("ALTER TABLE web_messages ADD COLUMN photo_status TEXT")
    conn.execute("ALTER TABLE web_messages ADD COLUMN photo_task_id TEXT")


MIGRATION = WebMigration(
    migration_id="1110_message_meta",
    module="communicator",
    description="message composer (event/template/model) and attached illustration status",
    apply=_apply,
)
