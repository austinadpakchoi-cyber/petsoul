"""HTTP 层共享工具函数。

从 ``main.py`` 抽出，供各个 APIRouter 复用，避免端点与装配逻辑耦合在同一个
God File 里。
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from .agent_engine import (
    JourneyEngine,
    PetNotFoundError,
    ThoughtNotFoundError,
    TravelQuestNotFoundError,
)
from .config import Settings
from .route_planner import TravelRoutePlanner
from .schemas import JourneyPlan, PetDNA
from .utils import utcnow

DEMO_FRENCHIE_PROFILE_PHOTO = "demo/frenchie-profile.png"
DEMO_FRENCHIE_POSTCARD_PHOTO = "demo/frenchie-netcafe-postcard.png"


def parse_dna(raw: str) -> PetDNA:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"dna must be JSON: {exc}") from exc
    return PetDNA.model_validate(payload)


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


def ensure_demo_media(upload_dir: Path) -> None:
    # 版本化的 demo 素材（随代码/镜像分发）优先；data/uploads/demo 兼容旧部署
    candidate_dirs = (
        Path(__file__).resolve().parent / "assets" / "demo",
        Path(__file__).resolve().parents[1] / "data" / "uploads" / "demo",
    )
    target_dir = upload_dir / "demo"
    for filename in (DEMO_FRENCHIE_PROFILE_PHOTO, DEMO_FRENCHIE_POSTCARD_PHOTO):
        target = target_dir / Path(filename).name
        if target.exists():
            continue
        for source_dir in candidate_dirs:
            source = source_dir / Path(filename).name
            if source.exists():
                target_dir.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                break


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


def with_not_found(factory):
    try:
        return factory()
    except PetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="pet not found") from exc
    except ThoughtNotFoundError as exc:
        raise HTTPException(status_code=404, detail="thought translation not found") from exc
    except TravelQuestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="travel quest not found") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="resource not found") from exc


def lightweight_illustrated_guide_plan(engine: JourneyEngine, route_planner: TravelRoutePlanner, pet) -> JourneyPlan:
    now = utcnow()
    elapsed = (now - pet.created_at).total_seconds()
    city = engine._city_for_elapsed(elapsed, now=now)
    planner = getattr(route_planner, "fallback", route_planner)
    return planner.build_journey_plan(pet, city, now)
