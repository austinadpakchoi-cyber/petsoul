"""Mock 生图 Provider（未配置密钥时抛错占位）。"""

from __future__ import annotations

from ..config import Settings
from .models import GeneratedImage, ImageReference


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

