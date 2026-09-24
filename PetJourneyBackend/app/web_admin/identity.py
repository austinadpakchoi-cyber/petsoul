"""员工身份与会话：与玩家身份完全分开的一套。

- 员工账号在 `admin_staff`，口令走玩家端同一套 scrypt（`web_identity.passwords`，只复用算法，不共用表）；
- 会话是**不透明**的：cookie 值 `<session_id>.<hmac>`，session_id 是 32 字节随机数，hmac 用服务端 auth_secret 签。
  只拿到数据库也签不出可用 cookie；撤权就是把 `admin_sessions.revoked_at` 写上，**下一次请求立刻失效**；
- 停用员工 = `status='disabled'` + 撤销它名下所有会话，两件事在同一个写事务里；
- 二次验证见 `totp.py`。要求 MFA 但本人还没入册时，会话是**受限**的：除 `auth.*` 与入册接口外，
  任何权限检查都拒绝（MFA_ENROLLMENT_REQUIRED）。没有"跳过 MFA"的后门参数。
"""

from __future__ import annotations

import hmac
import secrets
import sqlite3
import threading
import time
import unicodedata
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from ..web_identity.passwords import DUMMY_HASH, hash_password, verify_password
from .errors import AdminAPIError, AdminErrorCode
from .permissions import Permission, Role, permissions_for
from . import totp

MIN_PASSWORD_LENGTH = 12


class StaffExists(Exception):
    pass


@dataclass(frozen=True, slots=True)
class StaffRecord:
    staff_id: str
    username: str
    display_name: str
    status: str
    mfa_enabled: bool
    roles: tuple[str, ...]
    version: int
    created_at: datetime
    last_login_at: datetime | None

    @property
    def permissions(self) -> frozenset[Permission]:
        return permissions_for(self.roles)


@dataclass(frozen=True, slots=True)
class AdminPrincipal:
    staff: StaffRecord
    session_id: str
    expires_at: datetime
    mfa_satisfied: bool  # 本次会话是否已满足 MFA 策略（不满足时只能访问 auth.* 与入册）

    def has(self, permission: Permission) -> bool:
        return self.mfa_satisfied and permission in self.staff.permissions


@dataclass(frozen=True, slots=True)
class IssuedAdminSession:
    cookie_value: str
    session_id: str
    csrf_token: str
    expires_at: datetime


def username_key(username: str) -> str:
    return unicodedata.normalize("NFKC", username).strip().lower()


class _Limiter:
    def __init__(self, max_failures: int, window_seconds: int) -> None:
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
                    raise AdminAPIError(AdminErrorCode.rate_limited, "尝试次数过多，请稍后再试。", 429, retryable=True)

    def fail(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            for key in keys:
                self._failures.setdefault(key, deque()).append(now)

    def reset(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._failures.pop(key, None)


def _sign(secret: str, session_id: str) -> str:
    return hmac.new(secret.encode("utf-8"), session_id.encode("ascii"), "sha256").hexdigest()[:32]


class AdminIdentityService:
    def __init__(self, storage: JourneyStorage, *, auth_secret: str, settings) -> None:
        self.storage = storage
        self.secret = auth_secret
        self.settings = settings
        self.limiter = _Limiter(settings.login_max_failures, settings.login_window_seconds)

    # ---- 员工账号 ----
    def create_staff(self, username: str, password: str, display_name: str, roles, *, created_by: str | None = None) -> StaffRecord:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise AdminAPIError.validation(f"员工口令至少 {MIN_PASSWORD_LENGTH} 位。", field="password")
        wanted = self._valid_roles(roles)
        staff_id = f"ST-{uuid.uuid4().hex[:8].upper()}"
        now = iso(utcnow())
        try:
            with self.storage.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT INTO admin_staff (staff_id, username, username_key, display_name, password_hash, status, mfa_secret, mfa_enabled, "
                    "version, created_at, created_by, password_updated_at) VALUES (?, ?, ?, ?, ?, 'active', NULL, 0, 1, ?, ?, ?)",
                    (staff_id, username.strip(), username_key(username), display_name.strip()[:40] or username.strip(),
                     hash_password(password), now, created_by, now),
                )
                for role in wanted:
                    conn.execute("INSERT INTO admin_staff_roles (staff_id, role, granted_at, granted_by) VALUES (?, ?, ?, ?)",
                                 (staff_id, role, now, created_by))
        except sqlite3.IntegrityError as exc:
            raise StaffExists() from exc
        record = self.staff(staff_id)
        assert record is not None
        return record

    def _valid_roles(self, roles) -> list[str]:
        wanted = []
        for name in roles:
            try:
                wanted.append(Role(name).value)
            except ValueError as exc:
                raise AdminAPIError.validation(f"没有这个角色：{name}", field="roles") from exc
        if not wanted:
            raise AdminAPIError.validation("至少要给一个角色。", field="roles")
        return sorted(set(wanted))

    def staff(self, staff_id: str) -> StaffRecord | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM admin_staff WHERE staff_id = ?", (staff_id,)).fetchone()
            if row is None:
                return None
            return self._record(conn, row)

    def list_staff(self) -> list[StaffRecord]:
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT * FROM admin_staff ORDER BY created_at").fetchall()
            return [self._record(conn, row) for row in rows]

    def any_staff_exists(self) -> bool:
        with self.storage.connect() as conn:
            return conn.execute("SELECT 1 FROM admin_staff LIMIT 1").fetchone() is not None

    def _record(self, conn: sqlite3.Connection, row) -> StaffRecord:
        roles = tuple(r["role"] for r in conn.execute("SELECT role FROM admin_staff_roles WHERE staff_id = ? ORDER BY role", (row["staff_id"],)))
        return StaffRecord(
            staff_id=row["staff_id"], username=row["username"], display_name=row["display_name"], status=row["status"],
            mfa_enabled=bool(row["mfa_enabled"]), roles=roles, version=int(row["version"]),
            created_at=parse_dt(row["created_at"]), last_login_at=parse_dt(row["last_login_at"]) if row["last_login_at"] else None,
        )

    def set_roles(self, staff_id: str, roles, *, expected_version: int, actor: str) -> StaffRecord:
        wanted = self._valid_roles(roles)
        now = iso(utcnow())
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT version FROM admin_staff WHERE staff_id = ?", (staff_id,)).fetchone()
            if row is None:
                raise AdminAPIError.not_found("这位员工")
            if int(row["version"]) != expected_version:
                raise AdminAPIError.version_conflict(expected_version, int(row["version"]))
            conn.execute("DELETE FROM admin_staff_roles WHERE staff_id = ?", (staff_id,))
            for role in wanted:
                conn.execute("INSERT INTO admin_staff_roles (staff_id, role, granted_at, granted_by) VALUES (?, ?, ?, ?)", (staff_id, role, now, actor))
            conn.execute("UPDATE admin_staff SET version = version + 1 WHERE staff_id = ?", (staff_id,))
            # 撤权立即生效：改角色即断开该员工所有在用会话，不让旧会话继续按旧权限写。
            conn.execute("UPDATE admin_sessions SET revoked_at = ?, revoked_reason = 'roles_changed' WHERE staff_id = ? AND revoked_at IS NULL",
                         (now, staff_id))
        record = self.staff(staff_id)
        assert record is not None
        return record

    def set_status(self, staff_id: str, status: str, *, expected_version: int, actor: str) -> StaffRecord:
        if status not in ("active", "disabled"):
            raise AdminAPIError.validation("员工状态只能是 active 或 disabled。", field="status")
        now = iso(utcnow())
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT version FROM admin_staff WHERE staff_id = ?", (staff_id,)).fetchone()
            if row is None:
                raise AdminAPIError.not_found("这位员工")
            if int(row["version"]) != expected_version:
                raise AdminAPIError.version_conflict(expected_version, int(row["version"]))
            conn.execute("UPDATE admin_staff SET status = ?, version = version + 1, disabled_at = ?, disabled_by = ? WHERE staff_id = ?",
                         (status, now if status == "disabled" else None, actor if status == "disabled" else None, staff_id))
            if status == "disabled":
                conn.execute("UPDATE admin_sessions SET revoked_at = ?, revoked_reason = 'staff_disabled' WHERE staff_id = ? AND revoked_at IS NULL",
                             (now, staff_id))
        record = self.staff(staff_id)
        assert record is not None
        return record

    # ---- 登录 ----
    def authenticate(self, username: str, password: str, mfa_code: str | None, client_key: str) -> StaffRecord:
        key = username_key(username)
        self.limiter.check(f"staff:{key}", f"client:{client_key}")
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM admin_staff WHERE username_key = ?", (key,)).fetchone()
            record = self._record(conn, row) if row is not None else None
        if row is None:
            verify_password(password, DUMMY_HASH)  # 恒定时间：不让响应时间泄露员工名是否存在
            self.limiter.fail(f"staff:{key}", f"client:{client_key}")
            raise AdminAPIError(AdminErrorCode.invalid_credentials, "员工名或口令不正确。", 401)
        if not verify_password(password, row["password_hash"]):
            self.limiter.fail(f"staff:{key}", f"client:{client_key}")
            raise AdminAPIError(AdminErrorCode.invalid_credentials, "员工名或口令不正确。", 401)
        assert record is not None
        if record.status != "active":
            self.limiter.fail(f"staff:{key}", f"client:{client_key}")
            raise AdminAPIError(AdminErrorCode.forbidden, "这个员工账号已停用。", 403, details={"reason": "staff_disabled"})
        if record.mfa_enabled:
            if not mfa_code:
                raise AdminAPIError(AdminErrorCode.mfa_required, "请输入二次验证码。", 401, details={"reason": "mfa_required"})
            if not totp.verify(row["mfa_secret"] or "", mfa_code):
                self.limiter.fail(f"staff:{key}", f"client:{client_key}")
                raise AdminAPIError(AdminErrorCode.mfa_required, "二次验证码不正确。", 401, details={"reason": "mfa_invalid"})
        self.limiter.reset(f"staff:{key}")
        return record

    def issue_session(self, staff_id: str, *, client_hint: str | None = None) -> IssuedAdminSession:
        session_id = secrets.token_urlsafe(24)
        now = utcnow()
        expires_at = now + timedelta(seconds=self.settings.session_ttl_seconds)
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO admin_sessions (session_id, staff_id, created_at, expires_at, revoked_at, client_hint) "
                         "VALUES (?, ?, ?, ?, NULL, ?)", (session_id, staff_id, iso(now), iso(expires_at), (client_hint or "")[:80]))
            conn.execute("UPDATE admin_staff SET last_login_at = ? WHERE staff_id = ?", (iso(now), staff_id))
        return IssuedAdminSession(cookie_value=f"{session_id}.{_sign(self.secret, session_id)}", session_id=session_id,
                                  csrf_token=secrets.token_urlsafe(24), expires_at=expires_at)

    def resolve(self, cookie_value: str) -> AdminPrincipal:
        """解析 cookie；任何一步不成立都是 SESSION_EXPIRED，不区分原因（不给枚举线索）。"""
        session_id, _, signature = (cookie_value or "").partition(".")
        if not session_id or not signature or not hmac.compare_digest(signature, _sign(self.secret, session_id)):
            raise AdminAPIError.session_expired()
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM admin_sessions WHERE session_id = ?", (session_id,)).fetchone()
            if row is None or row["revoked_at"] is not None or parse_dt(row["expires_at"]) <= utcnow():
                raise AdminAPIError.session_expired()
            staff_row = conn.execute("SELECT * FROM admin_staff WHERE staff_id = ?", (row["staff_id"],)).fetchone()
            if staff_row is None or staff_row["status"] != "active":
                raise AdminAPIError.session_expired()
            record = self._record(conn, staff_row)
        satisfied = record.mfa_enabled or not self.settings.require_mfa
        return AdminPrincipal(staff=record, session_id=session_id, expires_at=parse_dt(row["expires_at"]), mfa_satisfied=satisfied)

    def revoke_session(self, session_id: str, reason: str = "logout") -> None:
        with self.storage.connect() as conn:
            conn.execute("UPDATE admin_sessions SET revoked_at = ?, revoked_reason = ? WHERE session_id = ? AND revoked_at IS NULL",
                         (iso(utcnow()), reason, session_id))

    # ---- 二次验证入册 ----
    def begin_mfa_enrollment(self, staff_id: str) -> tuple[str, str]:
        """生成并保存一个尚未启用的密钥；返回 (secret, otpauth URI)。启用前旧密钥可被新的覆盖。"""
        secret = totp.new_secret()
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT username, mfa_enabled FROM admin_staff WHERE staff_id = ?", (staff_id,)).fetchone()
            if row is None:
                raise AdminAPIError.not_found("这位员工")
            if row["mfa_enabled"]:
                raise AdminAPIError(AdminErrorCode.conflict, "二次验证已经启用；要更换请先由平台负责人重置。", 409)
            conn.execute("UPDATE admin_staff SET mfa_secret = ? WHERE staff_id = ?", (secret, staff_id))
            username = row["username"]
        return secret, totp.provisioning_uri(secret, username)

    def activate_mfa(self, staff_id: str, code: str) -> None:
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT mfa_secret, mfa_enabled FROM admin_staff WHERE staff_id = ?", (staff_id,)).fetchone()
            if row is None or not row["mfa_secret"]:
                raise AdminAPIError(AdminErrorCode.conflict, "还没有开始入册二次验证。", 409)
            if row["mfa_enabled"]:
                return
            if not totp.verify(row["mfa_secret"], code):
                raise AdminAPIError(AdminErrorCode.mfa_required, "验证码不正确，请用最新的一组再试。", 401, details={"reason": "mfa_invalid"})
            conn.execute("UPDATE admin_staff SET mfa_enabled = 1, version = version + 1 WHERE staff_id = ?", (staff_id,))
