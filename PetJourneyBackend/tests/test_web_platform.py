"""网页平台：/api/v1/web 元信息、会话、错误信封、CSRF、幂等键与账号隔离。"""

from __future__ import annotations

import json
import unittest

from app.web_platform.session import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE, issue_web_session
from web_base import WebPlatformTestBase


class WebReadChainTests(WebPlatformTestBase):
    def test_meta_is_public_and_lists_capabilities(self) -> None:
        response = self.client.get("/api/v1/web/meta")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        # 契约版本故意写死：改了它就得有人来改这一行，顺带想一遍前端的生成产物是不是也重出了。
        # 0.4.1 → 0.4.4 是补上历史欠账：0.4.2（PhotoStatus 多一个 unknown）、0.4.3（多两条 retry-image 路由）、
        # 0.4.4（PetRuntimeStatus 多一个可选 next_review_at）**都改过契约**，但这个常量一直停在 0.4.1。
        # 0.4.5：主人主动拍照那三条路由（命令 / 结果列表 / 重画）＋ PhotoRequestView。
        self.assertEqual(body["contract_version"], "0.4.5")
        self.assertEqual(body["data_origin"], "live")
        for migration in ("0001_web_platform", "0100_identity", "0400_homes", "0600_journeys", "1200_collection"):
            self.assertIn(migration, body["applied_migrations"])
        caps = {item["key"]: item["status"] for item in body["capabilities"]}
        self.assertEqual(caps["home.snapshot"], "available")
        self.assertEqual(caps["identity.password_registration"], "available")
        self.assertEqual(caps["identity.email_recovery"], "not_implemented")
        self.assertEqual(caps["map.street_rank_list"], "disabled")
        self.assertEqual(caps["market.player_listing"], "disabled")
        self.assertEqual(caps["intent.layer"], "disabled", "意图层默认关闭")
        self.assertEqual(caps["transport.live_status"], "disabled")
        self.assertIn(caps["map.amap"], ("not_configured", "disabled"), "未配置 key 时不声称可用")
        self.assertIn("web_password", body["auth_methods_available"])
        self.assertTrue(response.headers["X-Request-ID"].startswith("req_"))

    def test_session_anonymous_then_bearer(self) -> None:
        self.assertEqual(self.client.get("/api/v1/web/session").json(), {
            "authenticated": False, "user": None, "csrf_required": False, "expires_at": None, "onboarding": None,
        })
        token, user_id = self.sign_in("reader")
        body = self.client.get("/api/v1/web/session", headers={"Authorization": f"Bearer {token}"}).json()
        self.assertTrue(body["authenticated"])
        self.assertEqual(body["user"]["user_id"], user_id)
        self.assertEqual(body["user"]["auth_method"], "apple_bearer")
        self.assertEqual(body["onboarding"]["step"], "needs_companion")

    def test_invalid_token_is_session_expired_not_anonymous(self) -> None:
        response = self.client.get("/api/v1/web/session", headers={"Authorization": "Bearer nope"})
        self.assert_envelope(response, 401, "SESSION_EXPIRED")

    def test_home_requires_auth_and_activation(self) -> None:
        self.assert_envelope(self.client.get("/api/v1/web/home"), 401, "AUTH_REQUIRED")
        token, _ = self.sign_in("home-owner")
        headers = {"Authorization": f"Bearer {token}"}
        body = self.assert_envelope(self.client.get("/api/v1/web/home", headers=headers), 409, "PET_NOT_ACTIVATED")
        self.assertEqual(body["error"]["details"]["onboarding_step"], "needs_companion")
        # iOS 旧宠物不会被静默当作网页之家：网页之家必须经过领养/创建 → 入住。
        self.create_owned_pet(token)
        self.assert_envelope(self.client.get("/api/v1/web/home", headers=headers), 409, "PET_NOT_ACTIVATED")

    def test_home_is_isolated_between_accounts(self) -> None:
        owner = self.user("owner-a")
        owner.adopt_and_move_in("adopt-lan")
        other = self.user("owner-b")
        self.assert_envelope(other.get("/home"), 409, "PET_NOT_ACTIVATED")
        # 0.4.0：指明了别人家的宠物时一律 404（不是这个家庭的成员；不暴露宠物是否存在）
        self.assert_envelope(other.get(f"/communicator/{owner.pet_id}/messages"), 404, "NOT_FOUND")
        self.assert_envelope(other.get(f"/home?pet_id={owner.pet_id}"), 404, "NOT_FOUND")


class WebErrorSemanticsTests(WebPlatformTestBase):
    def test_unknown_web_route_uses_envelope_but_legacy_keeps_detail(self) -> None:
        self.assert_envelope(self.client.get("/api/v1/web/nope"), 404, "NOT_FOUND")
        legacy = self.client.get("/api/v1/nope")
        self.assertEqual(legacy.status_code, 404)
        self.assertIn("detail", legacy.json())

    def test_validation_error_does_not_echo_input(self) -> None:
        response = self.client.post("/api/v1/web/auth/login", json={"username": "ab", "password": "secret-value"})
        body = self.assert_envelope(response, 422, "VALIDATION_FAILED")
        self.assertNotIn("secret-value", json.dumps(body))

    def test_reads_check_auth_first(self) -> None:
        for path in ("/circle/feed", "/home", "/journey/map", "/collection", "/farm/crops", "/neighbors"):
            self.assert_envelope(self.client.get(f"/api/v1/web{path}"), 401, "AUTH_REQUIRED")

    def test_disabled_capability_is_honest(self) -> None:
        user = self.user("cap-user")
        response = user.get("/map/street-rank")
        self.assertIn(response.status_code, (404, 501))
        self.assertNotEqual(response.status_code, 200)

    def test_write_requires_idempotency_key(self) -> None:
        user = self.user("idem-user")
        user.adopt_and_move_in("adopt-lan")
        body = {"home_id": user.home_id, "plot_id": "p-none", "action": "harvest"}
        headers = {CSRF_HEADER: user.csrf}
        response = user.client.post("/api/v1/web/farm/actions", json=body, headers=headers)
        self.assert_envelope(response, 400, "IDEMPOTENCY_KEY_REQUIRED")

    def test_cookie_session_write_requires_csrf(self) -> None:
        user = self.user("cookie-user")
        session = user.get("/session").json()
        self.assertEqual(session["user"]["auth_method"], "web_password")
        self.assertTrue(session["csrf_required"])
        self.assert_envelope(user.client.post("/api/v1/web/auth/logout"), 403, "CSRF_FAILED")
        ok = user.client.post("/api/v1/web/auth/logout", headers={CSRF_HEADER: user.csrf})
        self.assertEqual(ok.status_code, 204)
        self.assertIn(SESSION_COOKIE, ok.headers.get("set-cookie", ""))

    def test_forged_cookie_without_server_session_is_rejected(self) -> None:
        # 签名正确但服务端没有这条会话记录（或已撤销）→ 不当作已登录。
        _, user_id = self.sign_in("forged")
        issued = issue_web_session(self.settings.auth_secret, user_id, 3600)
        self.client.cookies.set(SESSION_COOKIE, issued.token)
        self.client.cookies.set(CSRF_COOKIE, issued.csrf_token)
        self.assert_envelope(self.client.get("/api/v1/web/session"), 401, "SESSION_EXPIRED")


if __name__ == "__main__":
    unittest.main()
