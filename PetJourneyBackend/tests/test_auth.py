from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


class AuthApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        settings = Settings(
            database_path=root / "petjourney.sqlite3",
            upload_dir=root / "uploads",
            public_base_url="http://testserver",
            auth_secret="test-secret",
            apple_auth_mode="mock",
        )
        self.client = TestClient(create_app(settings))

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def sign_in(self, sub: str = "austin-apple-sub", display_name: str | None = "Austin") -> dict:
        response = self.client.post(
            "/api/v1/auth/apple",
            json={"identity_token": f"mock-apple-sub:{sub}", "display_name": display_name},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def create_pet(self) -> str:
        dna = {
            "owner_title": "妈妈",
            "personality": "黏人、温柔、喜欢慢慢走",
            "favorite_places": ["海边", "阳台"],
            "hobby": ["晒太阳"],
            "catchphrase": "慢慢走，我在",
            "emoji_pref": "soft",
            "voice_style": "像寄一封小信",
        }
        response = self.client.post(
            "/api/v1/create_pet",
            data={
                "pet_name": "小福",
                "pet_type": "dog",
                "dna": json.dumps(dna, ensure_ascii=False),
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["pet_id"]

    def test_sign_in_creates_user_then_reuses_it(self) -> None:
        first = self.sign_in()
        self.assertTrue(first["is_new_user"])
        self.assertTrue(first["access_token"])
        self.assertTrue(first["user_id"].startswith("PU-"))

        second = self.sign_in(display_name=None)
        self.assertFalse(second["is_new_user"])
        self.assertEqual(second["user_id"], first["user_id"])
        # Apple 只在首次返回姓名，后续登录不应清空
        self.assertEqual(second["display_name"], "Austin")

    def test_invalid_identity_token_rejected(self) -> None:
        response = self.client.post(
            "/api/v1/auth/apple",
            json={"identity_token": "not-a-valid-token"},
        )
        self.assertEqual(response.status_code, 401)

    def test_me_requires_bearer_token(self) -> None:
        self.assertEqual(self.client.get("/api/v1/me").status_code, 401)
        self.assertEqual(
            self.client.get(
                "/api/v1/me", headers={"Authorization": "Bearer bogus"}
            ).status_code,
            401,
        )

    def test_claim_pet_binds_guest_pet_to_account(self) -> None:
        session = self.sign_in()
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        pet_id = self.create_pet()

        claimed = self.client.post(
            "/api/v1/me/claim_pet", json={"pet_id": pet_id}, headers=headers
        )
        self.assertEqual(claimed.status_code, 200)
        pets = claimed.json()["pets"]
        self.assertEqual([pet["pet_id"] for pet in pets], [pet_id])

        me = self.client.get("/api/v1/me", headers=headers)
        self.assertEqual(me.status_code, 200)
        self.assertEqual(len(me.json()["pets"]), 1)

        # 重复认领是幂等的
        again = self.client.post(
            "/api/v1/me/claim_pet", json={"pet_id": pet_id}, headers=headers
        )
        self.assertEqual(again.status_code, 200)

    def test_claim_pet_owned_by_other_user_conflicts(self) -> None:
        owner = self.sign_in(sub="owner-sub")
        stranger = self.sign_in(sub="stranger-sub", display_name="Stranger")
        pet_id = self.create_pet()

        first = self.client.post(
            "/api/v1/me/claim_pet",
            json={"pet_id": pet_id},
            headers={"Authorization": f"Bearer {owner['access_token']}"},
        )
        self.assertEqual(first.status_code, 200)

        conflict = self.client.post(
            "/api/v1/me/claim_pet",
            json={"pet_id": pet_id},
            headers={"Authorization": f"Bearer {stranger['access_token']}"},
        )
        self.assertEqual(conflict.status_code, 409)

    def test_claim_unknown_pet_returns_404(self) -> None:
        session = self.sign_in()
        response = self.client.post(
            "/api/v1/me/claim_pet",
            json={"pet_id": "PJ-DOESNOTEXIST"},
            headers={"Authorization": f"Bearer {session['access_token']}"},
        )
        self.assertEqual(response.status_code, 404)

    def test_auth_disabled_without_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            settings = Settings(
                database_path=root / "petjourney.sqlite3",
                upload_dir=root / "uploads",
                apple_auth_mode="mock",
            )
            client = TestClient(create_app(settings))
            response = client.post(
                "/api/v1/auth/apple",
                json={"identity_token": "mock-apple-sub:x"},
            )
            self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
