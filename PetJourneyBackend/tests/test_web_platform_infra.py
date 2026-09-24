"""网页 R0 平台设施：幂等、迁移、任务队列、旧 /api/v1 访问策略。"""

from __future__ import annotations

import unittest

from app.web_platform import WebAPIError
from app.web_platform.migrations import apply_web_migrations, discover_migrations
from app.web_platform.tasks import run_once
from web_base import WebPlatformTestBase


class WebIdempotencyAndTaskTests(WebPlatformTestBase):
    def test_idempotency_replays_and_rejects_reuse(self) -> None:
        store = self.app.state.web_idempotency
        calls: list[int] = []

        def handler() -> dict:
            calls.append(1)
            return {"result": len(calls)}

        first = store.run(user_id="u1", scope="farm", key="k-00000001", payload={"a": 1}, handler=handler)
        second = store.run(user_id="u1", scope="farm", key="k-00000001", payload={"a": 1}, handler=handler)
        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)
        self.assertEqual(second.response, {"result": 1})
        self.assertEqual(len(calls), 1)
        with self.assertRaises(WebAPIError) as ctx:
            store.run(user_id="u1", scope="farm", key="k-00000001", payload={"a": 2}, handler=handler)
        self.assertEqual(ctx.exception.code.value, "IDEMPOTENCY_KEY_REUSED")
        other_user = store.run(user_id="u2", scope="farm", key="k-00000001", payload={"a": 2}, handler=handler)
        self.assertFalse(other_user.replayed)

    def test_failed_handler_allows_retry(self) -> None:
        store = self.app.state.web_idempotency

        def boom() -> dict:
            raise RuntimeError("fail")

        with self.assertRaises(RuntimeError):
            store.run(user_id="u1", scope="s", key="retry-0001", payload={}, handler=boom)
        again = store.run(user_id="u1", scope="s", key="retry-0001", payload={}, handler=lambda: {"ok": True})
        self.assertEqual(again.response, {"ok": True})

    def test_migrations_are_discoverable_and_rerunnable(self) -> None:
        ids = [m.migration_id for m in discover_migrations()]
        self.assertEqual(ids[0], "0001_web_platform")
        again = apply_web_migrations(self.app.state.storage)
        self.assertEqual(again.count("0001_web_platform"), 1)

    def test_task_dedupe_supersede_and_precheck(self) -> None:
        queue = self.app.state.web_tasks
        task, created = queue.enqueue("demo", "reception:note:n1:photo", {"note": "n1"}, source_version="1")
        _, created_again = queue.enqueue("demo", "reception:note:n1:photo", {"note": "n1"}, source_version="1")
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(queue.supersede_pending("reception:note:n1:", "revoked"), [task.task_id])
        self.assertEqual(queue.get(task.task_id).status, "superseded")

        class Handler:
            kind = "demo"
            ran = False

            def precheck(self, t):
                return t.source_version == "2"

            def run(self, t):
                Handler.ran = True

        stale, _ = queue.enqueue("demo", "demo:stale", {}, source_version="1")
        result = run_once(queue, {"demo": Handler()}, "worker-1")
        self.assertEqual(result.task_id, stale.task_id)
        self.assertEqual(result.status, "superseded")
        self.assertFalse(Handler.ran)


class LegacyOwnerBearerPolicyTests(WebPlatformTestBase):
    policy = "owner_bearer"

    def test_pet_scoped_legacy_routes_require_owner(self) -> None:
        token_a, _ = self.sign_in("legacy-a")
        pet_id = self.create_owned_pet(token_a)
        token_b, _ = self.sign_in("legacy-b")
        self.assertEqual(self.client.get(f"/api/v1/pet_dna/{pet_id}").status_code, 401)
        self.assertEqual(
            self.client.get(f"/api/v1/pet_dna/{pet_id}", headers={"Authorization": f"Bearer {token_b}"}).status_code, 404
        )
        self.assertEqual(
            self.client.get(f"/api/v1/pets/{pet_id}/memories", headers={"Authorization": f"Bearer {token_b}"}).status_code,
            404,
        )
        ok = self.client.get(f"/api/v1/pet_dna/{pet_id}", headers={"Authorization": f"Bearer {token_a}"})
        self.assertEqual(ok.status_code, 200)

    def test_admin_routes_need_admin_token(self) -> None:
        token, _ = self.sign_in("legacy-admin")
        headers = {"Authorization": f"Bearer {token}"}
        self.assertEqual(self.client.post("/api/v1/scheduler/tick", headers=headers).status_code, 403)
        self.assertEqual(self.client.get("/api/v1/memory/config", headers=headers).status_code, 403)
        admin = self.client.get("/api/v1/memory/config", headers={"X-PetJourney-Admin-Token": "admin-test-token"})
        self.assertEqual(admin.status_code, 200)

    def test_web_routes_are_not_affected(self) -> None:
        self.assertEqual(self.client.get("/api/v1/web/meta").status_code, 200)
        self.assertEqual(self.client.get("/health").status_code, 200)


class LegacyClosedPolicyTests(WebPlatformTestBase):
    policy = "closed"

    def test_closed_keeps_only_auth_and_web(self) -> None:
        self.assertEqual(self.client.post("/api/v1/scheduler/tick").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/pet_dna/PJ-XXXX").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/web/meta").status_code, 200)
        self.assertNotEqual(
            self.client.post("/api/v1/auth/apple", json={"identity_token": "mock-apple-sub:x"}).status_code, 404
        )


if __name__ == "__main__":
    unittest.main()
