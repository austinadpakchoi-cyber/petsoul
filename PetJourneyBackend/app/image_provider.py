from __future__ import annotations

from dataclasses import dataclass
import base64
import json
from uuid import uuid4
from urllib import error, request
from typing import Protocol

from .config import Settings


@dataclass(frozen=True, slots=True)
class GeneratedImage:
    image_bytes: bytes
    mime_type: str
    model: str
    provider: str
    source: str
    revised_prompt: str | None = None


@dataclass(frozen=True, slots=True)
class ImageReference:
    image_bytes: bytes
    mime_type: str
    filename: str
    role: str
    source: str | None = None


class ImageProvider(Protocol):
    provider_name: str

    def generate_image(self, prompt: str, *, size: str = "1024x1024") -> GeneratedImage:
        ...

    def generate_image_with_reference(
        self,
        prompt: str,
        *,
        reference_image_bytes: bytes,
        reference_mime_type: str,
        size: str = "1024x1024",
    ) -> GeneratedImage:
        ...

    def generate_image_with_references(
        self,
        prompt: str,
        *,
        references: list[ImageReference],
        size: str = "1024x1024",
    ) -> GeneratedImage:
        ...

    def config_snapshot(self) -> dict[str, str | bool | float]:
        ...


class MockImageProvider:
    provider_name = "mock-image-provider"

    def __init__(self, settings: Settings):
        self.settings = settings

    def generate_image(self, prompt: str, *, size: str = "1024x1024") -> GeneratedImage:
        raise RuntimeError("image provider is not configured for remote generation")

    def generate_image_with_reference(
        self,
        prompt: str,
        *,
        reference_image_bytes: bytes,
        reference_mime_type: str,
        size: str = "1024x1024",
    ) -> GeneratedImage:
        raise RuntimeError("image provider is not configured for reference generation")

    def generate_image_with_references(
        self,
        prompt: str,
        *,
        references: list[ImageReference],
        size: str = "1024x1024",
    ) -> GeneratedImage:
        raise RuntimeError("image provider is not configured for multi-reference generation")

    def config_snapshot(self) -> dict[str, str | bool | float]:
        return {
            "provider": self.provider_name,
            "image_model": self.settings.image_model,
            "base_url": self.settings.image_base_url.rstrip("/"),
            "remote_configured": bool(self.settings.image_api_key),
            "remote_call_active": False,
            "remote_call_enabled": False,
            "reference_image_supported": False,
            "multi_reference_image_supported": False,
            "timeout_seconds": self.settings.image_timeout_seconds,
            "last_remote_success": False,
            "last_remote_error": "",
        }


class OpenAICompatibleImageProvider:
    provider_name = "openai-compatible-image-provider"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.last_remote_call_succeeded = False
        self.last_remote_error = ""

    def generate_image(self, prompt: str, *, size: str = "1024x1024") -> GeneratedImage:
        self.last_remote_call_succeeded = False
        self.last_remote_error = ""
        if not self.settings.image_api_key:
            self.last_remote_error = "image API key is not configured"
            raise RuntimeError(self.last_remote_error)

        payload = {
            "model": self.settings.image_model,
            "prompt": prompt,
            "size": size,
            "n": 1,
        }

        try:
            response = self._post_json("/images/generations", payload)
            image = self._extract_image(response)
            self.last_remote_call_succeeded = True
            return image
        except Exception as exc:
            self.last_remote_error = self._redact_error(str(exc))
            raise RuntimeError(self.last_remote_error) from exc

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
        if not self.settings.image_api_key:
            self.last_remote_error = "image API key is not configured"
            raise RuntimeError(self.last_remote_error)
        valid_references = [reference for reference in references if reference.image_bytes]
        if not valid_references:
            self.last_remote_error = "reference image is empty"
            raise RuntimeError(self.last_remote_error)

        fields = {
            "model": self.settings.image_model,
            "prompt": prompt,
            "size": size,
            "n": "1",
        }
        try:
            response = self._post_multipart(
                "/images/edits",
                fields=fields,
                files=valid_references,
            )
            image = self._extract_image(response)
            self.last_remote_call_succeeded = True
            return image
        except Exception as exc:
            self.last_remote_error = self._redact_error(str(exc))
            raise RuntimeError(self.last_remote_error) from exc

    def config_snapshot(self) -> dict[str, str | bool | float]:
        return {
            "provider": self.provider_name,
            "image_model": self.settings.image_model,
            "base_url": self.settings.image_base_url.rstrip("/"),
            "remote_configured": bool(self.settings.image_api_key),
            "remote_call_active": bool(self.settings.image_api_key),
            "remote_call_enabled": bool(self.settings.image_api_key),
            "reference_image_supported": bool(self.settings.image_api_key),
            "multi_reference_image_supported": bool(self.settings.image_api_key),
            "timeout_seconds": self.settings.image_timeout_seconds,
            "last_remote_success": self.last_remote_call_succeeded,
            "last_remote_error": self.last_remote_error,
        }

    def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        url = f"{self.settings.image_base_url.rstrip('/')}{path}"
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.image_api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(req, timeout=self.settings.image_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"image relay request failed: {exc.code} {detail}") from exc

    def _post_multipart(
        self,
        path: str,
        *,
        fields: dict[str, str],
        files: list[ImageReference],
    ) -> dict[str, object]:
        boundary = f"PetSoulBoundary{uuid4().hex}"
        chunks: list[bytes] = []
        for key, value in fields.items():
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"),
                    str(value).encode("utf-8"),
                    b"\r\n",
                ]
            )
        for file in files:
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    (
                        'Content-Disposition: form-data; name="image[]"; '
                        f'filename="{file.filename}"\r\n'
                    ).encode("utf-8"),
                    f"Content-Type: {file.mime_type}\r\n\r\n".encode("utf-8"),
                    file.image_bytes,
                    b"\r\n",
                ]
            )
        chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
        body = b"".join(chunks)
        url = f"{self.settings.image_base_url.rstrip('/')}{path}"
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.image_api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        try:
            with request.urlopen(req, timeout=self.settings.image_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"image relay reference request failed: {exc.code} {detail}") from exc

    def _extract_image(self, response: dict[str, object]) -> GeneratedImage:
        data = response.get("data")
        if not isinstance(data, list) or not data:
            raise ValueError("image response did not contain data")

        first = data[0]
        if not isinstance(first, dict):
            raise ValueError("image response item was not an object")

        revised_prompt = first.get("revised_prompt")
        revised_prompt_value = revised_prompt if isinstance(revised_prompt, str) else None

        b64_json = first.get("b64_json")
        if isinstance(b64_json, str) and b64_json:
            return GeneratedImage(
                image_bytes=base64.b64decode(b64_json),
                mime_type="image/png",
                model=str(response.get("model") or self.settings.image_model),
                provider=self.provider_name,
                source="b64_json",
                revised_prompt=revised_prompt_value,
            )

        url = first.get("url")
        if isinstance(url, str) and url:
            image_bytes, mime_type = self._download_image(url)
            return GeneratedImage(
                image_bytes=image_bytes,
                mime_type=mime_type,
                model=str(response.get("model") or self.settings.image_model),
                provider=self.provider_name,
                source="url",
                revised_prompt=revised_prompt_value,
            )

        raise ValueError("image response did not contain b64_json or url")

    def _download_image(self, url: str) -> tuple[bytes, str]:
        req = request.Request(url, method="GET", headers={"Accept": "image/*"})
        with request.urlopen(req, timeout=self.settings.image_timeout_seconds) as response:
            mime_type = response.headers.get_content_type() or "image/png"
            return response.read(), mime_type

    def _redact_error(self, message: str) -> str:
        if self.settings.image_api_key:
            return message.replace(self.settings.image_api_key, "[REDACTED]")
        return message


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


def build_image_provider(settings: Settings) -> ImageProvider:
    if settings.image_provider_type == "volcengine" and (settings.image_api_key or settings.doubao_api_key):
        return DoubaoSeedreamImageProvider(settings)
    if settings.image_api_key:
        return OpenAICompatibleImageProvider(settings)
    return MockImageProvider(settings)
