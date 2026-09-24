"""网页账号与会话服务：注册、登录、会话吊销、登录限流。

账号：复用 users 表（apple_sub 为空）作为 user_id 主键；web_accounts 保存用户名与口令哈希。
会话：cookie JWT 只携带 sid；web_sessions 行决定会话是否仍有效（退出/过期即失效）。
"""

from __future__ import annotations

import sqlite3
import threading
import time
import unicodedata
import uuid
from collections import deque
from datetime import datetime, timedelta

from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from ..web_platform.runtime_epochs import bump_many_in, household_pets_in
from .passwords import DUMMY_HASH, hash_password, verify_password

DEFAULT_TIMEZONE = "Asia/Hong_Kong"
# 这几项是"用途授权"：改了就要让在途的结论重新复核。时区只是显示口径，不在其列
PURPOSE_PREFS = ("model_replies", "generated_photos", "pet_messages")
# 模型回信「从没选过」时的取值（2026-09-24 起开启）。读（没有行时）与 touch_active 建行时共用这一个值：
# 表的列默认值还是 0150 定的 0，建行时不显式写就会把"没选过"存成"关"（见迁移 0190）
MODEL_REPLIES_DEFAULT = True


def _households_of(conn: sqlite3.Connection, user_id: str) -> list[str]:
    """这位家人参与照顾的家。撤权只影响这些家的宠物，不波及别人家（保持成员与家庭的授权范围）。"""
    return [row["household_id"] for row in conn.execute("SELECT household_id FROM web_household_members WHERE user_id = ?", (user_id,))]


class UsernameTaken(Exception):
    pass


class InvalidCredentials(Exception):
    pass


class RateLimited(Exception):
    pass


def username_key(username: str) -> str:
    return unicodedata.normalize("NFKC", username).strip().lower()


class LoginRateLimiter:
    """单实例内存限流：同一用户名或同一来源在窗口内失败过多则暂时拒绝。"""

    def __init__(self, max_failures: int = 8, window_seconds: int = 300) -> None:
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            for key in keys:
                bucket = self._failures.get(key)
                if not bucket:
                    continue
                while bucket and now - bucket[0] > self.window:
                    bucket.popleft()
                if len(bucket) >= self.max_failures:
                    raise RateLimited()

    def record_failure(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            for key in keys:
                self._failures.setdefault(key, deque()).append(now)

    def reset(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._failures.pop(key, None)


class WebIdentityService:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage
        self.limiter = LoginRateLimiter()

    def register(self, username: str, password: str, display_name: str | None) -> str:
        key = username_key(username)
        user_id = f"PU-{uuid.uuid4().hex[:8].upper()}"
        now = iso(utcnow())
        password_hash = hash_password(password)
        try:
            with self.storage.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT INTO users (user_id, apple_sub, email, display_name, created_at) VALUES (?, NULL, NULL, ?, ?)",
                    (user_id, (display_name or username).strip()[:40], now),
                )
                conn.execute(
                    "INSERT INTO web_accounts (user_id, username, username_key, password_hash, created_at, password_updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, username.strip(), key, password_hash, now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise UsernameTaken() from exc
        return user_id

    def authenticate(self, username: str, password: str, client_key: str) -> str:
        key = username_key(username)
        self.limiter.check(f"user:{key}", f"client:{client_key}")
        with self.storage.connect() as conn:
            row = conn.execute("SELECT user_id, password_hash FROM web_accounts WHERE username_key = ?", (key,)).fetchone()
        if row is None:
            verify_password(password, DUMMY_HASH)
            self.limiter.record_failure(f"user:{key}", f"client:{client_key}")
            raise InvalidCredentials()
        if not verify_password(password, row["password_hash"]):
            self.limiter.record_failure(f"user:{key}", f"client:{client_key}")
            raise InvalidCredentials()
        self.limiter.reset(f"user:{key}")
        return row["user_id"]

    def username_of(self, user_id: str) -> str | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT username FROM web_accounts WHERE user_id = ?", (user_id,)).fetchone()
        return None if row is None else row["username"]

    def record_session(self, session_id: str, user_id: str, expires_at: datetime) -> None:
        with self.storage.connect() as conn:
            conn.execute(
                "INSERT INTO web_sessions (session_id, user_id, created_at, expires_at, revoked_at) VALUES (?, ?, ?, ?, NULL)",
                (session_id, user_id, iso(utcnow()), iso(expires_at)),
            )

    def revoke_session(self, session_id: str) -> None:
        with self.storage.connect() as conn:
            conn.execute(
                "UPDATE web_sessions SET revoked_at = ? WHERE session_id = ? AND revoked_at IS NULL",
                (iso(utcnow()), session_id),
            )

    def session_active(self, user_id: str, session_id: str) -> bool:
        with self.storage.connect() as conn:
            row = conn.execute(
                "SELECT expires_at, revoked_at FROM web_sessions WHERE session_id = ? AND user_id = ?",
                (session_id, user_id),
            ).fetchone()
        if row is None or row["revoked_at"] is not None:
            return False
        return parse_dt(row["expires_at"]) > utcnow() - timedelta(seconds=0)

    # ---- 账号偏好 ----
    def prefs(self, user_id: str) -> dict:
        """model_replies、pet_messages 默认开启；generated_photos 默认关闭（需主人明确开启）；timezone 默认香港。

        **model_replies 2026-09-24 改为默认开启**（用户：「跟宠物的聊天都是固定的，ds 没有参与，请修复」）。
        原先默认关闭、需要主人去设置页手动打开，于是配好了 DeepSeek 的环境里聊天照样是模板。
        它同时是「这只宠物能不能用模型」的授权（家庭频道主动消息的措辞、大脑是否可用模型都读它），
        所以**只改「从没选过」时的默认**：主人明确关掉的（库里存了 0）照旧尊重，撤权接口语义不变；
        大脑另受运营总闸 `web_brain_mode`（默认 off）与每宠每日上限约束，这里不绕过。
        """
        with self.storage.connect() as conn:
            return self._prefs_in(conn, user_id)

    def prefs_in(self, conn: sqlite3.Connection, user_id: str) -> dict:
        """公开入口：在**调用方已有的连接**上读同一份设置。

        给别的模块在自己的写事务里复核授权用（例如家庭那边判"这只宠物现在还能不能生成照片"）。
        它与 `prefs()` 读的是同一份数据、同一套默认值，只是不另开连接 —— 所以不会读到事务外的旧值，也不会自锁。
        """
        return self._prefs_in(conn, user_id)

    def _prefs_in(self, conn: sqlite3.Connection, user_id: str) -> dict:
        """在调用方的连接上读（写事务里的"读改写"要用这个，不能另开连接）。"""
        row = conn.execute("SELECT model_replies, generated_photos, pet_messages, timezone, last_active_at FROM web_user_prefs WHERE user_id = ?",
                           (user_id,)).fetchone()
        return {"model_replies": MODEL_REPLIES_DEFAULT if row is None else bool(row["model_replies"]), "generated_photos": bool(row and row["generated_photos"]),
                "pet_messages": True if row is None else bool(row["pet_messages"]), "timezone": (row["timezone"] if row else None) or DEFAULT_TIMEZONE,
                "last_active_at": parse_dt(row["last_active_at"]) if row and row["last_active_at"] else None}

    def set_prefs(self, user_id: str, *, model_replies: bool | None = None, generated_photos: bool | None = None,
                  pet_messages: bool | None = None, timezone: str | None = None) -> dict:
        """改设置：**读旧值、合并、判断授权是否变化、写回、递增授权代数，全部在同一个写事务、同一个连接里完成。**

        为什么不能先读后写：这个接口是"部分更新"——没给的字段要用旧值补齐。如果在事务外先读一遍，
        两个请求交错时后写的那个会把旧值整份盖回去：A 只想改时区，读到 model_replies=True；
        B 完成撤权写成 False；A 接着提交自己那份合并结果，又把 True 写了回去——**一个无关的请求撤销了别人的撤权**。
        放进 BEGIN IMMEDIATE 之后读，SQLite 的写锁就把两个请求排成先后，谁后写谁看到的就是最新值。
        """
        now = utcnow()
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = self._prefs_in(conn, user_id)  # 拿到写锁之后再读：读到的一定是此刻最新的
            merged = {"model_replies": current["model_replies"] if model_replies is None else model_replies,
                      "generated_photos": current["generated_photos"] if generated_photos is None else generated_photos,
                      "pet_messages": current["pet_messages"] if pet_messages is None else pet_messages,
                      "timezone": current["timezone"] if timezone is None else timezone}
            # 用途授权变了（能不能把共用资料交给模型、能不能生成照片、TA 能不能主动来信）要让在途的结论作废。
            # 只改时区不算授权变化；写同样的值也不算（验收 CR-Q13）。
            changed = [key for key in PURPOSE_PREFS if merged[key] != current[key]]
            conn.execute(
                "INSERT INTO web_user_prefs (user_id, model_replies, generated_photos, pet_messages, timezone, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET model_replies = excluded.model_replies, generated_photos = excluded.generated_photos, "
                "pet_messages = excluded.pet_messages, timezone = excluded.timezone, updated_at = excluded.updated_at",
                (user_id, int(merged["model_replies"]), int(merged["generated_photos"]), int(merged["pet_messages"]), merged["timezone"], iso(now)),
            )
            if changed:
                for household_id in _households_of(conn, user_id):  # 只影响这位家人真正参与照顾的那些家
                    bump_many_in(conn, household_pets_in(conn, household_id), "privacy_epoch", now)
        return {**merged, "last_active_at": current["last_active_at"]}

    def touch_active(self, user_id: str, now: datetime) -> None:
        """记录主人最近来过（每 10 分钟最多写一次）；主动消息据此判断要不要发。

        这里会替从没改过设置的人**建出偏好行**，所以建行时要显式写模型回信的默认值——不写就落到列默认值 0，
        读取端从此把"没选过"当成"关"（打开页面、发第一条私信都会走到这里，发生在回信之前）。
        已有的行只改 last_active_at，不碰任何授权值。
        """
        with self.storage.connect() as conn:
            conn.execute(
                "INSERT INTO web_user_prefs (user_id, model_replies, updated_at, last_active_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET last_active_at = excluded.last_active_at "
                "WHERE web_user_prefs.last_active_at IS NULL OR web_user_prefs.last_active_at < ?",
                (user_id, int(MODEL_REPLIES_DEFAULT), iso(now), iso(now), iso(now - timedelta(minutes=10))),
            )

