"""PetGuideEngine 基础 mixin：依赖注入 + 共享 HTTP/JSON 工具。"""

from __future__ import annotations

from json import JSONDecodeError
import json
from urllib import error, request

from ..config import Settings
from ..guide_orchestrator import build_guide_orchestration_policy


class PetGuideEngineBaseMixin:
    provider_name = "pet-guide-brain"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.last_remote_call_succeeded = False
        self.last_remote_error = ""
        self.orchestration_policy = build_guide_orchestration_policy()
    def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        url = f"{self.settings.openai_base_url.rstrip('/')}{path}"
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(req, timeout=self.settings.agent_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"guide brain request failed: {exc.code} {detail}") from exc
    def _post_doubao_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        url = f"{self.settings.doubao_base_url.rstrip('/')}{path}"
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.doubao_api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(req, timeout=self.settings.doubao_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"doubao guide voice request failed: {exc.code} {detail}") from exc
    def _extract_json_object(self, response: dict[str, object]) -> dict[str, object]:
        candidate = response.get("output_text")
        if isinstance(candidate, str):
            return self._parse_json_candidate(candidate)

        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, str):
                return self._parse_json_candidate(content)

        output = response.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for content_item in content:
                    if not isinstance(content_item, dict):
                        continue
                    text = content_item.get("text") or content_item.get("output_text")
                    if isinstance(text, str):
                        return self._parse_json_candidate(text)
        raise ValueError("guide brain response did not contain parseable JSON")
    def _parse_json_candidate(self, value: str) -> dict[str, object]:
        text = value.strip()
        if text.startswith("```"):
            text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            parsed = json.loads(text)
        except JSONDecodeError as exc:
            raise ValueError("guide brain returned non-json text") from exc
        if not isinstance(parsed, dict):
            raise ValueError("guide brain returned non-object JSON")
        return parsed
    def _int_or_default(self, value: object, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    def _redact_error(self, message: str) -> str:
        if self.settings.openai_api_key:
            return message.replace(self.settings.openai_api_key, "[REDACTED]")
        if self.settings.doubao_api_key:
            return message.replace(self.settings.doubao_api_key, "[REDACTED]")
        return message
