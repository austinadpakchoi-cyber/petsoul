"""网页私有媒体：上传校验（大小/魔数）、去除元数据（EXIF/GPS 等）、存放在公开 /media 挂载之外。

只接受 JPEG / PNG / WebP。不做解码重编码（未引入图像库），因此只剥离元数据段；
图片内容本身的安全转码作为后续媒体模块事项记录在交接中。
"""

from __future__ import annotations

import struct
import uuid
from pathlib import Path

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_DROP_CHUNKS = {b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"}
WEBP_DROP_CHUNKS = {b"EXIF", b"XMP "}


class MediaRejected(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def sniff_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(PNG_SIGNATURE):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def strip_jpeg(data: bytes) -> bytes:
    """删除 APP1–APP15 与 COM 段（EXIF/XMP/GPS/注释），保留 APP0 与图像数据。"""
    out = bytearray(data[:2])
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            raise MediaRejected("jpeg_malformed")
        marker = data[i + 1]
        if marker == 0xDA:  # SOS：其后为压缩数据，原样保留
            out += data[i:]
            return bytes(out)
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            out += data[i : i + 2]
            i += 2
            continue
        length = struct.unpack(">H", data[i + 2 : i + 4])[0]
        segment = data[i : i + 2 + length]
        if not (0xE1 <= marker <= 0xEF or marker == 0xFE):
            out += segment
        i += 2 + length
    raise MediaRejected("jpeg_truncated")


def strip_png(data: bytes) -> bytes:
    out = bytearray(PNG_SIGNATURE)
    i = len(PNG_SIGNATURE)
    while i + 8 <= len(data):
        length = struct.unpack(">I", data[i : i + 4])[0]
        chunk_type = data[i + 4 : i + 8]
        end = i + 12 + length
        if end > len(data):
            raise MediaRejected("png_truncated")
        if chunk_type not in PNG_DROP_CHUNKS:
            out += data[i:end]
        i = end
        if chunk_type == b"IEND":
            return bytes(out)
    raise MediaRejected("png_truncated")


def strip_webp(data: bytes) -> bytes:
    chunks = bytearray()
    i = 12
    while i + 8 <= len(data):
        chunk_type = data[i : i + 4]
        size = struct.unpack("<I", data[i + 4 : i + 8])[0]
        end = i + 8 + size + (size & 1)
        if chunk_type not in WEBP_DROP_CHUNKS:
            chunks += data[i:end]
        i = end
    return b"RIFF" + struct.pack("<I", len(chunks) + 4) + b"WEBP" + bytes(chunks)


def sanitize_image(data: bytes) -> tuple[bytes, str]:
    if not data:
        raise MediaRejected("empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise MediaRejected("too_large")
    content_type = sniff_type(data)
    if content_type == "image/jpeg":
        return strip_jpeg(data), content_type
    if content_type == "image/png":
        return strip_png(data), content_type
    if content_type == "image/webp":
        return strip_webp(data), content_type
    raise MediaRejected("unsupported_type")


EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def store_private(root: Path, owner_id: str, data: bytes, content_type: str) -> str:
    folder = root / "pets" / owner_id
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{EXTENSIONS[content_type]}"
    (folder / name).write_bytes(data)
    return (Path("pets") / owner_id / name).as_posix()


def resolve_private(root: Path, ref: str) -> Path | None:
    path = (root / ref).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None
