"""姿态参考图的**压灰底**（`web_character/flatten.py`）。纯单元：不联网、0 次付费调用、不依赖 Pillow。

钉的是规范 §6-5 写死的判定口径与合成结果：

    S = Σ a·(2126R + 7152G + 722B)，W = Σ a；S < 1,440,000·W ⇒ #E0E0E0，否则 #404040（正好等于取深灰）

**与 P 的真图对照不在这里**：那几张图在 P 的证据目录里（`data/` 下，不进仓库），
对照是一次性做的——两张真图的主体亮度与 P 给的值逐位一致（144.945143 / 149.670430），
我的压平结果与 P 自己压的参考逐像素相同（每通道最大差 0）。结果记在本窗口日志。

测试图用本文件里的小编码器现拼，**五种行过滤器都编一遍**：GPT 返回的 PNG 用哪种过滤器不由我们定，
还原错一种，发出去的参考图就是花的。
"""

from __future__ import annotations

import struct
import unittest
import zlib

from app.web_character import flatten, validate

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def _filtered(kind: int, line: bytes, prev: bytes, bpp: int) -> bytes:
    """按 PNG 规范给一行套过滤器（编码方向）。"""
    out = bytearray(len(line))
    for x in range(len(line)):
        left = line[x - bpp] if x >= bpp else 0
        up = prev[x]
        upleft = prev[x - bpp] if x >= bpp else 0
        if kind == 0:
            guess = 0
        elif kind == 1:
            guess = left
        elif kind == 2:
            guess = up
        elif kind == 3:
            guess = (left + up) >> 1
        else:
            p = left + up - upleft
            pa, pb, pc = abs(p - left), abs(p - up), abs(p - upleft)
            guess = left if pa <= pb and pa <= pc else (up if pb <= pc else upleft)
        out[x] = (line[x] - guess) & 0xFF
    return bytes(out)


def png(width: int, height: int, pixel, *, color: int = 6, depth: int = 8, filter_type: int = 0) -> bytes:
    """`pixel(x, y)` 给出各通道的值（8 位 0–255；16 位 0–65535）。颜色类型 6＝真彩＋alpha，4＝灰度＋alpha。"""
    size = depth // 8
    bpp = (4 if color == 6 else 2) * size
    raw, prev = bytearray(), bytes(width * bpp)
    for y in range(height):
        line = b"".join(value.to_bytes(size, "big") for x in range(width) for value in pixel(x, y))
        raw.append(filter_type)
        raw += _filtered(filter_type, line, prev, bpp)
        prev = line
    header = struct.pack(">IIBBBBB", width, height, depth, color, 0, 0, 0)
    return SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(bytes(raw))) + _chunk(b"IEND", b"")


def pixels(flat: bytes) -> list[tuple[int, int, int]]:
    """读回压平结果（8 位真彩、每行过滤类型 0）的全部像素。"""
    width, height, depth, color, _ = validate._header(flat)
    assert (depth, color) == (8, 2)
    raw = validate._idat(flat)
    rows = [raw[y * (width * 3 + 1) + 1:(y + 1) * (width * 3 + 1)] for y in range(height)]
    return [tuple(row[x * 3:x * 3 + 3]) for row in rows for x in range(width)]


def subject(color_inside, *, box=(2, 2, 6, 6), outside=(0, 0, 0, 0)):
    """方框内是主体、框外全透明的一张图的像素函数。"""
    left, top, right, bottom = box
    return lambda x, y: color_inside if left <= x < right and top <= y < bottom else outside


class BackdropChoiceTests(unittest.TestCase):
    def test_a_light_subject_goes_on_the_dark_gray(self) -> None:
        """银灰色的猫压在中灰上，轮廓会和底色糊在一起——所以取离它远的那块。"""
        _, gray = flatten.flatten(png(8, 8, subject((200, 200, 205, 255))))
        self.assertEqual(gray, flatten.DARK)

    def test_a_dark_subject_goes_on_the_light_gray(self) -> None:
        _, gray = flatten.flatten(png(8, 8, subject((40, 35, 30, 255))))
        self.assertEqual(gray, flatten.LIGHT)

    def test_the_boundary_is_decided_in_integers(self) -> None:
        """**正好等于 144 取深灰，143 取浅灰**——规范把口径写死成整数，就是为了两份实现在分界点上不各舍各的。"""
        _, at = flatten.flatten(png(8, 8, subject((144, 144, 144, 255))))
        _, below = flatten.flatten(png(8, 8, subject((143, 143, 143, 255))))
        self.assertEqual((at, below), (flatten.DARK, flatten.LIGHT))

    def test_alpha_weights_the_average(self) -> None:
        """半透明的边缘按它的 alpha 计入：一块几乎透明的白边，拉不动一只深色主体的平均亮度。"""
        def pixel(x, y):
            if 2 <= x < 6 and 2 <= y < 6:
                return (20, 20, 20, 255)
            return (255, 255, 255, 3) if y == 0 else (0, 0, 0, 0)  # 顶上一整行几乎透明的白

        _, gray = flatten.flatten(png(8, 8, pixel))
        self.assertEqual(gray, flatten.LIGHT, "按 alpha 加权是 (16·255·20+8·3·255)/(16·255+8·3)≈21.3，远低于 144")

    def test_no_subject_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            flatten.flatten(png(8, 8, lambda x, y: (0, 0, 0, 0)))


class CompositingTests(unittest.TestCase):
    def test_transparent_becomes_gray_opaque_stays_and_edges_blend(self) -> None:
        """全透明 → 正好是灰底；全不透明 → 原样；半透明 → `(a·c + (255−a)·g + 127) // 255`。"""
        def pixel(x, y):
            if 2 <= x < 6 and 2 <= y < 6:
                return (220, 210, 200, 255)
            return (200, 200, 200, 128) if (x, y) == (0, 0) else (9, 9, 9, 0)  # 透明处的 RGB 是垃圾值，不该漏出来

        flat, gray = flatten.flatten(png(8, 8, pixel))
        got = pixels(flat)

        self.assertEqual(gray, flatten.DARK)
        self.assertEqual(got[3 * 8 + 3], (220, 210, 200), "主体内部原样保留")
        self.assertEqual(got[7 * 8 + 7], (0x40, 0x40, 0x40), "全透明处正好是灰底，透明像素里存的 RGB 不许漏出来")
        self.assertEqual(got[0], ((128 * 200 + 127 * 0x40 + 127) // 255,) * 3, "半透明边缘按 alpha 混合")

    def test_the_output_has_no_alpha_and_the_validator_agrees(self) -> None:
        """整件事的目的：发出去的参考图**根本没有 alpha**，接口把透明区当蒙版的歧义就不存在。"""
        flat, _ = flatten.flatten(png(8, 8, subject((200, 200, 205, 255))))

        _, _, depth, color, _ = validate._header(flat)
        self.assertEqual((depth, color), (8, 2), "8 位真彩，没有 alpha 通道")
        self.assertEqual(validate.inspect(flat, "image/png").reason, validate.NO_ALPHA_CHANNEL)

    def test_the_same_input_always_gives_the_same_bytes(self) -> None:
        data = png(8, 8, subject((200, 200, 205, 255)))
        self.assertEqual(flatten.flatten(data), flatten.flatten(data))


class DecodingTests(unittest.TestCase):
    """解码复用 `validate` 的还原函数；这里证明它对压平需要的每一种输入都还原对了。"""

    @staticmethod
    def _gradient(x, y):
        # 有起伏的像素，才能让 Sub/Average/Paeth 的预测值真的起作用
        inside = 1 <= x < 9 and 1 <= y < 7
        return ((x * 23 + y * 7) % 256, (x * 5 + y * 31) % 256, (x * 13) % 256, 255 if inside else (60 if x == 0 else 0))

    def test_every_row_filter_decodes_to_the_same_picture(self) -> None:
        reference = flatten.flatten(png(10, 8, self._gradient, filter_type=0))
        for kind in (1, 2, 3, 4):
            with self.subTest(filter_type=kind):
                self.assertEqual(flatten.flatten(png(10, 8, self._gradient, filter_type=kind)), reference)

    def test_sixteen_bit_uses_the_high_byte(self) -> None:
        """16 位图取每个样本的高字节再合成（规范写明）。低字节放上噪声，结果仍与 8 位那张一模一样。"""
        eight = flatten.flatten(png(10, 8, self._gradient))
        sixteen = flatten.flatten(png(10, 8, lambda x, y: tuple(v * 256 + (x * 7 + y) % 256 for v in self._gradient(x, y)),
                                      depth=16, filter_type=4))
        self.assertEqual(sixteen, eight)

    def test_gray_with_alpha(self) -> None:
        """颜色类型 4（灰度＋alpha）也在校验的放行范围里，压平时三个通道都取那一个灰度。"""
        flat, gray = flatten.flatten(png(8, 8, subject((30, 255), outside=(0, 0)), color=4))
        self.assertEqual(gray, flatten.LIGHT)
        self.assertEqual(pixels(flat)[3 * 8 + 3], (30, 30, 30))

    def test_what_it_cannot_read_is_refused(self) -> None:
        """没有 alpha 的真彩图、不是 PNG 的字节：一律 ValueError，调用方据此**不发**。"""
        rgb = SIGNATURE + _chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)) + \
            _chunk(b"IDAT", zlib.compress(bytes(14))) + _chunk(b"IEND", b"")
        for data in (rgb, b"not a png"):
            with self.subTest(data=data[:8]):
                with self.assertRaises(ValueError):
                    flatten.flatten(data)


if __name__ == "__main__":
    unittest.main()
