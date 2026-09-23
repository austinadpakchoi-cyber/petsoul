"""进程租约要管到最终写事务（对应包 A 的 CR-A4）。

只在一轮开头查"我还持有租约吗"是不够的：一轮可能跑得比租期还长。
那时旧进程以为自己还在推进世界，新进程已经接手——两边同时写，工资、事件、投递都可能出两份。
所以每个业务写事务在拿到写锁之后、写业务之前，还要用**这一轮开始时记下的任期**再查一次；
对不上就整笔回滚，剩下的事交给接手的进程。
"""

from __future__ import annotations

import threading
import unittest
from datetime import timedelta

from app.web_agent.ticker import WorldTicker
from app.web_platform.lease import LeaseLost, WorkerLease
from app.web_platform.uow import lane_fence, unit_of_work
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class StaleProposal(Exception):
    """内层那道检查（例如提案版本）失败时抛的东西——和租约失效分开，才看得出是哪一道拦的。"""


class FenceTestBase(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.storage = self.app.state.storage
        with self.storage.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS fence_probe (writer TEXT NOT NULL)")

    def lease(self, role: str) -> WorkerLease:
        return WorkerLease(self.storage, "world", timedelta(seconds=90), role)

    def rows(self) -> list[str]:
        with self.storage.connect() as conn:
            return [r["writer"] for r in conn.execute("SELECT writer FROM fence_probe ORDER BY rowid")]

    def write(self, writer: str) -> None:
        with unit_of_work(self.storage) as conn:
            conn.execute("INSERT INTO fence_probe (writer) VALUES (?)", (writer,))

    def fence(self, label: str, *, ok: bool, seen: list[str]):
        """一道围栏：记下自己跑过了；不合格就抛——租约那道抛 LeaseLost，业务那道抛 StaleProposal。"""
        def check(conn) -> None:
            seen.append(label)
            if not ok:
                raise LeaseLost("world", label) if label == "lease" else StaleProposal(label)

        return check


class LeaseCommitFenceTests(FenceTestBase):
    def test_a_superseded_worker_cannot_commit_its_late_write(self) -> None:
        old = self.lease("worker-old")
        self.assertTrue(old.acquire(self.clock.now))
        tenure = old.tenure()

        self.clock.advance(seconds=120)  # 旧进程这一轮跑得比租期还长
        new = self.lease("worker-new")
        self.assertTrue(new.acquire(self.clock.now), "新进程接手")

        from app.web_platform.lease import assert_lease_held

        with lane_fence(lambda conn: assert_lease_held(conn, "world", tenure)):
            with self.assertRaises(LeaseLost) as lost:
                self.write("old")

        self.assertEqual(lost.exception.reason, "taken_over")
        self.assertEqual(self.rows(), [], "被接手之后旧进程的写入不能落库")

    def test_the_holder_of_the_current_tenure_still_writes(self) -> None:
        holder = self.lease("worker-a")
        self.assertTrue(holder.acquire(self.clock.now))

        from app.web_platform.lease import assert_lease_held

        with lane_fence(lambda conn: assert_lease_held(conn, "world", holder.tenure())):
            self.write("a")

        self.assertEqual(self.rows(), ["a"], "还持有租约就照常写")

    def test_requests_outside_the_lane_are_not_fenced(self) -> None:
        """HTTP 请求线程没有装围栏：命令照常执行（它们由幂等与领域键保证）。"""
        self.write("http")
        self.assertEqual(self.rows(), ["http"])

    def test_a_round_that_loses_the_lease_halfway_rolls_back_and_stops(self) -> None:
        old = self.lease("worker-old")
        self.assertTrue(old.acquire(self.clock.now))
        new = self.lease("worker-new")
        done: list[str] = []

        def first(now) -> None:
            self.write("first")
            done.append("first")
            self.clock.advance(seconds=120)  # 这一轮太久了
            self.assertTrue(new.acquire(self.clock.now), "新进程接手")

        def second(now) -> None:
            self.write("second")  # 旧进程还想接着写
            done.append("second")

        ticker = WorldTicker([("first", first), ("second", second)], interval_seconds=0)
        ticker.lease = old

        ticker.tick(self.clock.now)

        self.assertEqual(done, ["first"], "第二步在事务里被围栏挡下")
        self.assertEqual(self.rows(), ["first"], "只有接手之前那一笔留下来了")


class NestedFenceTests(FenceTestBase):
    """两道围栏叠在一起时的组合语义：内层不能把外层顶掉（CR-C10）。

    这不是假想：提案版本复核与进程租约围栏都要落在同一个写事务里，一旦谁用 `lane_fence` 包一层做自己的检查，
    外层那道租约就会被 ContextVar 覆盖掉——世界会在旧任期上继续写。
    """

    def test_an_inner_fence_does_not_cancel_the_outer_lease_check(self) -> None:
        seen: list[str] = []

        with lane_fence(self.fence("lease", ok=False, seen=seen)):
            with lane_fence(self.fence("versions", ok=True, seen=seen)):
                with self.assertRaises(LeaseLost, msg="内层自己的检查过了，不代表租约还在"):
                    self.write("inner")

        self.assertIn("lease", seen, "外层那道租约检查必须仍然执行")
        self.assertEqual(self.rows(), [], "租约已经不是这个任期了，一个字都不该写进去")

    def test_lane_fence_none_does_not_lift_an_existing_fence(self) -> None:
        """`None` 的意思是"我不追加检查"，不是"把已经装上的解除掉"。"""
        seen: list[str] = []

        with lane_fence(self.fence("lease", ok=False, seen=seen)):
            with lane_fence(None):
                with self.assertRaises(LeaseLost):
                    self.write("none")

        self.assertEqual(seen, ["lease"])
        self.assertEqual(self.rows(), [])

    def test_both_fences_run_outermost_first_and_both_must_pass(self) -> None:
        seen: list[str] = []

        with lane_fence(self.fence("lease", ok=True, seen=seen)):
            with lane_fence(self.fence("versions", ok=False, seen=seen)):
                with self.assertRaises(StaleProposal):
                    self.write("blocked")
            self.assertEqual(seen, ["lease", "versions"], "外层先过，两道都要过")
            self.write("after")  # 内层那道退出了，只剩租约

        self.assertEqual(self.rows(), ["after"])

    def test_the_outer_fence_comes_back_after_an_inner_block_raises(self) -> None:
        seen: list[str] = []

        with lane_fence(self.fence("lease", ok=False, seen=seen)):
            with self.assertRaises(StaleProposal):
                with lane_fence(self.fence("versions", ok=True, seen=seen)):
                    raise StaleProposal("内层块里出了别的错")
            with self.assertRaises(LeaseLost, msg="内层块退出之后，外层那道要回来"):
                self.write("after-error")

        self.assertEqual(self.rows(), [])

    def test_a_fence_installed_here_does_not_follow_a_bare_thread(self) -> None:
        """事实陈述，范围只到这一条：裸 `threading.Thread` 里的写入**不带**外面装的围栏。

        被测环境：CPython 3.12.2 / Windows 11（本仓库的后端测试环境）。
        **不要据此推广**到线程池、`asyncio` 任务或 `run_in_executor`——那些入口怎么传上下文由调用方式决定，这里没有验。
        后台线要围住自己的写，就在那个线程／任务里自己装一次（`ticker.tick` 就是这么做的）。
        """
        with lane_fence(self.fence("lease", ok=False, seen=[])):
            worker = threading.Thread(target=self.write, args=("thread",))
            worker.start()
            worker.join()

        self.assertEqual(self.rows(), ["thread"], "新线程没有继承围栏——要围住它，必须在它里面装")


if __name__ == "__main__":
    unittest.main()
