"""0260：待领养居民的「是否上架」（宠物区间；用户 2026-09-25 把撤下交给运营后台窗口 adm1 做，I 确认）。

- 撤下＝不再出现在领养卡、访客页，也不能被领养；TA 照常在驿站生活（不暂停、不删除，身份与经历不变）。放回＝恢复。
- 列加在领养卡表上：玩家侧读名单的四处与领养入口都认它（`web_pets/service.py` 的 candidates / adopt / candidate_for_pet，
  `web_residents/service.py` 的 public_list）；写入口只有 `PetsService.set_listed_in`（运营后台在自己的事务里调用）。
- 默认上架：已有的与之后新建的领养卡都照旧可见。谁、什么时候、为什么撤下，由后台另记（`admin_resident_listing`，迁移 1590）。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE web_adoption_candidates ADD COLUMN listed INTEGER NOT NULL DEFAULT 1 CHECK (listed IN (0, 1))")


MIGRATION = WebMigration(
    migration_id="0260_resident_listing",
    module="pets",
    description="adoption candidates can be delisted (hidden from adoption cards and visitor pages, not adoptable) and relisted",
    apply=_apply,
)
