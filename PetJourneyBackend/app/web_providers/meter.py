"""供应商调用计量：按天记次数/失败/最近错误摘要（已脱敏），到达每日上限即视为不可用（如实降级，不改用其他付费供应商）。

上限检查与计数是同一个原子操作：allow() 在一个写事务里“没到上限才 +1”，多个进程、多个线程同时检查也不会超额；
随后同一线程的 record() 只记成败，不再重复计数。allow() 放行后调用没发出去（例如构造请求时出错），这一次也保守地算作已用。
计费窗口是 UTC 日；次数存在数据库里，重启不清零。操作级额度（用途/宠物/家庭、并发、结果不明）见 web_platform/budget.py。
"""

from __future__ import annotations

import threading
import time
from datetime import datetime

from ..storage import JourneyStorage
from ..utils import iso, utcnow

# 进程内最近状态（供 /meta 能力说明使用；只含脱敏摘要）
_STATUS: dict[str, str | None] = {}
_STATUS_LOCK = threading.Lock()
_PENDING_MAX_AGE_SECONDS = 900.0  # allow() 之后这么久还没 record()，就不再把后来的 record 当作它的结算


def provider_status(provider: str) -> str | None:
    with _STATUS_LOCK:
        return _STATUS.get(provider)


def set_provider_status(provider: str, error: str | None) -> None:
    with _STATUS_LOCK:
        _STATUS[provider] = error


class ProviderMeter:
    def __init__(self, storage: JourneyStorage, caps: dict[str, int], secrets: list[str] | None = None) -> None:
        self.storage = storage
        self.caps = caps
        self._secrets = [s for s in (secrets or []) if s]
        self._lock = threading.Lock()
        self._pending = threading.local()  # 本线程 allow() 已预先计数、尚未 record() 的调用：provider → [(UTC 日, 单调时钟)]
        self._restore_status()

    def _restore_status(self) -> None:
        """重启后恢复最近一次调用状态（例如 Google 项目未开通计费），能力声明不因重启而“变好”。"""
        try:
            with self.storage.connect() as conn:
                rows = conn.execute("SELECT provider, last_error FROM web_provider_usage ORDER BY day").fetchall()
        except Exception:  # noqa: BLE001 - 迁移尚未应用时忽略
            return
        for row in rows:
            set_provider_status(row["provider"], row["last_error"])

    def redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "[REDACTED]")
        return text

    @staticmethod
    def _day(now: datetime | None = None) -> str:
        return (now or utcnow()).date().isoformat()

    def calls_today(self, provider: str) -> int:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT calls FROM web_provider_usage WHERE day = ? AND provider = ?", (self._day(), provider)).fetchone()
        return int(row["calls"]) if row else 0

    def allow(self, provider: str) -> bool:
        """原子地“检查上限并预先计数一次”。放行后请在同一线程里调用 record() 记录成败（不会再次计数）。"""
        cap = self.caps.get(provider)
        now = utcnow()
        day = self._day(now)
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO web_provider_usage (day, provider, calls, failures, last_error, updated_at) VALUES (?, ?, 0, 0, NULL, ?) "
                "ON CONFLICT(day, provider) DO NOTHING", (day, provider, iso(now)))
            cur = conn.execute(
                "UPDATE web_provider_usage SET calls = calls + 1, updated_at = ? WHERE day = ? AND provider = ? AND (? IS NULL OR calls < ?)",
                (iso(now), day, provider, cap, cap))
            allowed = cur.rowcount == 1
        if allowed:
            self._pending_calls(provider).append((day, time.monotonic()))
        return allowed

    def record(self, provider: str, ok: bool, error: str | None = None) -> None:
        summary = None if ok else self.redact(error or "error")[:200]
        now = utcnow()
        counted_day = self._take_pending(provider)
        with self._lock, self.storage.connect() as conn:
            if counted_day is not None:  # allow() 时已计数：只记失败与最近错误
                conn.execute(
                    "INSERT INTO web_provider_usage (day, provider, calls, failures, last_error, updated_at) VALUES (?, ?, 0, ?, ?, ?) "
                    "ON CONFLICT(day, provider) DO UPDATE SET failures = failures + excluded.failures, "
                    "last_error = CASE WHEN excluded.failures = 0 THEN NULL ELSE excluded.last_error END, updated_at = excluded.updated_at",
                    (counted_day, provider, 0 if ok else 1, summary, iso(now)),
                )
            else:  # 旧写法：没有先 allow() 的记录照旧计一次
                conn.execute(
                    "INSERT INTO web_provider_usage (day, provider, calls, failures, last_error, updated_at) VALUES (?, ?, 1, ?, ?, ?) "
                    "ON CONFLICT(day, provider) DO UPDATE SET calls = calls + 1, failures = failures + excluded.failures, "
                    "last_error = CASE WHEN excluded.failures = 0 THEN NULL ELSE excluded.last_error END, updated_at = excluded.updated_at",
                    (self._day(now), provider, 0 if ok else 1, summary, iso(now)),
                )
            try:  # “真的调通过”与“最近一次失败”分开记（运行状态接口据此区分“已配置”和“已验证”）
                conn.execute(
                    "INSERT INTO web_provider_health (provider, last_success_at, last_failure_at, last_error, updated_at) VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(provider) DO UPDATE SET last_success_at = COALESCE(excluded.last_success_at, last_success_at), "
                    "last_failure_at = COALESCE(excluded.last_failure_at, last_failure_at), "
                    "last_error = CASE WHEN excluded.last_success_at IS NOT NULL THEN last_error ELSE excluded.last_error END, updated_at = excluded.updated_at",
                    (provider, iso(now) if ok else None, None if ok else iso(now), summary, iso(now)),
                )
            except Exception:  # noqa: BLE001 - 迁移 0030 之前的库
                pass
        set_provider_status(provider, summary)

    def snapshot(self) -> dict[str, dict[str, object]]:
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT * FROM web_provider_usage WHERE day = ?", (self._day(),)).fetchall()
        return {r["provider"]: {"calls": r["calls"], "failures": r["failures"], "cap": self.caps.get(r["provider"])} for r in rows}

    # ---- 本线程已预计数的调用 ----
    def _pending_calls(self, provider: str) -> list[tuple[str, float]]:
        table = getattr(self._pending, "calls", None)
        if table is None:
            table = self._pending.calls = {}
        return table.setdefault(provider, [])

    def _take_pending(self, provider: str) -> str | None:
        """取出本线程最早一次尚未结算、且不太旧的 allow()；过旧的丢弃（它们已计数，保守算作已用）。"""
        calls = self._pending_calls(provider)
        horizon = time.monotonic() - _PENDING_MAX_AGE_SECONDS
        while calls:
            day, started = calls.pop(0)
            if started >= horizon:
                return day
        return None
