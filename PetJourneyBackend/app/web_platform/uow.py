"""UnitOfWork：一次业务事务只用一个 SQLite 连接。

参与的仓储与账本方法接受这个连接（``conn=`` 参数或 ``*_in(conn, …)``），不自己连接、提交或回滚；
块正常结束才提交，任何异常整体回滚。BEGIN IMMEDIATE 先拿写锁，竞争时由连接的等待超时排队；
事务里不做网络调用——模型、地图、生图都放到提交之后。

**进程租约围栏**：后台线程在一轮开始时用 ``lane_fence`` 把"我这一任期还持有租约吗"装上；
之后这条线里每一个 unit_of_work 在拿到写锁之后、写业务之前都会再查一次。
只在循环开头查是不够的——一轮可能跑得比租期还长，那时旧进程与接手的新进程会同时写（验收 CR-A4）。

围栏是**叠加**的：``lane_fence`` 嵌套时外层与内层都要过，任何一道抛异常都整笔不写；``lane_fence(None)``
表示"我不追加检查"，**不会**解除已经装上的那道（验收 CR-C10）。块退出或抛异常之后恢复进入前的那一套。

作用范围就是 ContextVar 的作用范围。本包**只保证一件事**：同一个执行上下文里往下调用看得到。
有用例验证过的也只有一条（CPython 3.12.2 / Windows 11，本仓库的测试环境，见 ``tests/test_web_lease_commit_fence.py``）：
裸 ``threading.Thread`` 里的写入**不带**外面装上的围栏。
线程池、``asyncio`` 任务、``run_in_executor`` 这些入口带不带，取决于那个入口怎么传上下文；本包没有逐一验证，
**不要从上面那一条推广过去**。后台线要围住自己的写，就在那个线程／任务里自己装一次（``ticker.tick`` 就是这么做的）。
HTTP 请求线程本来就没有装，照常写（命令由请求自己的幂等与领域键保证）。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

Fence = Callable[[sqlite3.Connection], None]
# 当前执行上下文里已经装上的那一套检查（可能是好几道叠起来的）
_FENCE: ContextVar[Fence | None] = ContextVar("web_uow_fence", default=None)


def _both(outer: Fence, inner: Fence) -> Fence:
    """外层先过，再过内层。前一道抛异常就不再往下查——调用方看到的是最先不成立的那条原因。"""
    def check(conn: sqlite3.Connection) -> None:
        outer(conn)
        inner(conn)

    return check


@contextmanager
def lane_fence(check: Fence | None) -> Iterator[None]:
    """把 check **叠加**到当前上下文已有的围栏上（通常最外层是 assert_lease_held）。

    这一轮里所有 unit_of_work 写事务都要把叠起来的每一道都过一遍，任何一道抛异常 → 整个事务回滚。
    check 为 None：不追加检查，也不解除外面已经装上的。
    """
    outer = _FENCE.get()
    token = _FENCE.set(outer if check is None else (check if outer is None else _both(outer, check)))
    try:
        yield
    finally:
        _FENCE.reset(token)  # 恢复进入这个块之前的那一套（正常退出与抛异常都一样）


@contextmanager
def unit_of_work(storage) -> Iterator[sqlite3.Connection]:
    with storage.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        check = _FENCE.get()
        if check is not None:
            check(conn)  # 租约已经被接手或过期、或者内层那道不成立：这次提交作废，写锁随事务一起释放
        yield conn


def execute_in(storage, conn: sqlite3.Connection | None, sql: str, params: tuple = ()) -> sqlite3.Cursor:
    """给了连接（调用者的 UnitOfWork 或任务围栏）就在它的事务里执行、不提交；没给就开一个短连接执行并提交。"""
    if conn is not None:
        return conn.execute(sql, params)
    with storage.connect() as own:
        return own.execute(sql, params)
