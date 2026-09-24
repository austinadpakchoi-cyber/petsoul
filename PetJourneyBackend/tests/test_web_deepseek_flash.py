"""DeepSeek V4.1 Flash transport compatibility; no network or business data."""

import io
import json
import unittest
from unittest.mock import Mock, patch

from app.web_providers.llm import ChatUnavailable, OpenAICompatibleChat


class DeepSeekFlashTests(unittest.TestCase):
    def client(self, base="https://api.deepseek.com/v1", model="deepseek-flash"):
        self.meter = Mock()
        self.meter.allow.return_value = True
        return OpenAICompatibleChat(base_url=base, api_key="test-only", model=model,
                                    timeout=4, meter=self.meter)

    def response(self):
        return io.BytesIO(json.dumps({"model": "effective-flash", "choices": [
            {"message": {"content": '{"ok":true}', "reasoning_content": ""}}],
            "usage": {"prompt_tokens": 9, "completion_tokens": 4}}).encode())

    def test_flash_short_json_explicitly_disables_default_thinking(self):
        client = self.client()
        with patch("app.web_providers.llm.request.urlopen", return_value=self.response()) as send:
            result = client.complete([{"role": "user", "content": "Return JSON."}],
                                     max_tokens=64, json_mode=True)
        request = send.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload.get("thinking"), {"type": "disabled"})
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["max_tokens"], 64)
        self.assertEqual(request.full_url, "https://api.deepseek.com/v1/chat/completions")
        self.assertEqual(json.loads(result.text), {"ok": True})
        self.assertEqual((result.requested_model, result.effective_model),
                         ("deepseek-flash", "effective-flash"))
        self.assertEqual((result.prompt_tokens, result.completion_tokens), (9, 4))
        self.meter.record.assert_called_once_with("llm", True)

    def test_flash_plain_reply_also_uses_non_thinking(self):
        client = self.client(base="https://api.deepseek.com/")
        with patch("app.web_providers.llm.request.urlopen", return_value=self.response()) as send:
            client.complete([{"role": "user", "content": "Hello"}])
        payload = json.loads(send.call_args.args[0].data)
        self.assertEqual(payload.get("thinking"), {"type": "disabled"})
        self.assertNotIn("response_format", payload)

    def test_no_deepseek_extension_is_sent_to_other_provider_or_model(self):
        for base, model in [("https://relay.example/v1", "deepseek-flash"),
                            ("https://api.deepseek.com.evil.example/v1", "deepseek-flash"),
                            ("https://api.deepseek.com/v1", "deepseek-chat")]:
            with self.subTest(base=base, model=model):
                client = self.client(base, model)
                with patch("app.web_providers.llm.request.urlopen", return_value=self.response()) as send:
                    client.complete([{"role": "user", "content": "Hello"}])
                self.assertNotIn("thinking", json.loads(send.call_args.args[0].data))

    def test_daily_cap_prevents_send_with_new_model(self):
        client = self.client()
        self.meter.allow.return_value = False
        with patch("app.web_providers.llm.request.urlopen") as send:
            with self.assertRaisesRegex(ChatUnavailable, "daily_cap"):
                client.complete([{"role": "user", "content": "Hello"}])
        send.assert_not_called()
        self.meter.record.assert_not_called()

    def test_invalid_json_is_reported_without_repair_or_resend(self):
        for content in ['{"ok":<|OPENAI|>true}', '', '[]']:
            with self.subTest(content=content):
                client = self.client()
                reply = io.BytesIO(json.dumps({"model": "deepseek-flash", "choices": [
                    {"message": {"content": content}}]}).encode())
                with patch("app.web_providers.llm.request.urlopen", return_value=reply) as send:
                    with self.assertRaisesRegex(ChatUnavailable, "malformed_json"):
                        client.complete([{"role": "user", "content": "Return JSON"}], json_mode=True)
                self.assertEqual(send.call_count, 1)
                self.meter.allow.assert_called_once_with("llm")
                self.meter.record.assert_called_once_with("llm", False, "malformed JSON response")


if __name__ == "__main__":
    unittest.main()
