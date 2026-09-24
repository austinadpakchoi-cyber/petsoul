"""世界定时器：没人打开页面时，世界照样往前走。

每一轮依次执行：补齐进行中旅程的世界事件 → 自主生活 → 兑现到点的排队回复 → TA 主动发来的消息 → 驾校。
每项任务都是幂等的；读取接口本身也会补齐，所以定时器停了只会让“及时性”变差，不会让结果出错。

可以跑在 API 进程里（后台线程，runner=embedded），也可以跑在独立的任务进程里（python -m app.web_worker）。
不管几个进程，都先拿数据库里的租约（web_platform.lease）：同一时刻只有一个进程推进世界；持有者挂了，租约过期后别的进程接手。
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Callable

from ..utils import utcnow
from ..web_platform.lease import LeaseLost, assert_lease_held
from ..web_platform.uow import lane_fence

logger = logging.getLogger(__name__)

Job = tuple[str, Callable[[datetime], object]]


class WorldTicker:
    def __init__(self, jobs: list[Job], interval_seconds: float = 30.0) -> None:
        self.jobs = jobs
        self.interval = interval_seconds
        self.lease = None  # web_platform.lease.WorkerLease（装配时注入）
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def tick(self, now: datetime | None = None) -> bool:
        """跑一轮；没拿到租约（别的进程在推进世界）时跳过并返回 False。"""
        now = now or utcnow()
        if self.lease is not None and not self.lease.acquire(now):
            return False
        errors: list[str] = []
        # 这一轮开始时记下任期；本轮每一个业务写事务都会在事务里再查一次（一轮可能跑得比租期长）
        fence = None
        if self.lease is not None:
            tenure, name_of_lease = self.lease.tenure(), self.lease.name
            fence = lambda conn: assert_lease_held(conn, name_of_lease, tenure)  # noqa: E731 - 就是一个查询闭包
        with lane_fence(fence):
            self._run_jobs(now, errors)
        if self.lease is not None:
            try:
                self.lease.record_tick(not errors, "; ".join(errors) or None, now)
            except Exception:  # noqa: BLE001 - 状态记录失败不影响世界
                logger.exception("world ticker status record failed")
        return True

    def _run_jobs(self, now: datetime, errors: list[str]) -> None:
        for name, job in self.jobs:
            try:
                job(now)
            except LeaseLost as lost:
                # 租约已被接手：**立刻停住整轮**，剩下的任务（以及同一任务里剩下的宠物）都交给新任期。
                # 正在进行的那个写事务已经整体回滚；这之前已经提交的，是本任期还持有租约时合法写下的，不回滚也不重做。
                # 这里不写任何"失败"记号：退避、决策编号、生活决定都归新任期决定，旧执行者只负责停手。
                logger.warning("world ticker stopped mid-round: %s", lost)
                errors.append(f"{name}: lease_lost")
                return
            except Exception as exc:  # noqa: BLE001 - 单项失败不影响其他任务与下一轮
                logger.exception("world ticker job failed: %s", name)
                errors.append(f"{name}: {type(exc).__name__}")

    def start(self) -> None:
        if self._thread is not None or self.interval <= 0:
            return
        self._thread = threading.Thread(target=self._loop, name="web-world-ticker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        if self.lease is not None:
            try:
                self.lease.release()  # 让别的进程马上接手，不必等租约过期
            except Exception:  # noqa: BLE001
                pass

    def run_forever(self) -> None:
        """独立任务进程用：在当前线程里一直跑，直到 stop()。"""
        self.tick()
        while not self._stop.wait(self.interval):
            self.tick()

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            self.tick()
