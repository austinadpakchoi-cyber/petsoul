"""角色链路用例的**假供应商**与 PNG 构造工具。非测试模块。

**这里的一切都是假的，明确标注**（CR-PLAYER-CHARACTER-01：「测试阶段注入假供应商且明确标注」）：

  - `FakeCharacterIllustrator` **不联网、不产生任何付费调用**，返回的是本文件用 `zlib` 拼出来的 PNG；
  - 它返回的透明 PNG **不能当作"真实 GPT 链路能产出透明角色"的证据**。
    `gpt_images.py` 现在按调用发 `background=transparent`（2026-09-23 起），中转透传是 P 在用户授权下实测过的（各 n=1）；
    但**正式产品链路还没有真实产出过一张透明角色**。假供应商证明的只是"校验与发布这条闸接对了"。

`transparent_png` 刻意不依赖 Pillow：`requirements.txt` 里没有它，
而被测的 `web_character/validate.py` 也不依赖它——测试与实现用同一条前提，不借环境里碰巧装了什么。
"""

from __future__ import annotations

import struct
import zlib

from app.image_provider.models import GeneratedImage
from app.web_providers import ImageUnavailable

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def rgba_png(width: int, height: int, filled, *, filter_type: int = 0) -> bytes:
    """按 `filled(x, y) -> bool` 画一张 8 位 RGBA PNG。为真的像素不透明，其余 alpha 全 0。

    `filter_type` 只影响编码方式，不影响画面——用来证明校验对 Up 这类行过滤器也还原得对。
    """
    raw = bytearray()
    previous = bytearray(width * 4)
    for y in range(height):
        line = bytearray()
        for x in range(width):
            line += bytes((120, 90, 60, 255)) if filled(x, y) else bytes(4)
        raw.append(filter_type)
        raw += bytes((line[i] - previous[i]) & 0xFF for i in range(len(line))) if filter_type == 2 else line
        previous = line
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return PNG_SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(bytes(raw))) + _chunk(b"IEND", b"")


def transparent_png(width: int = 64, height: int = 96, **kwargs) -> bytes:
    """一张能通过全部校验的假角色图：居中的主体、四边留白、单一连通块、真有透明像素。"""
    left, top, right, bottom = 10, 10, width - 10, height - 10
    return rgba_png(width, height, lambda x, y: left <= x < right and top <= y < bottom, **kwargs)


def opaque_png(width: int = 64, height: int = 96) -> bytes:
    """有 alpha 通道、却一个透明像素都没有——**"PNG 不等于透明"的那一类**。"""
    return rgba_png(width, height, lambda x, y: True)


def two_subjects_png(width: int = 64, height: int = 96) -> bytes:
    """两块互不相连的不透明区域：多画了一只动物或一个物件。"""
    def filled(x: int, y: int) -> bool:
        return (8 <= x < 28 and 10 <= y < 60) or (36 <= x < 56 and 10 <= y < 60)

    return rgba_png(width, height, filled)


def rgb_png(width: int = 64, height: int = 96, color_of=None) -> bytes:
    """真彩 PNG，**根本没有 alpha 通道**。`color_of(x, y) -> (r, g, b)`，不给就是一块均匀的暖灰。"""
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw += (b"".join(bytes(color_of(x, y)) for x in range(width)) if color_of else bytes((200, 180, 160)) * width)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return PNG_SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(bytes(raw))) + _chunk(b"IEND", b"")


def checker(period: int, shift_x: int = 0, shift_y: int = 0):
    """灰白相间的方格（204 / 255）：模型把"透明"当图案画出来、或中转把 RGBA 压平时长这样。
    `shift_*` 让图案**不从左上角那个像素对齐**——相位不固定是真实情况，检测器必须不怕这个。"""
    def color_of(x: int, y: int) -> tuple[int, int, int]:
        light = ((x + shift_x) // period + (y + shift_y) // period) % 2
        return (255, 255, 255) if light else (204, 204, 204)
    return color_of


class FakeCharacterIllustrator:
    """**假的**生图供应商：不联网、不计费。`images` 按调用次序取，用完沿用最后一张。

    `requests_transparent_background` 默认**假**——和真实协议一样，不声明就是不支持。
    要测"请求了透明"那一路，显式传 `transparent=True`。
    """

    available = True
    provider_label = "测试生图（假）"

    def __init__(self, images=None, fail_reason: str | None = None, *, transparent: bool = False) -> None:
        self.images = list(images) if images else [transparent_png()]
        self.fail_reason = fail_reason
        self.requests_transparent_background = transparent
        self.prompts: list[str] = []
        self.sizes: list[str] = []
        self.references: list[tuple[bytes, str] | None] = []
        self.backgrounds: list[str | None] = []

    @property
    def calls(self) -> int:
        return len(self.prompts)

    def render(self, prompt, reference=None, size="2048x2048", background=None) -> GeneratedImage:
        self.prompts.append(prompt)
        self.sizes.append(size)
        self.references.append(reference)
        self.backgrounds.append(background)
        if self.fail_reason:
            raise ImageUnavailable(self.fail_reason)
        data = self.images[min(len(self.prompts) - 1, len(self.images) - 1)]
        return GeneratedImage(image_bytes=data, mime_type="image/png", model="fake-character", provider="fake", source="b64")
