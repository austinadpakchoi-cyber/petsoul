"""m1702：已有库升级时补齐早期 m1700 留下的差异（TRV-03；I 提醒，实测 3 个库属实）。不联网、0 次付费调用。

旧库的形状**照实抄**真库：`OLD_FACTS` 是 2026-09-24 从 `PetJourneyBackend/data/petjourney.sqlite3` 只读取出的建表语句，另两个旧库相同。
做法：先按现行迁移建库，再退回旧形状（删掉 considerations、facts 换回旧约束、journals 加回两列、抹掉 m1702 的登记），再跑一次升级。
钉的是：
  - 缺陷真的在（对照）：旧库上，一份带冲突事实的研究结果**当场报错、整次发布回滚**，应答留着。这是 store 加固后的行为；
    加固前 store 用 `INSERT OR IGNORE`，同样情况是冲突事实**被悄悄丢掉**、计划照常发布——我原先以为会回滚，是这条对照抓出来的；
  - 升级之后同一份结果能发布，缺的表建出来了，旧值 'conflict' 改成了 'conflicting'，索引还在，多出的两列按约定不动；
  - 现行版建的库上 m1702 是空操作，再跑一次也不改任何东西；
  - store 的「跳过重复」只跳过重复：约束违例报错，同一行重复插入照样无事。
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from task_budget_helpers import open_storage
from travel_wish_fakes import TravelResearchTestBase, good_result

from app.utils import iso, utcnow
from app.web_platform.migrations import apply_web_migrations
from app.web_platform.migrations.m1702_travel_schema_backfill import MIGRATION
from app.web_platform.uow import unit_of_work
from app.web_travel import store
from app.web_travel.ports import ResearchFact
from app.web_travel.service import TravelWishService

OLD_FACTS = """CREATE TABLE web_travel_facts (
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
            verdict TEXT NOT NULL CHECK (verdict IN ('verified', 'unverified', 'stale', 'conflict', 'rejected')),
            blocks_departure INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )"""


def fact_row(fact_id: str, verdict: str) -> dict:
    return {"fact_id": fact_id, "operation_id": "op-old", "wish_id": "wish-old", "category": "route", "subject": "浅水湾", "value_json": '"x"',
            "source_ids_json": "[]", "verification": "map", "verdict": verdict, "created_at": "2026-09-23T22:30:00+00:00"}


def regress_to_early_m1700(storage, *, old_rows=()) -> None:
    """把现行版建的库退回早期 m1700 的形状（与 3 个真旧库逐表比对过）。"""
    with storage.connect() as conn:
        conn.execute("DROP TABLE web_travel_considerations")
        conn.execute("DROP TABLE web_travel_facts")
        conn.execute(OLD_FACTS)
        conn.execute("CREATE INDEX ix_travel_facts_operation ON web_travel_facts (operation_id)")
        conn.execute("ALTER TABLE web_travel_journals ADD COLUMN image_status TEXT")
        conn.execute("ALTER TABLE web_travel_journals ADD COLUMN image_url TEXT")
        conn.execute("DELETE FROM web_schema_migrations WHERE migration_id = ?", (MIGRATION.migration_id,))
        for fact_id, verdict in old_rows:
            row = fact_row(fact_id, verdict)
            conn.execute(f"INSERT INTO web_travel_facts ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})", tuple(row.values()))


def facts_sql(storage) -> str:
    with storage.connect() as conn:
        return conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'web_travel_facts'").fetchone()[0]


class TravelSchemaBackfillTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.storage = open_storage(str(Path(tmp.name) / "early.sqlite3"))

    def test_an_early_database_gets_the_missing_table_and_the_current_verdicts(self) -> None:
        regress_to_early_m1700(self.storage, old_rows=(("tf-old-1", "conflict"), ("tf-old-2", "verified")))
        self.assertNotIn("'conflicting'", facts_sql(self.storage), "前提：退回了旧约束")
        applied = apply_web_migrations(self.storage)

        self.assertIn(MIGRATION.migration_id, applied)
        wishes = TravelWishService(self.storage, None)
        with unit_of_work(self.storage) as conn:
            wishes.considered_in(conn, "pet-1", "2026-09-24T05:00:00+00:00")
        with self.storage.connect() as conn:
            self.assertEqual(wishes.last_considered_in(conn, "pet-1"), "2026-09-24T05:00:00+00:00", "缺的表建出来了，端口能用")
            rows = dict(conn.execute("SELECT fact_id, verdict FROM web_travel_facts").fetchall())
            self.assertEqual(rows, {"tf-old-1": "conflicting", "tf-old-2": "verified"}, "旧值改成现行值，其余原样")
            indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'web_travel_facts'")}
            self.assertIn("ix_travel_facts_operation", indexes)
            journal_columns = {r[1] for r in conn.execute("PRAGMA table_info(web_travel_journals)")}
            self.assertTrue({"image_status", "image_url"} <= journal_columns, "多出的两列按约定不动")

    def test_on_a_current_database_it_changes_nothing(self) -> None:
        before = facts_sql(self.storage)
        self.assertTrue(before.startswith("CREATE TABLE web_travel_facts ("), "前提：现行 m1700 建的表，没被重建过（重建会带引号）")
        with unit_of_work(self.storage) as conn:
            MIGRATION.apply(conn)  # 再跑一次
        self.assertEqual(facts_sql(self.storage), before)

    def test_skipping_duplicates_does_not_swallow_constraint_violations(self) -> None:
        """`INSERT OR IGNORE` 会连 CHECK 违例一起吞，旧库上的冲突事实就是这样无声丢掉的；现在只跳过重复。"""
        with unit_of_work(self.storage) as conn:
            store.insert_facts_in(conn, [fact_row("tf-1", "verified")])
            store.insert_facts_in(conn, [fact_row("tf-1", "verified")])  # 同一行重复：无事
        with self.assertRaises(sqlite3.IntegrityError):
            with unit_of_work(self.storage) as conn:
                store.insert_facts_in(conn, [fact_row("tf-2", "made-up")])
        with self.storage.connect() as conn:
            self.assertEqual([r[0] for r in conn.execute("SELECT fact_id FROM web_travel_facts")], ["tf-1"])


class EarlyDatabaseResearchTests(TravelResearchTestBase):
    """产品层面的那个坏法：旧约束下，冲突事实写不进去。"""

    def answer_with_conflicting_prices(self):
        observed = iso(utcnow() - timedelta(days=1))
        prices = tuple(ResearchFact(key, "ticket_price", "浅水湾", {"amount": amount, "currency": "HKD", "estimated": False}, ("s-web",),
                                    observed_at=observed, verification="search") for key, amount in (("fee-a", 10), ("fee-b", 20)))
        return good_result(facts=good_result().facts + prices)

    def test_before_the_backfill_a_conflicting_fact_fails_the_publish_loudly(self) -> None:
        """对照：没有这一条，下面那条全绿也可能只是因为冲突根本没发生。"""
        regress_to_early_m1700(self.storage)
        self.port.result = self.answer_with_conflicting_prices()
        self.propose()
        self.research.run_pending()
        self.assertEqual(self.plans(), [], "旧约束：写冲突事实当场报错，整次发布回滚")
        self.assertEqual([r["status"] for r in self.receipts()], ["answered"], "应答还存着，留给升级后复用")
        self.assertEqual(self.task()["last_error"], "IntegrityError", "报出来了，不是悄悄丢掉")

    def test_after_the_backfill_the_same_answer_publishes(self) -> None:
        regress_to_early_m1700(self.storage)
        apply_web_migrations(self.storage)
        self.port.result = self.answer_with_conflicting_prices()
        self.propose()
        self.research.run_pending()
        self.assertEqual(len(self.plans()), 1)
        verdicts = [r["verdict"] for r in self.query("SELECT verdict FROM web_travel_facts WHERE category = 'ticket_price'")]
        self.assertEqual(verdicts, ["conflicting", "conflicting"])


if __name__ == "__main__":
    unittest.main()
