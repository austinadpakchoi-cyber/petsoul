"""图文攻略出图与缓存 mixin（架构审计 P1-2 包化，自 illustrated_guide.py 原样迁入）。"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from ..illustrated_guide_styles import get_illustrated_guide_style
from ..schemas import IllustratedGuidePage, IllustratedGuideStatus


class IllustratedGuideMediaMixin:
    def _attach_cached_images(
        self,
        *,
        pet_id: str,
        guide_id: str,
        pages: list[IllustratedGuidePage],
    ) -> list[IllustratedGuidePage]:
        cached_pages: list[IllustratedGuidePage] = []
        for page in pages:
            media_path = self._cached_page_media_path(pet_id=pet_id, guide_id=guide_id, page_index=page.index)
            if not media_path:
                cached_pages.append(page)
                continue
            media_url = self._media_url(media_path)
            cached_pages.append(
                page.model_copy(
                    update={
                        "status": IllustratedGuideStatus.ready,
                        "image_url": media_url,
                        "thumbnail_url": media_url,
                    }
                )
            )
        return cached_pages
    def _cached_page_media_path(self, *, pet_id: str, guide_id: str, page_index: int) -> str | None:
        target_dir = self.settings.upload_dir / "illustrated_guides" / pet_id
        if not target_dir.exists():
            return None
        matches = list(target_dir.glob(f"{guide_id}_page{page_index}_*"))
        if not matches:
            return None
        latest = max(matches, key=lambda path: path.stat().st_mtime)
        return str(latest.relative_to(self.settings.upload_dir))
    def _active_style_manifest_path(self, *, pet_id: str, base_guide_id: str) -> Path:
        return self.settings.upload_dir / "illustrated_guides" / pet_id / f"{base_guide_id}_active_style.txt"
    def _read_active_style_id(self, *, pet_id: str, base_guide_id: str) -> str | None:
        path = self._active_style_manifest_path(pet_id=pet_id, base_guide_id=base_guide_id)
        if not path.exists():
            return None
        style_id = path.read_text(encoding="utf-8").strip()
        if not get_illustrated_guide_style(style_id):
            return None
        guide_id = f"{base_guide_id}_{style_id}"
        if not self._cached_page_media_path(pet_id=pet_id, guide_id=guide_id, page_index=1):
            return None
        return style_id
    def _write_active_style_id(self, *, pet_id: str, base_guide_id: str, style_id: str) -> None:
        if not get_illustrated_guide_style(style_id):
            return
        target = self._active_style_manifest_path(pet_id=pet_id, base_guide_id=base_guide_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(style_id, encoding="utf-8")
    def _save_image(self, *, pet_id: str, guide_id: str, page_index: int, image_bytes: bytes, mime_type: str) -> str:
        suffix = ".jpg" if mime_type in {"image/jpeg", "image/jpg"} else ".png"
        target_dir = self.settings.upload_dir / "illustrated_guides" / pet_id
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{guide_id}_page{page_index}_{uuid4().hex[:8]}{suffix}"
        target = target_dir / filename
        target.write_bytes(image_bytes)
        return str(target.relative_to(self.settings.upload_dir))
    def _media_url(self, media_path: str) -> str | None:
        if not self.settings.public_base_url:
            return None
        return f"{self.settings.public_base_url.rstrip('/')}/media/{media_path}"
