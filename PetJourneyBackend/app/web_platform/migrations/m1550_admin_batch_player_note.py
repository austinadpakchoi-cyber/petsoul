"""1550：批量补偿记下「给玩家看的说明」。

账本流水的 `reason` 会原样显示在玩家的星球银行卡上（`routers/web/credentials.py`）。批量补偿以前把**批次的内部原因**
写进了那一栏——员工写给审批人看的话，玩家也看得到。这一列存提交时定下的玩家说明，执行时写进账本；
内部原因仍留在 `reason` 列，只进审计与审批页。

旧批次这一列为空：执行时用默认说明（见 `web_admin/commands.py` 的 `DEFAULT_GRANT_NOTE`），不再回退到内部原因。
已经执行过的旧批次写进账本的文字不改——账本不改写。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE admin_grant_batches ADD COLUMN player_note TEXT")


MIGRATION = WebMigration(
    migration_id="1550_admin_batch_player_note",
    module="web_admin",
    description="grant batches carry the player-facing ledger note separately from the internal reason",
    apply=_apply,
)
