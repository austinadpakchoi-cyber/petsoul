"""运营素材库：原件、缩略图、来源、使用范围、哈希，外加一条硬规则。

**硬规则：玩家的参考照进不了素材库。** 不是靠提醒，是靠三道一起挡：

1. 只接受**员工从自己机器上传的文件**。没有"给个服务器路径"或"给个 URL 让服务器去抓"的入口——
   那两种做法一旦存在，参考照目录就只隔着一个路径字符串。
2. 入库前按 **sha256 比对**玩家参考照（`web_pet_profiles.photo_ref` 指向的文件）。
   命中就拒绝，并留一条 denied 审计。先比文件大小再比哈希，避免每次上传把整个目录读一遍。
3. 素材文件存在**独立目录**（`<数据库目录>/admin-assets`），既不在公开挂载的 `/media` 下，
   也不在玩家私有媒体目录里。公开素材只由 `/api/v1/web/assets/{asset_id}` 这一个受控入口提供。

来源与使用范围**没有默认值**：上传时必须说清楚这张图哪来的、能用在哪。说不清就别入库。

缩略图用 Pillow 生成。**Pillow 不在 requirements.txt 里**（本机装着，来源是传递依赖），
所以这里做成可降级：装不上就如实记 `thumb_note`、`thumb_rel_path` 留空，不假装有缩略图。
已作为跨窗口请求记给 I：要么把 Pillow 写进依赖，要么这项能力永久标为不可用。
"""

from __future__ import annotations

import hashlib
import io
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from ..web_pets.media import EXTENSIONS, MediaRejected, sanitize_image
from ..web_platform.uow import unit_of_work
from .audit import AuditLog
from .commands import ActorContext, require_reason
from .errors import AdminAPIError, AdminErrorCode
from .permissions import Permission

SOURCES = ("own_work", "commissioned", "public_domain", "licensed", "ai_generated")
USAGE_SCOPES = ("public", "internal")
THUMB_BOX = (320, 320)
# 解压炸弹护栏：员工上传也不例外。Pillow 默认 ~1.79 亿像素，这里收紧到 4000 万。
MAX_PIXELS = 40_000_000


@dataclass(frozen=True, slots=True)
class AssetRow:
    asset_id: str
    filename: str
    content_type: str
    byte_size: int
    sha256: str
    width: int | None
    height: int | None
    has_thumbnail: bool
    thumb_note: str | None
    source: str
    source_note: str
    license: str | None
    usage_scope: str
    status: str
    version: int
    uploaded_by: str
    uploaded_at: datetime
    retired_at: datetime | None
    retired_reason: str | None


def _row(row) -> AssetRow:
    return AssetRow(
        asset_id=row["asset_id"], filename=row["filename"], content_type=row["content_type"],
        byte_size=int(row["byte_size"]), sha256=row["sha256"],
        width=None if row["width"] is None else int(row["width"]),
        height=None if row["height"] is None else int(row["height"]),
        has_thumbnail=bool(row["thumb_rel_path"]), thumb_note=row["thumb_note"],
        source=row["source"], source_note=row["source_note"], license=row["license"],
        usage_scope=row["usage_scope"], status=row["status"], version=int(row["version"]),
        uploaded_by=row["uploaded_by"], uploaded_at=parse_dt(row["uploaded_at"]),
        retired_at=parse_dt(row["retired_at"]) if row["retired_at"] else None,
        retired_reason=row["retired_reason"],
    )


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def thumbnail(data: bytes, content_type: str) -> tuple[bytes | None, str | None]:
    """返回 (缩略图字节, 说明)。生成不了就返回 (None, 原因)——不假装有。"""
    try:
        from PIL import Image
    except ImportError:
        return None, "这套环境没有安装 Pillow，缩略图未生成（原件与哈希照常记录）。"
    try:
        Image.MAX_IMAGE_PIXELS = MAX_PIXELS
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            copy = image.convert("RGB") if image.mode not in ("RGB", "RGBA", "L") else image.copy()
            copy.thumbnail(THUMB_BOX)
            buffer = io.BytesIO()
            fmt = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}[content_type]
            copy.save(buffer, format=fmt)
            return buffer.getvalue(), None
    except Exception as exc:  # noqa: BLE001 - 解码失败不该让整次上传失败；如实记原因
        return None, f"缩略图生成失败（{type(exc).__name__}），原件与哈希照常记录。"


def dimensions(data: bytes) -> tuple[int | None, int | None]:
    try:
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = MAX_PIXELS
        with Image.open(io.BytesIO(data)) as image:
            return image.width, image.height
    except Exception:  # noqa: BLE001
        return None, None


class AdminAssets:
    def __init__(self, storage: JourneyStorage, audit: AuditLog, *, root: Path, private_media_root: Path) -> None:
        self.storage = storage
        self.audit = audit
        self.root = root
        self.private_media_root = private_media_root

    # ---- 硬规则：玩家参考照不能入库 ----
    def matches_owner_reference(self, data: bytes, digest: str) -> str | None:
        """命中就返回那只宠物的编号。先比大小再比哈希：不把整个参考照目录每次都读一遍。"""
        size = len(data)
        with self.storage.connect() as conn:
            rows = conn.execute(
                "SELECT pet_id, photo_ref FROM web_pet_profiles WHERE photo_ref IS NOT NULL").fetchall()
        for row in rows:
            path = (self.private_media_root / row["photo_ref"])
            try:
                if not path.is_file() or path.stat().st_size != size:
                    continue
                if _digest(path.read_bytes()) == digest:
                    return row["pet_id"]
            except OSError:
                continue
        return None

    # ---- 上传 ----
    def upload(self, ctx: ActorContext, *, filename: str, data: bytes, source: str, source_note: str,
               license_note: str | None, usage_scope: str) -> dict[str, Any]:
        if source not in SOURCES:
            raise AdminAPIError.validation(f"来源只能是 {' / '.join(SOURCES)}。", field="source")
        if usage_scope not in USAGE_SCOPES:
            raise AdminAPIError.validation(f"使用范围只能是 {' / '.join(USAGE_SCOPES)}。", field="usage_scope")
        source_note = require_reason(source_note)
        try:
            clean, content_type = sanitize_image(data)
        except MediaRejected as exc:
            raise AdminAPIError.validation(f"这个文件不能作为素材：{exc.reason}。只接受 JPEG / PNG / WebP，不超过 5MB。",
                                           field="file") from exc

        digest = _digest(clean)
        audit_kwargs = {
            "action": "asset.upload", "permission": Permission.ASSET_MANAGE.value,
            "actor_staff_id": ctx.staff_id, "actor_username": ctx.username,
            "target_kind": "asset", "target_id": digest[:16], "reason": source_note,
            "operation_id": ctx.operation_id, "request_id": ctx.request_id,
        }
        # 原件与清洗后都比一遍：剥元数据会改变字节，但参考照本来也是清洗后入库的。
        hit = self.matches_owner_reference(clean, digest) or self.matches_owner_reference(data, _digest(data))
        if hit:
            self.audit.record(status="denied", outcome="owner_reference_photo",
                              changes={"pet_id": hit, "filename": filename[:80]}, **audit_kwargs)
            raise AdminAPIError(AdminErrorCode.forbidden,
                                "这张图和某位玩家的宠物参考照是同一份文件，不能收进公共素材库。"
                                "参考照属于那位主人，运营不能把它变成公共素材。", 403,
                                details={"reason": "owner_reference_photo", "pet_id": hit})

        with self.storage.connect() as conn:
            existing = conn.execute("SELECT asset_id FROM admin_assets WHERE sha256 = ?", (digest,)).fetchone()
        if existing is not None:
            raise AdminAPIError(AdminErrorCode.conflict, "这张图已经在素材库里了（按哈希判定）。", 409,
                                details={"asset_id": existing["asset_id"]})

        asset_id = f"AS-{uuid.uuid4().hex[:16].upper()}"
        width, height = dimensions(clean)
        thumb_bytes, thumb_note = thumbnail(clean, content_type)
        rel_path = self._store(asset_id, clean, content_type, suffix="")
        thumb_rel = self._store(asset_id, thumb_bytes, content_type, suffix="-thumb") if thumb_bytes else None
        now = iso(utcnow())
        with unit_of_work(self.storage) as conn:
            try:
                conn.execute(
                    "INSERT INTO admin_assets (asset_id, filename, content_type, byte_size, sha256, width, height, rel_path, "
                    "thumb_rel_path, thumb_note, source, source_note, license, usage_scope, status, version, uploaded_by, uploaded_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 1, ?, ?)",
                    (asset_id, filename[:120] or "upload", content_type, len(clean), digest, width, height, rel_path,
                     thumb_rel, thumb_note, source, source_note, (license_note or None), usage_scope, ctx.staff_id, now),
                )
            except sqlite3.IntegrityError as exc:
                raise AdminAPIError(AdminErrorCode.conflict, "这张图已经在素材库里了（按哈希判定）。", 409) from exc
            self.audit.record_in(conn, status="succeeded", outcome=usage_scope,
                                 changes={"asset_id": asset_id, "sha256": digest, "bytes": len(clean),
                                          "source": source, "usage_scope": usage_scope,
                                          "thumbnail": bool(thumb_bytes)},
                                 **{**audit_kwargs, "target_id": asset_id})
        return {"asset": _as_dict(self.get(asset_id)),
                "note": "原件、哈希、来源与使用范围都已记录。" + (thumb_note or "缩略图已生成。")}

    def _store(self, asset_id: str, data: bytes, content_type: str, *, suffix: str) -> str:
        folder = self.root / asset_id[:6]
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{asset_id}{suffix}{EXTENSIONS[content_type]}"
        (folder / name).write_bytes(data)
        return (Path(asset_id[:6]) / name).as_posix()

    # ---- 读 ----
    def get(self, asset_id: str) -> AssetRow:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM admin_assets WHERE asset_id = ?", (asset_id,)).fetchone()
        if row is None:
            raise AdminAPIError.not_found("这个素材")
        return _row(row)

    def list_assets(self, *, usage_scope: str | None = None, include_retired: bool = False, limit: int = 100) -> list[dict]:
        where, params = [], []
        if usage_scope:
            where.append("usage_scope = ?")
            params.append(usage_scope)
        if not include_retired:
            where.append("status = 'active'")
        clause = f" WHERE {' AND '.join(where)}" if where else ""
        with self.storage.connect() as conn:
            rows = conn.execute(f"SELECT * FROM admin_assets{clause} ORDER BY uploaded_at DESC LIMIT ?",
                                [*params, max(1, min(500, limit))]).fetchall()
        return [_as_dict(_row(row)) for row in rows]

    def file_path(self, asset_id: str, *, thumb: bool = False) -> tuple[Path, str] | None:
        """磁盘路径 + content type。路径必须落在素材根目录内，防止 rel_path 被做成穿越。"""
        try:
            asset = self.get(asset_id)
        except AdminAPIError:
            return None
        with self.storage.connect() as conn:
            row = conn.execute("SELECT rel_path, thumb_rel_path FROM admin_assets WHERE asset_id = ?", (asset_id,)).fetchone()
        rel = row["thumb_rel_path"] if thumb else row["rel_path"]
        if not rel:
            return None
        path = (self.root / rel).resolve()
        try:
            path.relative_to(self.root.resolve())
        except ValueError:
            return None
        return (path, asset.content_type) if path.is_file() else None

    def public_asset(self, asset_id: str) -> AssetRow | None:
        """玩家侧只拿得到 public + active 的素材。internal 或已下架一律当不存在。"""
        try:
            asset = self.get(asset_id)
        except AdminAPIError:
            return None
        return asset if asset.usage_scope == "public" and asset.status == "active" else None

    # ---- 下架 ----
    def retire(self, ctx: ActorContext, asset_id: str, *, reason: str, expected_version: int) -> dict[str, Any]:
        reason = require_reason(reason)
        now = iso(utcnow())
        with unit_of_work(self.storage) as conn:
            row = conn.execute("SELECT status, version FROM admin_assets WHERE asset_id = ?", (asset_id,)).fetchone()
            if row is None:
                raise AdminAPIError.not_found("这个素材")
            if int(row["version"]) != expected_version:
                raise AdminAPIError.version_conflict(expected_version, int(row["version"]))
            if row["status"] == "retired":
                raise AdminAPIError(AdminErrorCode.conflict, "这个素材已经下架了。", 409)
            used = conn.execute(
                "SELECT i.item_id, i.slug FROM admin_content_items i "
                "JOIN admin_content_revisions r ON r.item_id = i.item_id AND r.revision = i.live_revision "
                "WHERE i.status = 'published' AND r.body_json LIKE ?", (f'%"{asset_id}"%',)).fetchall()
            if used:
                # 还挂在已发布内容上就不许下架：否则玩家侧会拿到一个取不到的图。
                raise AdminAPIError(AdminErrorCode.conflict,
                                    "这个素材还挂在已发布的内容上，先把那些内容改掉或撤下再下架。", 409,
                                    details={"used_by": [dict(r) for r in used]})
            conn.execute("UPDATE admin_assets SET status = 'retired', version = version + 1, retired_at = ?, "
                         "retired_by = ?, retired_reason = ? WHERE asset_id = ?", (now, ctx.staff_id, reason, asset_id))
            self.audit.record_in(conn, action="asset.retire", status="succeeded", outcome="retired",
                                 permission=Permission.ASSET_MANAGE.value, actor_staff_id=ctx.staff_id,
                                 actor_username=ctx.username, target_kind="asset", target_id=asset_id,
                                 reason=reason, operation_id=ctx.operation_id, request_id=ctx.request_id,
                                 changes={"asset_id": asset_id})
        return {"asset": _as_dict(self.get(asset_id)),
                "note": "已下架：玩家侧取不到了；文件与哈希保留，作为审计依据。"}


def _as_dict(row: AssetRow) -> dict[str, Any]:
    return {field: getattr(row, field) for field in AssetRow.__slots__}
