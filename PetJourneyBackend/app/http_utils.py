"""HTTP 层共享工具：上传落盘、文件名清洗、公开媒体 URL（纯底层工具）。

架构审计 P1-3 后本模块只剩「真正的 HTTP/文件工具」：
- parse_dna / with_not_found → app/routers/helpers.py
- ensure_demo_media / DEMO_* 常量 → app/seeding.py
- lightweight_illustrated_guide_plan → app/pet_guide_engine/preview_plan.py
本模块不得 import 任何引擎层模块（依赖方向门禁会检查）。
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import UploadFile

from .config import Settings


async def save_upload(upload_dir: Path, upload: UploadFile | None, subdir: str = "pet_photos") -> str | None:
    if upload is None:
        return None
    data = await upload.read()
    if not data:
        return None

    filename = sanitize_filename(upload.filename or "pet-photo.jpg")
    suffix = Path(filename).suffix.lower() or ".jpg"
    target_dir = upload_dir / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uuid.uuid4().hex}{suffix}"
    target.write_bytes(data)
    return target.relative_to(upload_dir).as_posix()


def sanitize_filename(filename: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "-", filename)


def public_photo_url(settings: Settings, photo_path: str | None) -> str | None:
    return public_media_url(settings, photo_path)


def public_media_url(settings: Settings, media_path: str | None) -> str | None:
    if not media_path:
        return None
    if not settings.public_base_url:
        return None
    base = settings.public_base_url.rstrip("/")
    return f"{base}/media/{media_path}"
