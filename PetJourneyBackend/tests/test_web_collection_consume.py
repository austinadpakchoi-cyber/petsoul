"""借车券的同事务核销（CR-I-to-A2）：`consume_in` 在**调用方已经开好的写事务**里执行——
券和它换来的东西要么一起成立、要么一起没发生；同一张券也不会被两处同时用掉。

一次性临时库 ＋ 真实 web 迁移 ＋ 真实 `WebCollectionService`；不联网、不调供应商、不碰真实库。
"""

from __future__ import annotations

import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.web_collection.service import WebCollectionService
from app.web_platform.uow import unit_of_work
from task_budget_helpers import open_storage

NOW = datetime(2026, 9, 23, 4, 0, tzinfo=timezone.utc)
PET = "pet-consume"
KIND = "driving_voucher"


class CollectionConsumeInTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.storage = open_storage(str(Path(tmp.name) / "collection.sqlite3"))
        self.collection = WebCollectionService(self.storage)
        with self.storage.connect() as conn:  # 替身“券换来的东西”：调用方在同一个事务里写的业务数据
            conn.execute("CREATE TABLE probe_trip (trip_id TEXT PRIMARY KEY)")

    # ---- 辅助 ----
    def grant(self, source: str = "src-1") -> None:
        with self.storage.connect() as conn:
            WebCollectionService.keepsake(conn, user_id="u-1", pet_id=PET, kind=KIND, title="借车券",
                                          note="驾校发的", source_event_id=source, now=NOW)

    def count(self, sql: str) -> int:
        with self.storage.connect() as conn:
            return conn.execute(f"SELECT COUNT(*) AS n FROM {sql}").fetchone()["n"]

    def unused(self) -> int:
        return self.count(f"web_collection_items WHERE pet_id = '{PET}' AND kind = '{KIND}' AND consumed_at IS NULL")

    def trips(self) -> int:
        return self.count("probe_trip")

    # ---- 同生共死 ----
    def test_a_rolled_back_caller_transaction_leaves_the_voucher_unused(self) -> None:
        """核销之后调用方那一步失败：券必须跟着回滚，不能出现“券没了、车也没借到”。"""
        self.grant()
        with self.assertRaises(RuntimeError):
            with unit_of_work(self.storage) as conn:
                self.assertTrue(WebCollectionService.consume_in(conn, PET, KIND, NOW))
                conn.execute("INSERT INTO probe_trip (trip_id) VALUES ('trip-1')")
                raise RuntimeError("行程写到一半失败了")
        self.assertEqual(self.unused(), 1, "券还在，主人可以再用一次")
        self.assertEqual(self.trips(), 0)

    def test_a_committed_caller_transaction_spends_it_exactly_once(self) -> None:
        self.grant()
        with unit_of_work(self.storage) as conn:
            self.assertTrue(WebCollectionService.consume_in(conn, PET, KIND, NOW))
            conn.execute("INSERT INTO probe_trip (trip_id) VALUES ('trip-1')")
        self.assertEqual((self.unused(), self.trips()), (0, 1), "券和行程一起提交")
        with unit_of_work(self.storage) as conn:
            self.assertFalse(WebCollectionService.consume_in(conn, PET, KIND, NOW), "同一张券不能核销第二次")

    def test_without_a_voucher_it_reports_false_and_writes_nothing(self) -> None:
        with unit_of_work(self.storage) as conn:
            self.assertFalse(WebCollectionService.consume_in(conn, PET, KIND, NOW))
        self.assertEqual(self.count("web_collection_items"), 0, "没有券时不新建、不改任何行")

    def test_it_does_not_commit_on_its_own(self) -> None:
        """只核销、不提交：调用方没提交之前，另一个连接读到的券仍然是可用的。"""
        self.grant()
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self.assertTrue(WebCollectionService.consume_in(conn, PET, KIND, NOW))
            self.assertEqual(self.unused(), 1, "还没提交，别的连接不该看到核销")
            conn.execute("ROLLBACK")
        self.assertEqual(self.unused(), 1)

    # ---- 并发：同一张券只能有一方拿到 ----
    def test_two_callers_cannot_spend_the_same_voucher(self) -> None:
        self.grant()
        results: list[bool] = []
        lock, start = threading.Lock(), threading.Barrier(2)

        def spend() -> None:
            start.wait(timeout=10)
            with unit_of_work(self.storage) as conn:  # BEGIN IMMEDIATE：后到的那个等前一个提交完（连接 timeout=15）
                got = WebCollectionService.consume_in(conn, PET, KIND, NOW)
            with lock:
                results.append(got)

        threads = [threading.Thread(target=spend) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            self.assertFalse(thread.is_alive(), "不该卡住")
        self.assertEqual(sorted(results), [False, True], "一张券只能被用掉一次，另一方走原价路径")
        self.assertEqual(self.unused(), 0)

    # ---- 自开事务的老接口保持原样 ----
    def test_the_self_contained_consume_still_works_as_before(self) -> None:
        self.grant()
        self.assertTrue(self.collection.consume(PET, KIND, NOW))
        self.assertEqual(self.unused(), 0)
        self.assertFalse(self.collection.consume(PET, KIND, NOW))
        self.assertFalse(self.collection.consume(PET, "no_such_kind", NOW))


if __name__ == "__main__":
    unittest.main()
