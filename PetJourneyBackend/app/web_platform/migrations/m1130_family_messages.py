"""1130：星球通讯器的“家庭频道”。

- 私聊：某位主人与某只宠物之间，按 (user_id, pet_id) 独立；新成员加入不能看到别人的历史私聊；
- 家庭频道：宠物把实际发生的事（出发、到站、工资、守菜、驾考、明信片……）发给全家；同一件事对同一只宠物只存一条
  （沿用 UNIQUE(pet_id, source_event_id)），每位成员各自保存已读状态（web_message_reads 本来就按 (user_id, pet_id)）。
- 家庭频道的消息 user_id 记为 '*'（不属于任何一位成员），并记录 household_id。旧消息都在原主人的私聊里，保持不动。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE web_messages ADD COLUMN channel TEXT NOT NULL DEFAULT 'private'")
    conn.execute("ALTER TABLE web_messages ADD COLUMN household_id TEXT")
    conn.execute("CREATE INDEX idx_web_messages_channel ON web_messages (pet_id, channel, available_at)")


MIGRATION = WebMigration(
    migration_id="1130_family_messages",
    module="communicator",
    description="family channel for event messages shared by all household members; private threads stay per (user, pet)",
    apply=_apply,
)
