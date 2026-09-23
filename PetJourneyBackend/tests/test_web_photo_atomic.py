"""同事务拍照登记（COORD-A-ATOMIC 方案 B）：任务、插画记录与调用方的业务写入同生共死。

为什么要这条：旧的事务外登记（自己开连接排队）会在版本冲突或租约被接手时留下**孤儿任务**
——镜头没响、事件没写，队列里却多了一张要画的照片，而且它会真的去花钱。

一次性临时库 ＋ 真实 `WebTaskQueue` / `IllustrationService`；不联网、不调供应商、无付费。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from pathlib import Path

from app.utils import iso
import app.web_journey.illustrations as illustrations_mod
import app.web_platform.tasks as tasks_mod
from app.web_journey.illustrations import IllustrationService
from app.web_platform.tasks import WebTaskQueue
from app.web_platform.uow import unit_of_work
from task_budget_helpers import open_storage

SHOT_AT = datetime(2026, 9, 23, 3, 30, tzinfo=timezone.utc)  # 主人按下“拍一张”的那一刻
OWNER, PET, SOURCE = "u-1", "pet-1", "photo:vi-1"


class FakeIllustrator:
    available = True
    provider_label = "测试生图"


class PhotoAtomicRegistrationTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.storage = open_storage(str(root / "atomic.sqlite3"))
        self.queue = WebTaskQueue(self.storage)
        self.illustrations = IllustrationService(self.storage, root / "media", self.queue)
        self.illustrations.illustrator = FakeIllustrator()
        self.illustrations.opted_in = lambda user_id, pet_id=None: True
        with self.storage.connect() as conn:  # 替身“业务写入”：调用方在同一个事务里写的东西
            conn.execute("CREATE TABLE probe_visit (visit_id TEXT PRIMARY KEY)")

    # ---- 辅助 ----
    def register(self, conn, *, source_key: str = SOURCE, captured_at=SHOT_AT) -> str | None:
        return self.illustrations.request_photo_in(
            conn, OWNER, PET, source_key, place="信德中心", city="香港", scene="在店里靠窗的位置坐着",
            captured_at=captured_at, scene_key="cafe")

    def count(self, table: str, where: str = "1=1") -> int:
        with self.storage.connect() as conn:
            return conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {where}").fetchone()["n"]

    def payload_of(self, task_id: str) -> dict:
        with self.storage.connect() as conn:
            return json.loads(conn.execute("SELECT payload_json FROM web_tasks WHERE task_id = ?", (task_id,)).fetchone()["payload_json"])

    # ---- 同生共死 ----
    def test_a_rolled_back_caller_transaction_leaves_no_orphan_task(self) -> None:
        """调用方那一步失败：任务和插画记录都必须跟着回滚，不能留下一张要画的照片。"""
        with self.assertRaises(RuntimeError):
            with unit_of_work(self.storage) as conn:
                self.assertIsNotNone(self.register(conn))
                conn.execute("INSERT INTO probe_visit (visit_id) VALUES ('vi-1')")
                raise RuntimeError("版本冲突，这一步失败了")
        self.assertEqual(self.count("web_tasks"), 0, "不能留下孤儿任务——它会真的去花钱")
        self.assertEqual(self.count("web_illustrations"), 0)
        self.assertEqual(self.count("probe_visit"), 0)

    def test_a_committed_caller_transaction_registers_everything_together(self) -> None:
        with unit_of_work(self.storage) as conn:
            task_id = self.register(conn)
            conn.execute("INSERT INTO probe_visit (visit_id) VALUES ('vi-1')")
        self.assertEqual((self.count("web_tasks"), self.count("web_illustrations"), self.count("probe_visit")), (1, 1, 1))
        with self.storage.connect() as conn:
            row = conn.execute("SELECT status, dedupe_key FROM web_tasks WHERE task_id = ?", (task_id,)).fetchone()
        self.assertEqual((row["status"], row["dedupe_key"]), ("queued", f"illustration:{SOURCE}"))

    def test_it_does_not_commit_on_its_own(self) -> None:
        """只登记、不提交：调用方还没提交之前，另一个连接读不到这张任务。"""
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self.assertIsNotNone(self.register(conn))
            self.assertEqual(self.count("web_tasks"), 0, "还没提交，别的连接不该看到")
            conn.execute("ROLLBACK")
        self.assertEqual(self.count("web_tasks"), 0)

    # ---- 幂等：同一次拍照不会排两张 ----
    def test_the_same_source_key_registers_only_one_task(self) -> None:
        with unit_of_work(self.storage) as conn:
            first = self.register(conn)
        with unit_of_work(self.storage) as conn:
            second = self.register(conn)
        self.assertEqual(first, second, "同一次拍照重复登记要拿回同一张任务")
        self.assertEqual((self.count("web_tasks"), self.count("web_illustrations")), (1, 1), "不能多排一张（多排就是多花一次钱）")

    # ---- 拍摄时刻按原样存下，不被登记时钟顶掉 ----
    def register_at(self, moment: datetime, *, captured_at: datetime) -> str:
        """把**登记时钟**固定到 `moment` 再登记一次，返回任务号。

        两个时钟必须分别控制：`captured_at` 是主人按下快门那一刻（调用方给的事实），
        `moment` 是这条任务被写进队列那一刻（系统时钟）。
        以前这条用例靠"和现在差得够远"间接判断，等于把一个固定日历时刻当成永远是过去——
        真在那个时刻前后跑就会红（2026-09-23 全量那次就差 54.868 秒）。
        """
        with mock.patch.object(tasks_mod, "utcnow", return_value=moment):
            with mock.patch.object(illustrations_mod, "utcnow", return_value=moment):
                with unit_of_work(self.storage) as conn:
                    return self.register(conn, captured_at=captured_at)

    def created_at_of(self, task_id: str) -> str:
        with self.storage.connect() as conn:
            return conn.execute("SELECT created_at FROM web_tasks WHERE task_id = ?", (task_id,)).fetchone()["created_at"]

    def assert_capture_time_survives(self, registered_at: datetime, captured_at: datetime) -> None:
        """登记时钟与拍摄时刻各是各的：两个都精确断言，不靠"差得够远"这种相对判断。"""
        task_id = self.register_at(registered_at, captured_at=captured_at)
        payload = self.payload_of(task_id)
        self.assertEqual(payload["captured_at"], iso(captured_at), "存的必须是主人按下快门那一刻，原样不动")
        self.assertEqual(self.created_at_of(task_id), iso(registered_at), "入库时刻必须是登记那一刻的系统时钟")
        self.assertEqual(payload["scene_key"], "cafe", "场景键由调用方显式给出，不在这里推导")

    def test_the_capture_time_is_stored_as_given_when_registered_moments_later(self) -> None:
        """近时间：登记发生在快门之后几十秒。**本用例只登记，不跑 worker**——
        它证明的是"登记这一步没有用系统时钟顶掉 captured_at"，不涉及执行阶段。"""
        self.assert_capture_time_survives(SHOT_AT + timedelta(seconds=54.868), captured_at=SHOT_AT)

    def test_the_capture_time_is_stored_as_given_across_a_day_boundary(self) -> None:
        """跨日：快门在前一天深夜，登记发生在第二天凌晨。同样只登记，不跑 worker。"""
        shutter = datetime(2026, 9, 22, 23, 58, tzinfo=timezone.utc)
        self.assert_capture_time_survives(shutter + timedelta(minutes=5), captured_at=shutter)

    def test_the_capture_time_is_stored_as_given_when_the_two_moments_coincide(self) -> None:
        """两个时刻恰好相同也要成立——**这一条是防误报的边界，不是判别器**。

        旧写法在这种情况下会假红（它靠"和现在差得够远"判断），全量那次就是差 54.868 秒被判失败。
        反向对照里它也**不会**转红：把 captured_at 顶成登记时刻时，两个值本来就相等，无从分辨。
        真正能抓住"被顶掉"的是上面那两条（相差几十秒、跨日）。
        """
        self.assert_capture_time_survives(SHOT_AT, captured_at=SHOT_AT)

    def test_a_missing_capture_time_is_absent_rather_than_null(self) -> None:
        """没给拍摄时刻就不要这个键——“没有这个事实”和“这个事实是 None”要分得开。"""
        with unit_of_work(self.storage) as conn:
            task_id = self.register(conn, captured_at=None)
        self.assertNotIn("captured_at", self.payload_of(task_id))

    # ---- 授权必须在调用方那个连接上读 ----
    def test_permission_is_read_on_the_callers_connection_not_a_fresh_one(self) -> None:
        """调用方事务里刚撤权（还没提交）时，登记就必须被挡下。

        另开连接的 `opted_in` 读到的是事务开始前的快照，这一刻还是"允许"——
        用它做判断，等于在一个已经决定要撤权的事务里又排了一张要花钱的照片。
        同连接的 `consent_in` 读得到本事务的未提交改动，所以必须用它。
        """
        with self.storage.connect() as conn:
            conn.execute("CREATE TABLE probe_consent (pet_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL)")
            conn.execute("INSERT INTO probe_consent (pet_id, enabled) VALUES (?, 1)", (PET,))
        # opted_in 故意停在"允许"——它代表另开连接读到的旧快照
        self.illustrations.opted_in = lambda user_id, pet_id=None: True
        self.illustrations.consent_in = lambda conn, user_id, pet_id: bool(
            conn.execute("SELECT enabled FROM probe_consent WHERE pet_id = ?", (pet_id,)).fetchone()["enabled"])

        with unit_of_work(self.storage) as conn:
            conn.execute("UPDATE probe_consent SET enabled = 0 WHERE pet_id = ?", (PET,))  # 同一个事务里撤权，尚未提交
            self.assertIsNone(self.register(conn), "同连接已经读得到撤权，不该再登记")

        self.assertEqual((self.count("web_tasks"), self.count("web_illustrations")), (0, 0))

    # ---- 没授权就什么都不写 ----
    def test_without_permission_nothing_is_registered(self) -> None:
        self.illustrations.opted_in = lambda user_id, pet_id=None: False
        with unit_of_work(self.storage) as conn:
            self.assertIsNone(self.register(conn))
        self.assertEqual((self.count("web_tasks"), self.count("web_illustrations")), (0, 0))


if __name__ == "__main__":
    unittest.main()
