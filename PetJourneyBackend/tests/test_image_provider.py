"""DoubaoSeedreamImageProvider 单元测试（monkeypatch urlopen）。"""

from base import *


class SeedreamImageProviderTests(PetJourneyApiTestBase):

    def _provider(self, captured: dict) -> DoubaoSeedreamImageProvider:
        class FakeSeedreamProvider(DoubaoSeedreamImageProvider):
            captured_payload: dict[str, object] | None = None

            def _post_json(self, path: str, payload: dict[str, object], *, api_key: str) -> dict[str, object]:
                FakeSeedreamProvider.captured_payload = payload
                return {"data": [{"b64_json": captured["b64"]}], "model": "doubao-seedream-4-0-250828"}

        settings = Settings(
            image_provider_type="volcengine",
            doubao_api_key="test-volc-key",
        )
        return FakeSeedreamProvider(settings)

    def test_generate_image_payload_has_no_reference_field(self) -> None:
        import base64 as b64

        fake = {"b64": b64.b64encode(b"PNGDATA").decode("ascii")}
        provider = self._provider(fake)
        image = provider.generate_image("一只小狗在海边", size="1024x1024")
        self.assertEqual(image.image_bytes, b"PNGDATA")
        payload = provider.captured_payload
        assert payload is not None
        self.assertEqual(payload["model"], "doubao-seedream-4-0-250828")
        self.assertEqual(payload["response_format"], "url")
        self.assertNotIn("image", payload)

    def test_two_references_map_to_image_array_with_roles(self) -> None:
        import base64 as b64

        fake = {"b64": b64.b64encode(b"PNGDATA").decode("ascii")}
        provider = self._provider(fake)
        pet_ref = ImageReference(image_bytes=b"PET", mime_type="image/png", filename="pet.png", role="pet_identity")
        place_ref = ImageReference(image_bytes=b"PLACE", mime_type="image/png", filename="place.png", role="place_environment")
        image = provider.generate_image_with_references(
            "参考图自拍",
            references=[pet_ref, place_ref],
            size="1536x1024",
        )
        self.assertEqual(image.image_bytes, b"PNGDATA")
        payload = provider.captured_payload
        assert payload is not None
        images = payload["image"]
        assert isinstance(images, list)
        self.assertEqual(len(images), 2)
        self.assertEqual(images[0]["role"], "pet_identity")
        self.assertEqual(images[0]["image_data"], b64.b64encode(b"PET").decode("ascii"))
        self.assertEqual(images[1]["role"], "place_environment")
        self.assertEqual(images[1]["image_data"], b64.b64encode(b"PLACE").decode("ascii"))

    def test_url_response_downloads_image(self) -> None:
        class FakeUrlSeedreamProvider(DoubaoSeedreamImageProvider):
            def _post_json(self, path: str, payload: dict[str, object], *, api_key: str) -> dict[str, object]:
                return {"data": [{"url": "https://example.com/image.png"}], "model": "doubao-seedream-4-0-250828"}

            def _download_image(self, url: str) -> tuple[bytes, str]:
                return b"URLDATA", "image/png"

        settings = Settings(image_provider_type="volcengine", doubao_api_key="test-volc-key")
        provider = FakeUrlSeedreamProvider(settings)
        image = provider.generate_image("一张明信片")
        self.assertEqual(image.image_bytes, b"URLDATA")
        self.assertEqual(image.mime_type, "image/png")

    def test_missing_key_raises_runtime_error(self) -> None:
        settings = Settings(image_provider_type="volcengine", doubao_api_key=None, image_api_key=None)
        provider = DoubaoSeedreamImageProvider(settings)
        with self.assertRaises(RuntimeError):
            provider.generate_image("一张图")
        self.assertIn("not configured", provider.last_remote_error)

    def test_http_error_is_redacted(self) -> None:
        class FakeErrorSeedreamProvider(DoubaoSeedreamImageProvider):
            def _post_json(self, path: str, payload: dict[str, object], *, api_key: str) -> dict[str, object]:
                raise RuntimeError(f"remote call failed with key {api_key}")

        settings = Settings(image_provider_type="volcengine", doubao_api_key="secret-volc-key")
        provider = FakeErrorSeedreamProvider(settings)
        with self.assertRaises(RuntimeError):
            provider.generate_image("一张图")
        self.assertNotIn("secret-volc-key", provider.last_remote_error)
        self.assertIn("[REDACTED]", provider.last_remote_error)

    def test_build_image_provider_dispatches_to_seedream(self) -> None:
        settings = Settings(image_provider_type="volcengine", doubao_api_key="test-volc-key")
        provider = build_image_provider(settings)
        self.assertEqual(provider.provider_name, "doubao-seedream-image-provider")
        snapshot = provider.config_snapshot()
        self.assertTrue(snapshot["remote_configured"])
        self.assertTrue(snapshot["reference_image_supported"])
        self.assertTrue(snapshot["multi_reference_image_supported"])
