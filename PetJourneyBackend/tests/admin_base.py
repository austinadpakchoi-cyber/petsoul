"""运营后台用例的共用基类（非测试模块，不以 test_ 开头）。

沿用 `web_base.WebPlatformTestBase` 的隔离环境：每个用例一个临时库、一份临时媒体目录、
供应商全 mock、调度器关闭。员工账号由领域服务直接创建（网页没有创建第一个员工的入口）。
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from web_base import WebPlatformTestBase

ADMIN_PREFIX = "/api/v1/admin"
STRONG_PASSWORD = "staff-password-0123"


class AdminStaff:
    """一个独立的员工浏览器会话（独立 cookie jar），写操作自动带 CSRF 与幂等键。"""

    def __init__(self, app, username: str, roles, password: str = STRONG_PASSWORD, display_name: str | None = None) -> None:
        self.app = app
        self.password = password
        self.client = TestClient(app)
        self.record = app.state.admin.identity.create_staff(username, password, display_name or username, roles)
        self.staff_id = self.record.staff_id
        self.username = self.record.username

    # ---- 会话 ----
    def login(self, mfa_code: str | None = None):
        body = {"username": self.username, "password": self.password}
        if mfa_code is not None:
            body["mfa_code"] = mfa_code
        return self.client.post(f"{ADMIN_PREFIX}/auth/login", json=body)

    def login_ok(self) -> dict:
        response = self.login()
        assert response.status_code == 200, response.text
        return response.json()

    @property
    def csrf(self) -> str:
        return self.client.cookies.get("petsoul_admin_csrf") or ""

    # ---- 请求 ----
    def get(self, path: str, **kwargs):
        return self.client.get(f"{ADMIN_PREFIX}{path}", **kwargs)

    def post(self, path: str, body=None, key: str | None = None, **kwargs):
        headers = {"X-Admin-CSRF-Token": self.csrf, "Idempotency-Key": key or f"adm-{uuid.uuid4().hex[:16]}",
                   **kwargs.pop("headers", {})}
        return self.client.post(f"{ADMIN_PREFIX}{path}", json=body, headers=headers, **kwargs)

    def upload(self, path: str, *, files, data=None, key: str | None = None, **kwargs):
        """多部分上传（素材库）。CSRF 与幂等键同普通写操作。"""
        headers = {"X-Admin-CSRF-Token": self.csrf, "Idempotency-Key": key or f"adm-{uuid.uuid4().hex[:16]}",
                   **kwargs.pop("headers", {})}
        return self.client.post(f"{ADMIN_PREFIX}{path}", files=files, data=data, headers=headers, **kwargs)

    def put(self, path: str, body=None, key: str | None = None, **kwargs):
        headers = {"X-Admin-CSRF-Token": self.csrf, "Idempotency-Key": key or f"adm-{uuid.uuid4().hex[:16]}",
                   **kwargs.pop("headers", {})}
        return self.client.put(f"{ADMIN_PREFIX}{path}", json=body, headers=headers, **kwargs)


class AdminTestBase(WebPlatformTestBase):
    def tearDown(self) -> None:
        # 界面不晦涩的一道兜底：这个用例里**真实产生过**的每一个审计动作，都要在 labels.AUDIT_ACTION 里有一句人话。
        # 全部后台用例跑一遍，就等于把所有会写审计的路径都核了一遍；新加动作忘了写说法，这里就红。
        actions: set[str] = set()
        try:
            with self.app.state.storage.connect() as conn:
                actions = {row[0] for row in conn.execute("SELECT DISTINCT action FROM admin_audit")}
        except Exception:
            actions = set()  # 这个用例没有后台的表（比如故意不迁移的环境）：没有东西要核
        super().tearDown()
        from app.web_admin.labels import audit_action_label
        missing = sorted(action for action in actions if audit_action_label(action) is None)
        self.assertEqual(missing, [], "这些审计动作在操作记录页上没有说法，请在 app/web_admin/labels.py 的 AUDIT_ACTION 里补上")

    def staff(self, username: str, roles) -> AdminStaff:
        return AdminStaff(self.app, username, roles)

    def owner(self) -> AdminStaff:
        member = self.staff(f"owner-{uuid.uuid4().hex[:6]}", ["platform_owner"])
        member.login_ok()
        return member

    def assert_admin_error(self, response, status: int, code: str) -> dict:
        self.assertEqual(response.status_code, status, response.text)
        body = response.json()
        self.assertIn("error", body, response.text)
        self.assertEqual(body["error"]["code"], code, response.text)
        self.assertTrue(body["error"]["request_id"])
        return body["error"]

    def table_counts(self, tables) -> dict:
        """业务表行数快照：用来证明"后台的读不写业务表"。"""
        counts = {}
        with self.app.state.storage.connect() as conn:
            for table in tables:
                row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
                counts[table] = int(row["n"])
        return counts
