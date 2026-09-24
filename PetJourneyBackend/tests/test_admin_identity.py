"""员工身份与权限的拒绝路径：谁进不来、谁进来了也做不了什么。

覆盖点按**位置**排（不是按原因码）：未登录、玩家 cookie、家庭管理员、错误角色、被撤权、
被停用、CSRF 缺失、来源不符、MFA 未入册。每一条都走真实 HTTP。
"""

from __future__ import annotations

import unittest

from admin_base import ADMIN_PREFIX, AdminTestBase
from web_base import PREFIX


class AdminIdentityTests(AdminTestBase):
    def test_meta_is_public_but_carries_no_business_data(self):
        response = self.client.get(f"{ADMIN_PREFIX}/meta")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertFalse(body["initialized"])  # 还没有任何员工
        self.assertTrue(body["tables_ready"])
        self.assertIn("roles", body)
        self.assertNotIn("users", body)

    def test_anonymous_cannot_reach_any_protected_endpoint(self):
        for method, path in (("GET", "/overview"), ("GET", "/search?q=a"), ("GET", "/audit"),
                             ("GET", "/reports"), ("GET", "/content"), ("GET", "/providers/usage")):
            with self.subTest(path=path):
                response = self.client.request(method, f"{ADMIN_PREFIX}{path}")
                self.assert_admin_error(response, 401, "AUTH_REQUIRED")

    def test_player_session_cookie_is_not_a_staff_session(self):
        """普通玩家登录后拿到的 cookie 对管理端完全无效——两套 cookie、两张表、两条解析路径。"""
        player = self.user("player-a")
        self.assertTrue(player.client.cookies.get("petsoul_session"))
        response = player.client.get(f"{ADMIN_PREFIX}/overview")
        self.assert_admin_error(response, 401, "AUTH_REQUIRED")
        # 把玩家的会话值硬塞进管理端 cookie 名下，也进不去（签名对不上 + 不在 admin_sessions 里）
        player.client.cookies.set("petsoul_admin_session", player.client.cookies.get("petsoul_session"))
        self.assert_admin_error(player.client.get(f"{ADMIN_PREFIX}/overview"), 401, "SESSION_EXPIRED")

    def test_household_admin_has_no_platform_permission(self):
        """家庭管理员是家庭里的角色，和平台权限没有任何映射。"""
        owner = self.user("household-admin")
        owner.adopt_and_move_in("adopt-lan")
        household = owner.get("/households")
        self.assertEqual(household.status_code, 200, household.text)
        payload = household.json()
        rows = payload if isinstance(payload, list) else [payload]
        self.assertTrue(any(row.get("role") == "admin" for row in rows), household.text)  # 他确实是家庭管理员
        self.assert_admin_error(owner.client.get(f"{ADMIN_PREFIX}/overview"), 401, "AUTH_REQUIRED")
        self.assert_admin_error(owner.client.get(f"{ADMIN_PREFIX}/users/{owner.user_id}"), 401, "AUTH_REQUIRED")

    def test_login_logout_and_session(self):
        staff = self.staff("ops-owner", ["platform_owner"])
        body = staff.login_ok()
        self.assertEqual(body["staff"]["username"], "ops-owner")
        self.assertIn("ops.read", body["staff"]["permissions"])
        self.assertNotIn("private.read", body["staff"]["permissions"])  # 私密正文不给任何默认角色
        self.assertEqual(staff.get("/auth/session").status_code, 200)
        cookie = staff.client.cookies.get("petsoul_admin_session")
        self.assertEqual(staff.post("/auth/logout").status_code, 200)
        self.assert_admin_error(staff.get("/auth/session"), 401, "AUTH_REQUIRED")  # cookie 已清
        # 把退出前的 cookie 原样塞回去：服务端那条会话已经吊销，照样进不来（不是只清了浏览器）
        staff.client.cookies.set("petsoul_admin_session", cookie)
        self.assert_admin_error(staff.get("/auth/session"), 401, "SESSION_EXPIRED")

    def test_wrong_password_and_unknown_user_look_the_same(self):
        staff = self.staff("ops-a", ["support"])
        wrong = self.client.post(f"{ADMIN_PREFIX}/auth/login", json={"username": "ops-a", "password": "not-the-password"})
        self.assert_admin_error(wrong, 401, "INVALID_CREDENTIALS")
        missing = self.client.post(f"{ADMIN_PREFIX}/auth/login", json={"username": "nobody-here", "password": "whatever-long"})
        self.assert_admin_error(missing, 401, "INVALID_CREDENTIALS")
        self.assertEqual(wrong.json()["error"]["message"], missing.json()["error"]["message"])
        self.assertIsNotNone(staff.staff_id)

    def test_validation_error_never_echoes_the_password(self):
        response = self.client.post(f"{ADMIN_PREFIX}/auth/login", json={"username": "x", "password": 12345})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertNotIn("12345", response.text)
        self.assertNotIn("input", response.text)

    def test_role_without_permission_is_denied_and_audited(self):
        editor = self.staff("content-only", ["content_editor"])
        editor.login_ok()
        self.assertEqual(editor.get("/content").status_code, 200)
        denied = editor.get("/search?q=anything")
        error = self.assert_admin_error(denied, 403, "FORBIDDEN")
        self.assertEqual(error["details"]["required_permission"], "user.read")
        # 被拒绝这件事本身要留痕
        owner = self.owner()
        entries = owner.get("/audit?status=denied").json()["entries"]
        self.assertTrue(any(e["actor_username"] == "content-only" and e["permission"] == "user.read" for e in entries))

    def test_revoking_roles_kills_the_existing_session(self):
        support = self.staff("support-1", ["support"])
        support.login_ok()
        self.assertEqual(support.get("/search?q=zzz").status_code, 200)
        owner = self.owner()
        response = owner.put(f"/staff/{support.staff_id}/roles", {"roles": ["auditor"], "expected_version": support.record.version})
        self.assertEqual(response.status_code, 200, response.text)
        self.assert_admin_error(support.get("/search?q=zzz"), 401, "SESSION_EXPIRED")
        support.login_ok()  # 重新登录后是新角色
        self.assertEqual(support.get("/search?q=zzz").status_code, 200)
        self.assert_admin_error(support.post("/users/PU-NOPE/revoke-sessions", {"reason": "测试越权"}), 403, "FORBIDDEN")

    def test_disabling_staff_kills_session_and_login(self):
        support = self.staff("support-2", ["support"])
        support.login_ok()
        owner = self.owner()
        response = owner.put(f"/staff/{support.staff_id}/status",
                             {"status": "disabled", "expected_version": support.record.version, "reason": "离职交接"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assert_admin_error(support.get("/auth/session"), 401, "SESSION_EXPIRED")
        self.assert_admin_error(support.login(), 403, "FORBIDDEN")

    def test_write_requires_csrf_and_known_origin(self):
        owner = self.owner()
        player = self.user("victim-1")
        no_csrf = owner.client.post(f"{ADMIN_PREFIX}/users/{player.user_id}/revoke-sessions",
                                    json={"reason": "缺少 CSRF 头"}, headers={"Idempotency-Key": "k-no-csrf-0001"})
        self.assert_admin_error(no_csrf, 403, "CSRF_FAILED")
        bad_origin = owner.post(f"/users/{player.user_id}/revoke-sessions", {"reason": "来源不对"},
                                headers={"Origin": "https://evil.example"})
        self.assert_admin_error(bad_origin, 403, "CSRF_FAILED")
        ok = owner.post(f"/users/{player.user_id}/revoke-sessions", {"reason": "正常路径对照"},
                        headers={"Origin": "http://127.0.0.1:5299"})
        self.assertEqual(ok.status_code, 200, ok.text)

    def test_write_requires_idempotency_key(self):
        owner = self.owner()
        player = self.user("victim-2")
        response = owner.client.post(f"{ADMIN_PREFIX}/users/{player.user_id}/revoke-sessions",
                                     json={"reason": "缺少幂等键"}, headers={"X-Admin-CSRF-Token": owner.csrf})
        self.assert_admin_error(response, 400, "IDEMPOTENCY_KEY_REQUIRED")

    def test_version_conflict_on_role_change(self):
        support = self.staff("support-3", ["support"])
        owner = self.owner()
        stale = owner.put(f"/staff/{support.staff_id}/roles", {"roles": ["auditor"], "expected_version": 99})
        self.assert_admin_error(stale, 409, "VERSION_CONFLICT")

    def test_owner_cannot_disable_self(self):
        owner = self.owner()
        response = owner.put(f"/staff/{owner.staff_id}/status",
                             {"status": "disabled", "expected_version": owner.record.version, "reason": "自锁测试"})
        self.assert_admin_error(response, 409, "CONFLICT")


class AdminLegacyPolicyTests(AdminTestBase):
    """policy=closed 是推荐给纯网页部署的旧接口策略；它不能把新的员工后台一起 404 掉。"""

    policy = "closed"

    def test_admin_api_is_not_treated_as_a_legacy_endpoint(self):
        legacy = self.client.get("/api/v1/pets/PJ-NOPE/traces")
        self.assertEqual(legacy.status_code, 404, "旧接口在 closed 策略下照常 404")
        self.assertEqual(self.client.get(f"{ADMIN_PREFIX}/meta").status_code, 200, "后台元信息不该被旧守卫拦掉")
        self.assert_admin_error(self.client.get(f"{ADMIN_PREFIX}/overview"), 401, "AUTH_REQUIRED")
        staff = self.staff("closed-policy-owner", ["platform_owner"])
        staff.login_ok()
        self.assertEqual(staff.get("/overview").status_code, 200)


class AdminMfaTests(AdminTestBase):
    """MFA 入册与强制：要求 MFA 的环境里，没入册的员工会话是受限的，没有绕过参数。"""

    def setUp(self) -> None:
        super().setUp()
        import dataclasses

        self.app.state.admin.settings = dataclasses.replace(self.app.state.admin.settings, require_mfa=True)
        self.app.state.admin.identity.settings = self.app.state.admin.settings

    def test_unenrolled_staff_is_restricted_until_enrolled(self):
        from app.web_admin import totp

        staff = self.staff("mfa-owner", ["platform_owner"])
        body = staff.login_ok()
        self.assertTrue(body["mfa_enrollment_required"])
        self.assert_admin_error(staff.get("/overview"), 403, "MFA_ENROLLMENT_REQUIRED")

        enroll = staff.post("/auth/mfa/enroll")
        self.assertEqual(enroll.status_code, 200, enroll.text)
        secret = enroll.json()["secret"]
        self.assertNotIn(secret, staff.get("/auth/session").text)

        bad = staff.post("/auth/mfa/activate", {"code": "000000"})
        self.assertIn(bad.status_code, (401, 422))
        activate = staff.post("/auth/mfa/activate", {"code": totp.code_now(secret)})
        self.assertEqual(activate.status_code, 200, activate.text)
        self.assertEqual(staff.get("/overview").status_code, 200)

        # 启用之后登录必须带验证码
        staff.post("/auth/logout")
        self.assert_admin_error(staff.login(), 401, "MFA_REQUIRED")
        self.assert_admin_error(staff.login(mfa_code="000000"), 401, "MFA_REQUIRED")
        self.assertEqual(staff.login(mfa_code=totp.code_now(secret)).status_code, 200)

    def test_audit_never_stores_the_mfa_secret(self):
        from app.web_admin import totp

        staff = self.staff("mfa-audit", ["platform_owner"])
        staff.login_ok()
        secret = staff.post("/auth/mfa/enroll").json()["secret"]
        staff.post("/auth/mfa/activate", {"code": totp.code_now(secret)})
        with self.app.state.storage.connect() as conn:
            blob = " ".join(str(tuple(row)) for row in conn.execute("SELECT * FROM admin_audit"))
        self.assertNotIn(secret, blob)


if __name__ == "__main__":
    unittest.main()
