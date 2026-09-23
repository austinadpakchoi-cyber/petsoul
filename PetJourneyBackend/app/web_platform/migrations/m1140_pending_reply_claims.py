"""1140：待回复的领取可以过期回收，最终写入按领取令牌核对（修 G5 / 验收 CR-Q4）。

- claimed_until：领取期限。领取者崩溃后，期限一过别的进程可以重新领取，不再永远卡在 claim-*；
- outcome：delivered（已回复）/ suppressed（发布前复核发现这位家人已不在家庭里，不再回复）。
旧数据：没有期限的 claim-* 视为已过期，下一轮就会被重新领取。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE web_pending_replies ADD COLUMN claimed_until TEXT")
    conn.execute("ALTER TABLE web_pending_replies ADD COLUMN outcome TEXT")


MIGRATION = WebMigration(
    migration_id="1140_pending_reply_claims",
    module="communicator",
    description="pending-reply claims expire and are fenced by claim token; outcome delivered/suppressed",
    apply=_apply,
)
