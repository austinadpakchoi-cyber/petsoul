"""火山方舟/即梦 Seedream 生图 Provider（支持多参考图角色一致性）。"""

from __future__ import annotations

import base64
import json
from uuid import uuid4
from urllib import error, request

from ..config import Settings
from .models import GeneratedImage, ImageReference


class DoubaoSeedreamImageProvider:
    """火山方舟/即梦 Seedream 生图 Provider（支持多参考图角色一致性）。"""

    provider_name = "doubao-seedream-image-provider"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.last_remote_call_succeeded = False
        self.last_remote_error = ""

    def _api_key(self) -> str | None:
        return self.settings.image_api_key or self.settings.doubao_api_key

    def generate_image(self, prompt: str, *, size: str = "1024x1024") -> GeneratedImage:
        return self.generate_image_with_references(prompt, references=[], size=size)

    def generate_image_with_reference(
        self,
        prompt: str,
        *,
        reference_image_bytes: bytes,
        reference_mime_type: str,
        size: str = "1024x1024",
    ) -> GeneratedImage:
        file_suffix = ".jpg" if reference_mime_type in {"image/jpeg", "image/jpg"} else ".png"
        return self.generate_image_with_references(
            prompt,
            references=[
                ImageReference(
                    image_bytes=reference_image_bytes,
                    mime_type=reference_mime_type,
                    filename=f"pet-reference-{uuid4().hex}{file_suffix}",
                    role="pet_identity",
                )
            ],
            size=size,
        )

    def generate_image_with_references(
        self,
        prompt: str,
        *,
        references: list[ImageReference],
        size: str = "1024x1024",
    ) -> GeneratedImage:
        self.last_remote_call_succeeded = False
        self.last_remote_error = ""
        api_key = self._api_key()
        if not api_key:
            self.last_remote_error = "volcengine image API key is not configured"
            raise RuntimeError(self.last_remote_error)

        payload: dict[str, object] = {
            "model": self.settings.volcengine_image_model,
            "prompt": prompt,
            "size": size,
            "n": 1,
            "response_format": "url",
        }
        valid_references = [reference for reference in references if reference.image_bytes]
        if valid_references:
            payload["image"] = [
                {
                    "image_data": base64.b64encode(reference.image_bytes).decode("ascii"),
                    "role": reference.role or "reference",
                }
                for reference in valid_references
            ]

        try:
            response = self._post_json("/images/generations", payload, api_key=api_key)
            image = self._extract_image(response)
            self.last_remote_call_succeeded = True
            return image
        except Exception as exc:
            self.last_remote_error = self._redact_error(str(exc), api_key)
            raise RuntimeError(self.last_remote_error) from exc

    def config_snapshot(self) -> dict[str, str | bool | float]:
        return {
            "provider": self.provider_name,
            "image_model": self.settings.volcengine_image_model,
            "base_url": self.settings.doubao_base_url.rstrip("/"),
            "remote_configured": bool(self._api_key()),
            "remote_call_active": bool(self._api_key()),
            "remote_call_enabled": bool(self._api_key()),
            "reference_image_supported": True,
            "multi_reference_image_supported": True,
            "timeout_seconds": self.settings.image_timeout_seconds,
            "last_remote_success": self.last_remote_call_succeeded,
            "last_remote_error": self.last_remote_error,
        }

    def _post_json(self, path: str, payload: dict[str, object], *, api_key: str) -> dict[str, object]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        url = f"{self.settings.doubao_base_url.rstrip('/')}{path}"
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(req, timeout=self.settings.image_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"seedream image request failed: {exc.code} {detail}") from exc

    def _extract_image(self, response: dict[str, object]) -> GeneratedImage:
        data = response.get("data")
        if not isinstance(data, list) or not data:
            raise ValueError("image response did not contain data")

        first = data[0]
        if not isinstance(first, dict):
            raise ValueError("image response item was not an object")

        b64_json = first.get("b64_json")
        if isinstance(b64_json, str) and b64_json:
            return GeneratedImage(
                image_bytes=base64.b64decode(b64_json),
                mime_type="image/png",
                model=str(response.get("model") or self.settings.volcengine_image_model),
                provider=self.provider_name,
                source="b64_json",
            )

        url = first.get("url")
        if isinstance(url, str) and url:
            image_bytes, mime_type = self._download_image(url)
            return GeneratedImage(
                image_bytes=image_bytes,
                mime_type=mime_type,
                model=str(response.get("model") or self.settings.volcengine_image_model),
                provider=self.provider_name,
                source="url",
            )

        raise ValueError("image response did not contain b64_json or url")

    def _download_image(self, url: str) -> tuple[bytes, str]:
        req = request.Request(url, method="GET", headers={"Accept": "image/*"})
        with request.urlopen(req, timeout=self.settings.image_timeout_seconds) as response:
            mime_type = response.headers.get_content_type() or "image/png"
            return response.read(), mime_type

    def _redact_error(self, message: str, api_key: str) -> str:
        return message.replace(api_key, "[REDACTED]") if api_key else message

