"""0190：模型回信改为默认开启（2026-09-24，用户：「跟宠物的聊天都是固定的，ds 没有参与，请修复」）。

`web_user_prefs.model_replies` 的列默认值是 0（0150 建表时「默认关闭」），而「主人来过」（`touch_active`，
打开页面读会话、发一条私信都会调）只写 user_id / updated_at / last_active_at —— 于是**主人第一次露面就被写进一行 0**，
读取端「没行才用默认值」的规则永远轮不到，改了默认也等于没改。代码侧已让 `touch_active` 插入时显式写默认值；
这里把**旧库里同样来路的行**补正过来。

只补「确定从没选过」的行，**分不清的一律不动**（主人明确关掉的撤权必须尊重）：

  · `timezone IS NULL`：0160 之后，改设置（`set_prefs`）每次都会写入非空时区（没给就补香港），
    所以时区还是空的行，0160 之后从没经过改设置——它的 0 只是列默认值，不是主人的选择。
  · `updated_at >= 0160 的应用时间`：0160 之前的旧代码改设置时还没有时区这一列，那个年代留下的行时区也是空，
    其中可能有「开过又关掉」的真撤权。`touch_active` **只在建行时写一次** `updated_at`，之后从不改（冲突时只改 last_active_at）——
    所以它建出来的行 `updated_at` 就是建行时刻（一定晚于 0160），而旧年代的行停在 0160 之前，据此排除。
    （C 2026-09-24 指出：原先写成「从不改」，照那句去读会以为这条筛选没有依据。）

改过设置、只是没碰模型回信的老行（时区非空、值为 0）也不动：库里分不出「没碰过」和「明确关掉」，按撤权对待；
这些账号要用模型回信得在设置页自己打开一次。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        "UPDATE web_user_prefs SET model_replies = 1 "
        "WHERE model_replies = 0 AND timezone IS NULL "
        "AND updated_at >= (SELECT applied_at FROM web_schema_migrations WHERE migration_id = '0160_agent_prefs')"
    )


MIGRATION = WebMigration(
    migration_id="0190_model_replies_default_on",
    module="identity",
    description="model-written replies default on: backfill rows that only ever came from activity tracking (never a choice)",
    apply=_apply,
)
