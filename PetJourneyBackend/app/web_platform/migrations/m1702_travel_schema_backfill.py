"""1702：补齐早期 m1700 在已有库上留下的差异（A；编号由总集成分配）。新库上是空操作。

m1700 在被库应用过之后又改过，而迁移执行器只按编号记「已应用」、不看内容——更早应用了 m1700 的库不会再跑新版。
2026-09-24 只读扫了工作区全部库：3 个是旧版（本地 06:27–06:55 应用），与现行版差三处：
  1. 没有 `web_travel_considerations`（按宠物存「上次考虑」，合同 §21.1）：心跳一调 `considered_in` 就报没有这张表。
     → 补建，`IF NOT EXISTS`，新库上不动；
  2. `web_travel_facts.verdict` 的 CHECK 是旧值 `'conflict'`，代码写的是 `'conflicting'`。当时 store 用 `INSERT OR IGNORE`，
     它连 CHECK 违例一起吞：冲突事实被**悄悄丢掉**、计划照常发布、没有任何报错（实测；store 已改成 `ON CONFLICT DO NOTHING`，
     现在同样情况会当场报错、整次发布回滚）。
     SQLite 改不了 CHECK，照官方做法重建这张表：建新表、拷数据时把 `'conflict'` 改成 `'conflicting'`、删旧表、改名、重建索引。
     只在检测到旧约束时做，新库上不动；
  3. `web_travel_journals` 多出 `image_status`、`image_url` 两列 → **不动**：可以为空，代码不读不写（图的状态不是列，合同 §22.2），
     删列要重建表，不值当。
**已应用过的迁移不再改，要改就新开一个号**——这一条就是那次违例的补丁。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration

FACTS_COLUMNS = ("fact_id", "operation_id", "wish_id", "category", "subject", "value_json", "source_ids_json", "retrieved_at",
                 "published_at", "observed_at", "valid_from", "valid_until", "verification", "conclusion", "verdict", "blocks_departure",
                 "created_at")


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS web_travel_considerations (
            pet_id TEXT PRIMARY KEY,
            last_considered_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    facts = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'web_travel_facts'").fetchone()
    if facts is None or "'conflicting'" in facts[0]:
        return  # 现行版建的库：约束已经对了
    conn.execute(
        """
        CREATE TABLE web_travel_facts_new (
            fact_id TEXT PRIMARY KEY,
            operation_id TEXT NOT NULL,
            wish_id TEXT NOT NULL,
            category TEXT NOT NULL,
            subject TEXT NOT NULL,
            value_json TEXT NOT NULL,
            source_ids_json TEXT NOT NULL,
            retrieved_at TEXT,
            published_at TEXT,
            observed_at TEXT,
            valid_from TEXT,
            valid_until TEXT,
            verification TEXT NOT NULL,
            conclusion TEXT,
            verdict TEXT NOT NULL CHECK (verdict IN ('verified', 'unverified', 'stale', 'conflicting', 'rejected')),
            blocks_departure INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
    columns = ", ".join(FACTS_COLUMNS)
    selected = ", ".join("CASE verdict WHEN 'conflict' THEN 'conflicting' ELSE verdict END" if c == "verdict" else c for c in FACTS_COLUMNS)
    conn.execute(f"INSERT INTO web_travel_facts_new ({columns}) SELECT {selected} FROM web_travel_facts")
    conn.execute("DROP TABLE web_travel_facts")
    conn.execute("ALTER TABLE web_travel_facts_new RENAME TO web_travel_facts")
    conn.execute("CREATE INDEX ix_travel_facts_operation ON web_travel_facts (operation_id)")


MIGRATION = WebMigration(
    migration_id="1702_travel_schema_backfill",
    module="travel",
    description="backfill databases that applied an early m1700: add web_travel_considerations, rebuild web_travel_facts with the 'conflicting' verdict",
    apply=_apply,
)
