"""姿态 2..N 的参考图：把已生效的中性姿态（带 alpha 的 PNG）**压到一块纯中性灰底上**再发。

P 规范 §6-4 的蒙版风险：部分图片编辑接口会把**输入图的透明区当成"要编辑的区域"**；
中转若也这么理解，模型会去"填补"猫周围的透明区，行为不可预期。**这一点没人实测过**，
所以不依赖接口语义：发出去的参考图根本不带 alpha，歧义直接消失。
输出的透明仍由 `background` 参数负责，与参考图透不透明无关。

**灰底不能一律用中灰**（§6-5）：银灰色的猫合成到 `#808080` 上，轮廓和耳朵边缘会和底色糊在一起，
而轮廓、耳形、身体比例正是身份锁要保持的东西。所以在 `#E0E0E0` 与 `#404040` 里取**离主体更远**的那块。

判定口径**按规范写死成整数**（2026-09-24，免得两份实现在分界点上各舍各的）：

    S = Σ a·(2126R + 7152G + 722B)，W = Σ a        （8 位值；16 位图取高字节；不做线性化）
    S < 1,440,000·W  ⇒  #E0E0E0，否则 #404040       （平均亮度 < 144 取浅灰，正好等于 144 取深灰）

与另一份实现互相比对时**比像素、不比字节**：取整方式与 PNG 编码参数都可能不同；灰度选择必须完全相同，像素每通道差 ≤1。

**只处理发出去的那一份**：已存的角色资产一个字节都不动。纯函数、不用模型，同一张参考永远合成出同一张图。
不依赖 Pillow（`requirements.txt` 里没有它）；解码复用 `validate` 的还原函数——**同一套还原逻辑只有一份**。
"""

from __future__ import annotations

import operator
import re
import struct
import zlib

from . import validate

LIGHT, DARK = 0xE0, 0x40
# 分界：平均亮度 144（两块灰的中点）。乘上 10000 是因为 S 里的系数放大了一万倍。
_THRESHOLD = 144 * 10000
_CLEAR = re.compile(rb"\x00+")
_PARTIAL = re.compile(rb"[\x01-\xfe]")


def backdrop(red: bytes, green: bytes, blue: bytes, alpha: bytes) -> int:
    """按规范的整数口径选灰。整张没有主体（alpha 全 0）抛 ValueError——没有东西可比，就不下结论。"""
    weight = sum(alpha)
    if weight == 0:
        raise ValueError("no subject")
    # `map(operator.mul, …)` 让逐像素乘法在 C 里跑；一张 1024×1536 的图三遍下来不到半秒。
    total = (2126 * sum(map(operator.mul, alpha, red)) + 7152 * sum(map(operator.mul, alpha, green))
             + 722 * sum(map(operator.mul, alpha, blue)))
    return LIGHT if total < _THRESHOLD * weight else DARK


def _planes(data: bytes) -> tuple[int, int, bytes, bytes, bytes, bytes]:
    """解出 (宽, 高, R, G, B, A)，每个平面 8 位、按像素顺序。

    只收 `validate` 放行的那几种：灰度＋alpha 或真彩＋alpha，8／16 位，非隔行——中性姿态已经过了那道校验，
    走到这里还解不出来，说明文件在发布之后变了，抛 ValueError 让调用方别发。
    """
    shape = validate._shape(data)
    if isinstance(shape, str):
        raise ValueError(shape)
    width, height, depth, color, _ = shape
    sample = depth // 8
    channels = 2 if color == 4 else 4
    raw = validate._idat(data)
    lanes = [validate._restore_lane(raw, width, height, channels * sample, k * sample, sample) for k in range(channels)]
    if sample == 2:
        lanes = [lane[0::2] for lane in lanes]  # 16 位取高字节：参考图只定长相，8 位足够
    if any(len(lane) != width * height for lane in lanes):
        raise ValueError("short image")
    if color == 4:
        gray, alpha = lanes
        return width, height, gray, gray, gray, alpha
    red, green, blue, alpha = lanes
    return width, height, red, green, blue, alpha


def _over(channel: bytes, alpha: bytes, gray: int) -> bytes:
    """一个通道合成到灰底上：`(a·c + (255−a)·g + 127) // 255`（四舍五入）。

    全透明的整段直接填灰、全不透明的原样保留，只有边缘那些半透明像素逐个算——
    大片背景与主体内部都交给正则在 C 里扫，不逐像素走 Python。
    """
    out = bytearray(channel)
    fill = bytes((gray,))
    for match in _CLEAR.finditer(alpha):
        start, end = match.span()
        out[start:end] = fill * (end - start)
    for match in _PARTIAL.finditer(alpha):
        i = match.start()
        a = alpha[i]
        out[i] = (a * channel[i] + (255 - a) * gray + 127) // 255
    return bytes(out)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def _encode_rgb(width: int, height: int, rgb: bytes) -> bytes:
    """8 位真彩、无 alpha、非隔行；每行过滤类型 0。编码参数固定，同一输入永远得到同一串字节（同一 zlib 版本内）。"""
    stride = width * 3
    raw = b"".join(b"\x00" + rgb[y * stride:(y + 1) * stride] for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return validate.PNG_SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(raw, 6)) + _chunk(b"IEND", b"")


def onto(data: bytes, color: tuple[int, int, int]) -> tuple[int, int, bytes]:
    """带 alpha 的 PNG **按 alpha 合成到指定底色**上，返回 (宽, 高, 8 位 RGB 像素)。

    证件照用（P 证件照规范 §4.1）：透明生成、发布时合成到界面常量（现为 `#DCE8F2`）——底色分毫不差，
    颜色词不进提示词、不会染到毛色；将来换底色只需拿私下保留的透明原图重新合成，不必重画。与上面参考图压灰底同一个合成公式。
    """
    width, height, red, green, blue, alpha = _planes(data)
    rgb = bytearray(width * height * 3)
    rgb[0::3] = _over(red, alpha, color[0])
    rgb[1::3] = _over(green, alpha, color[1])
    rgb[2::3] = _over(blue, alpha, color[2])
    return width, height, bytes(rgb)


def flatten(data: bytes) -> tuple[bytes, int]:
    """带 alpha 的 PNG → 压在中性灰底上的 8 位真彩 PNG（没有 alpha）。返回 (图片字节, 所用灰度 0–255)。

    解不出来、或者整张没有主体，抛 ValueError（`struct.error`／`zlib.error` 也可能从解码里冒出来，调用方一并接住）。
    """
    width, height, red, green, blue, alpha = _planes(data)
    gray = backdrop(red, green, blue, alpha)
    rgb = bytearray(width * height * 3)
    rgb[0::3] = _over(red, alpha, gray)
    rgb[1::3] = _over(green, alpha, gray)
    rgb[2::3] = _over(blue, alpha, gray)
    return _encode_rgb(width, height, bytes(rgb)), gray
