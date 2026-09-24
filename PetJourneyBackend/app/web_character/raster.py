"""证件照用的几样像素活：解码、从上方裁正方形、按块缩小、编码。**不依赖 Pillow**（`requirements.txt` 里没有它）。

角色图那边的 `validate` / `flatten` 只收带 alpha 的图；证件照是**不透明**的（要有纯色底），
GPT 回来的通常是 8 位真彩（颜色类型 2），也可能是带着全不透明 alpha 的真彩＋alpha（6）。这里四种都收：

    0 灰度   2 真彩   4 灰度＋alpha   6 真彩＋alpha        8／16 位，非隔行；调色板（3）不收

带 alpha 的按 alpha **压到白底上**再算——证件照本不该有透明区，真有，也不能让透明处漏出存着的垃圾 RGB。
还原逐行过滤器复用 `validate._restore_lane`（**同一套还原只有一份**），编码复用 `flatten._encode_rgb`。
"""

from __future__ import annotations

from . import validate
from .flatten import _encode_rgb

_CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}


def decode(data: bytes) -> tuple[int, int, bytes]:
    """PNG → (宽, 高, 8 位 RGB 字节，按像素排列)。解不出来抛 ValueError（`struct.error`／`zlib.error` 调用方一并接住）。"""
    if not data.startswith(validate.PNG_SIGNATURE):
        raise ValueError(validate.NOT_PNG)
    width, height, depth, color, interlace = validate._header(data)
    if interlace or color not in _CHANNELS or depth not in (8, 16) or width <= 0 or height <= 0:
        raise ValueError(validate.BIT_DEPTH if color in _CHANNELS else validate.PALETTE)
    if width * height > validate.MAX_PIXELS:
        raise ValueError(validate.TOO_LARGE)
    sample = depth // 8
    channels = _CHANNELS[color]
    raw = validate._idat(data)
    lanes = [validate._restore_lane(raw, width, height, channels * sample, k * sample, sample) for k in range(channels)]
    if sample == 2:
        lanes = [lane[0::2] for lane in lanes]  # 16 位取高字节
    if any(len(lane) != width * height for lane in lanes):
        raise ValueError(validate.UNDECODABLE)
    if color in (0, 4):
        lanes = [lanes[0], lanes[0], lanes[0], *lanes[1:]]
    red, green, blue = lanes[:3]
    if len(lanes) == 4:
        alpha = lanes[3]
        red, green, blue = (_over_white(lane, alpha) for lane in (red, green, blue))
    rgb = bytearray(width * height * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = red, green, blue
    return width, height, bytes(rgb)


def _over_white(channel: bytes, alpha: bytes) -> bytes:
    if min(alpha) == 255:
        return channel  # 全不透明（GPT 常见）：原样
    return bytes((a * c + (255 - a) * 255 + 127) // 255 for c, a in zip(channel, alpha))


def top_square(width: int, height: int, rgb: bytes) -> tuple[int, bytes]:
    """从画面**上方**裁一个边长等于宽度的正方形（竖幅证件照的头在上半部）。横幅或方图就取中间那一块。"""
    size = min(width, height)
    left = (width - size) // 2
    stride = width * 3
    rows = [rgb[y * stride + left * 3:y * stride + (left + size) * 3] for y in range(size)]
    return size, b"".join(rows)


def shrink(size: int, rgb: bytes, target: int) -> bytes:
    """正方形按块平均缩到 `target`×`target`。块边界按比例取整，任何边长都能缩，不要求整除。"""
    edges = [size * i // target for i in range(target + 1)]
    stride = size * 3
    out = bytearray(target * target * 3)
    for ty in range(target):
        y0, y1 = edges[ty], max(edges[ty + 1], edges[ty] + 1)
        block_rows = [rgb[y * stride:(y + 1) * stride] for y in range(y0, y1)]
        for tx in range(target):
            x0, x1 = edges[tx], max(edges[tx + 1], edges[tx] + 1)
            count = (y1 - y0) * (x1 - x0)
            base = (ty * target + tx) * 3
            for channel in range(3):
                total = sum(sum(row[x0 * 3 + channel:x1 * 3:3]) for row in block_rows)
                out[base + channel] = (total + count // 2) // count
    return bytes(out)


def avatar(data: bytes, target: int = 256) -> bytes:
    """证件照 → 地图头像小方图（上方正方形，缩到 `target`×`target`，8 位真彩 PNG）。"""
    width, height, rgb = decode(data)
    return avatar_of(width, height, rgb, target)


def avatar_of(width: int, height: int, rgb: bytes, target: int = 256) -> bytes:
    size, square = top_square(width, height, rgb)
    return _encode_rgb(target, target, shrink(size, square, target))


def top_portrait(width: int, height: int, rgb: bytes, ratio: tuple[int, int] = (3, 4)) -> bytes:
    """从画面**上方**裁竖幅 `ratio`（默认 3:4，1024 宽即 1024×1365），编码成 8 位真彩 PNG。原图不够高就原样编码。"""
    rows = min(height, width * ratio[1] // ratio[0])
    return _encode_rgb(width, rows, rgb[:rows * width * 3])


def luma_spread(width: int, height: int, rgb: bytes, samples: int = 4096) -> int:
    """均匀抽样的亮度极差（Rec.709，8 位）：整片单色的图接近 0。用来挡"只画了一块底色"的空图。"""
    total = width * height
    step = max(1, total // samples)
    values = [(2126 * rgb[i * 3] + 7152 * rgb[i * 3 + 1] + 722 * rgb[i * 3 + 2]) // 10000 for i in range(0, total, step)]
    return max(values) - min(values)
