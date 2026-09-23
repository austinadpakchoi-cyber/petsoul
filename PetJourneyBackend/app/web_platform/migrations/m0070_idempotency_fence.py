"""0070：幂等回执加一道领取围栏（平台共享）。

占位超时被别人接手之后，卡住的旧执行者可能很久以后才醒过来写回执。没有围栏它会把接手者的结果覆盖掉，
后续重放拿到的就是那份过期结果（验收合同 Q-C3d）。这里给每次领取一个随机令牌：
写回执时必须带上自己领取时的令牌，被接手过就写不进去。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE web_idempotency_keys ADD COLUMN claim_token TEXT")


MIGRATION = WebMigration(
    migration_id="0070_idempotency_fence",
    module="platform",
    description="claim token on idempotency receipts so a superseded executor cannot overwrite the taker's result",
    apply=_apply,
)
