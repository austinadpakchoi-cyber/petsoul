"""生图结果与参考图模型。"""

from __future__ import annotations

from dataclasses import dataclass


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
