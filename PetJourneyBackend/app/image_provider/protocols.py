"""生图 Provider 协议。"""

from __future__ import annotations

from typing import Protocol

from .models import GeneratedImage, ImageReference


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

