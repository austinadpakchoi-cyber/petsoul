"""图先到终态、消息后插：结果不能被丢掉（C 的 CR-C12，已由 C 在真实 worker 上复现）。

两个执行者之间真实存在一道缝：`on_world_event` 无条件写 `processing`，而
`illustration_ready` / `illustration_failed` 是 `UPDATE ... WHERE photo_task_id = ?`——
消息行还不存在时命中 0 行，结果被丢掉，**之后没有任何事件会再来纠正它**，页面就永远停在"正在画"。

这里在插消息的那一刻取一次这张图的当前状态，把已经拿到的结果写进去。幂等，不重新派发。
一次性临时库；不联网、不调供应商。
"""

from __future__ import annotations

import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.utils import iso
from app.web_communicator import WebCommunicatorService
from task_budget_helpers import open_storage

NOW = datetime(2026, 9, 23, 2, 0, tzinfo=timezone.utc)
PET, HOUSE, TASK, ILLUSTRATION = "pet-1", "hh-1", "wt_task_1", "il-1"
URL = f"/api/v1/web/media/illustrations/{ILLUSTRATION}"


class PhotoMessageOrderTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.storage = open_storage(str(Path(tmp.name) / "order.sqlite3"))
        self.communicator = WebCommunicatorService(self.storage)
        self.communicator.household_of = lambda pet_id: HOUSE

    # ---- 造数 ----
    def illustration(self, status: str) -> None:
        with self.storage.connect() as conn:
            conn.execute("INSERT INTO web_illustrations (illustration_id, user_id, pet_id, source_event_id, task_id, status, created_at, updated_at) "
                         "VALUES (?, 'u-1', ?, 'jn-1:adventure', ?, ?, ?, ?)",
                         (ILLUSTRATION, PET, TASK, status, iso(NOW), iso(NOW)))

    @staticmethod
    def event():
        """世界事件的最小替身：插消息只用到这几项。"""
        return SimpleNamespace(kind="photo_taken", journey=SimpleNamespace(pet_id=PET, user_id="u-1"),
                               visit=SimpleNamespace(place={"name": "信德中心"}), occurred_at=NOW,
                               source_event_id="jn-1:photo", data={"photo_task_id": TASK})

    def message(self):
        with self.storage.connect() as conn:
            return conn.execute("SELECT photo_status, photo_url FROM web_messages WHERE photo_task_id = ?", (TASK,)).fetchone()

    # ---- 缺陷本体：图先好，消息后插 ----
    def test_a_photo_that_finished_before_the_message_is_not_lost(self) -> None:
        self.illustration("ready")
        self.communicator.illustration_ready(TASK, URL)  # 消息还不存在：这一次更新命中 0 行，结果被丢掉

        self.communicator.on_world_event(self.event())  # 消息这时才插进来

        row = self.message()
        self.assertEqual(row["photo_status"], "ready", "图已经画好了，消息不能再写成'正在画'")
        self.assertEqual(row["photo_url"], URL, "而且要带上图的地址")

    def test_a_photo_that_already_failed_before_the_message_is_not_stuck_processing(self) -> None:
        self.illustration("failed")

        self.communicator.on_world_event(self.event())

        self.assertEqual(self.message()["photo_status"], "failed", "不能永远停在'正在画'")

    def test_an_unconfirmed_outcome_is_reported_as_unknown_not_failed(self) -> None:
        """结果不明那一档同样不能丢：装配把插画服务的 `outcome_of` 接进来时要用它的判断。"""
        self.illustration("failed")
        self.communicator.illustration_outcome_in = lambda conn, task_id: "unknown"

        self.communicator.on_world_event(self.event())

        self.assertEqual(self.message()["photo_status"], "unknown", "可能已经受理过，不能说成'没画成'")

    # ---- 第二种交错：读到"正在画"之后、插入之前，worker 才跑完 ----
    def test_a_photo_finishing_between_the_read_and_the_insert_is_not_lost(self) -> None:
        """第一版只是把窗口缩小：读在事务外、插在另一个连接，这条缝原样还在。

        现在读与插在**同一个写事务**里，所以两种到达顺序都对：
        worker 先拿到写锁 → 它的回调命中 0 行，我们随后在同一事务里读到终态；
        我们先拿到写锁 → 先插"正在画"，worker 的回调随后命中这一行。
        """
        self.illustration("processing")
        worker = []

        def finish_in_background() -> None:
            """另一个连接上的 worker：把插画置 ready 并回调。写锁被占时它会等，不是报错。"""
            with self.storage.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("UPDATE web_illustrations SET status = 'ready' WHERE task_id = ?", (TASK,))
            self.communicator.illustration_ready(TASK, URL)

        original = self.communicator._photo_at_insert

        def read_then_let_worker_run(conn, task_id):
            result = original(conn, task_id)  # 这一刻读到的还是"正在画"
            thread = threading.Thread(target=finish_in_background)
            thread.start()
            worker.append(thread)
            thread.join(timeout=0.3)  # 给它机会插队；修好之后它会被写锁挡住，等我们提交
            return result

        self.communicator._photo_at_insert = read_then_let_worker_run
        self.communicator.on_world_event(self.event())
        for thread in worker:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive(), "不该卡住")

        self.assertEqual(self.message()["photo_status"], "ready", "worker 在读与插之间跑完，结果也不能丢")

    def test_the_read_and_the_insert_share_one_connection(self) -> None:
        """结构性断言：读当前状态与插消息必须在同一个连接（同一个写事务）上。"""
        self.illustration("processing")
        opened, original = [], self.storage.connect

        def counting_connect():
            conn = original()
            opened.append(conn)
            return conn

        self.storage.connect = counting_connect
        self.addCleanup(lambda: setattr(self.storage, "connect", original))
        self.communicator.on_world_event(self.event())

        self.assertEqual(len(opened), 1, f"读 ＋ 插应当只开一个连接，实际开了 {len(opened)} 个")

    # ---- 正常顺序：行为一字不变 ----
    def test_the_normal_order_is_unchanged(self) -> None:
        self.illustration("processing")

        self.communicator.on_world_event(self.event())
        row = self.message()
        self.assertEqual((row["photo_status"], row["photo_url"]), ("processing", None), "图还在画：照旧写'正在画'")

        self.communicator.illustration_ready(TASK, URL)  # 图好了，回调照常生效
        self.assertEqual(self.message()["photo_status"], "ready")

    def test_a_task_without_any_illustration_record_still_shows_processing(self) -> None:
        """还没登记插画记录（例如登记与投递之间）：维持'正在画'，不臆断成失败。"""
        self.communicator.on_world_event(self.event())
        self.assertEqual(self.message()["photo_status"], "processing")


if __name__ == "__main__":
    unittest.main()
