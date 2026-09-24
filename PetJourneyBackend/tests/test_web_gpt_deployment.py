"""Deployment switches and GPT web image transport; isolated HTTP substitutes, no network."""
from __future__ import annotations

import base64
import os
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from app.config import Settings, load_settings
from app.image_provider.openai import OpenAICompatibleImageProvider
from app.web_providers import build_web_providers
from app.web_providers.images import ImageUnavailable, NoIllustrator
from app.web_providers.readiness import image_ready

MODEL = "gpt-image-2.5-sunburst-2026-09-08"


class LiveSettingsTests(unittest.TestCase):
    def test_process_environment_reaches_live_brain_and_disables_shadow(self):
        values = {"PETJOURNEY_WEB_BRAIN_MODE": "live", "PETJOURNEY_WEB_HEARTBEAT_MODE": "off",
                  "PETJOURNEY_WEB_BRAIN_DAILY_PER_PET": "3"}
        with patch.dict(os.environ, values, clear=True), patch("app.config.load_env_file"):
            settings = load_settings()
        self.assertEqual((settings.web_brain_mode, settings.web_heartbeat_mode, settings.web_brain_daily_per_pet),
                         ("live", "off", 3))

    def test_default_still_has_no_paid_brain(self):
        with patch.dict(os.environ, {}, clear=True), patch("app.config.load_env_file"):
            settings = load_settings()
        self.assertEqual((settings.web_brain_mode, settings.web_heartbeat_mode), ("off", "shadow"))


class GPTWebTransportTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(web_providers_enabled=True, image_provider_type="openai",
                                 image_api_key="isolated-test-key", web_image_model=MODEL,
                                 image_base_url="https://relay.invalid/v1")
        self.meter = Mock()
        self.meter.allow.return_value = True
        with patch("app.web_providers.ProviderMeter", return_value=self.meter):
            self.illustrator = build_web_providers(self.settings, Mock()).illustrator

    def response(self):
        return {"data": [{"b64_json": base64.b64encode(b"isolated-image").decode()}]}

    def test_real_composition_selects_gpt_and_reports_ready(self):
        self.assertTrue(self.illustrator.available)
        self.assertTrue(image_ready(self.settings))
        self.assertIn("GPT", self.illustrator.provider_label)

    def test_reference_bytes_model_and_size_reach_edits(self):
        with patch.object(OpenAICompatibleImageProvider, "_post_multipart", return_value=self.response()) as send:
            result = self.illustrator.render("same cat", (b"reference", "image/jpeg"))
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args, ("/images/edits",))
        fields = send.call_args.kwargs["fields"]
        self.assertEqual((fields["model"], fields["size"], fields["n"], fields["quality"]),
                         (MODEL, "1024x1024", "1", "medium"))
        self.assertEqual(send.call_args.kwargs["files"][0].image_bytes, b"reference")
        self.assertEqual(result.image_bytes, b"isolated-image")
        self.meter.allow.assert_called_once_with("image")
        self.meter.record.assert_called_once_with("image", True)

    def test_no_reference_uses_generations_and_journal_keeps_portrait_aspect(self):
        with patch.object(OpenAICompatibleImageProvider, "_post_json", return_value=self.response()) as send:
            self.illustrator.render("portrait", size="1440x2560")
        self.assertEqual(send.call_args.args[0], "/images/generations")
        self.assertEqual(send.call_args.args[1]["size"], "1024x1536")
        self.assertEqual(send.call_args.args[1]["model"], MODEL)

    def test_timeout_is_unknown_and_never_retried_by_transport(self):
        with patch.object(OpenAICompatibleImageProvider, "_post_multipart", side_effect=TimeoutError) as send:
            with self.assertRaises(ImageUnavailable) as error:
                self.illustrator.render("cat", (b"reference", "image/jpeg"))
        self.assertEqual(error.exception.reason, "timeout")
        self.assertEqual(send.call_count, 1)

    def test_rejection_is_definite_and_is_not_retried(self):
        rejected = HTTPError("https://relay.invalid", 401, "rejected", {}, None)
        with patch.object(OpenAICompatibleImageProvider, "_post_json", side_effect=rejected) as send:
            with self.assertRaises(ImageUnavailable) as error:
                self.illustrator.render("cat")
        self.assertEqual(error.exception.reason, "rejected")
        self.assertEqual(send.call_count, 1)

    def test_cap_blocks_before_any_send(self):
        self.meter.allow.return_value = False
        with patch.object(OpenAICompatibleImageProvider, "_post_json") as send:
            with self.assertRaises(ImageUnavailable) as error:
                self.illustrator.render("cat")
        self.assertEqual(error.exception.reason, "daily_cap")
        send.assert_not_called()

    def test_missing_key_and_global_off_stay_disabled(self):
        self.settings.image_api_key = None
        with patch("app.web_providers.ProviderMeter", return_value=self.meter):
            self.assertIsInstance(build_web_providers(self.settings, Mock()).illustrator, NoIllustrator)
        self.assertFalse(image_ready(self.settings))
        self.settings.image_api_key = "test"
        self.settings.web_providers_enabled = False
        self.assertFalse(build_web_providers(self.settings, Mock()).illustrator.available)
        self.assertFalse(image_ready(self.settings))


if __name__ == "__main__":
    unittest.main()
