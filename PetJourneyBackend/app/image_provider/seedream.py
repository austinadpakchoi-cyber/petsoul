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

    # 方舟参考图 role → 上线顺序（宠物身份参考必须排在地点环境参考之前，
    # 与提示词里的「图一/图二」位置说明一一对应）。
    REFERENCE_ROLE_ORDER = {"pet_identity": 0, "place_environment": 1}

    def __init__(self, settings: Settings):
        self.settings = settings
        self.last_remote_call_succeeded = False
        self.last_remote_error = ""

    def _api_key(self) -> str | None:
        # volcengine 生图与豆包语音共用方舟同一 key 体系，优先 DOUBAO_API_KEY；
        # 仅配置了 PETJOURNEY_IMAGE_API_KEY 的部署回退到 image_api_key。
        return self.settings.doubao_api_key or self.settings.image_api_key

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
            # 火山方舟参考图协议：image 字段是 URL / data-URI 字符串（或其数组），
            # 不接受 {image_data, role} 对象（旧格式会被方舟以 400 拒绝）。
            # role 只用于提示词契约，线上按 role 排序后以 data-URI 透传。
            ordered_references = sorted(
                valid_references,
                key=lambda reference: self.REFERENCE_ROLE_ORDER.get(reference.role or "", 99),
            )
            payload["image"] = [self._data_uri(reference) for reference in ordered_references]
            payload["prompt"] = self._with_positional_reference_notes(prompt, ordered_references)

        try:
            response = self._post_json("/images/generations", payload, api_key=api_key)
            image = self._extract_image(response)
            self.last_remote_call_succeeded = True
            return image
        except Exception as exc:
            self.last_remote_error = self._redact_error(str(exc), api_key)
            raise RuntimeError(self.last_remote_error) from exc

    @staticmethod
    def _data_uri(reference: ImageReference) -> str:
        mime_type = reference.mime_type if reference.mime_type.startswith("image/") else "image/png"
        encoded = base64.b64encode(reference.image_bytes).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    @staticmethod
    def _with_positional_reference_notes(
        prompt: str,
        references: list[ImageReference],
    ) -> str:
        """给提示词补上方舟参考图的位置说明（方舟按「图一/图二」理解多参考图）。"""
        role_labels = {
            "pet_identity": "TA 的照片，保持长相、毛色与特征一致",
            "place_environment": "地点的照片，只借用场景、光线与氛围",
        }
        ordinals = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
        notes: list[str] = []
        for index, reference in enumerate(references):
            ordinal = ordinals[index] if index < len(ordinals) else str(index + 1)
            label = role_labels.get(reference.role or "", "参考")
            notes.append(f"图{ordinal}是{label}")
        if not notes:
            return prompt
        return f"{prompt.strip()}\n\n参考图说明：{'；'.join(notes)}。"

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

