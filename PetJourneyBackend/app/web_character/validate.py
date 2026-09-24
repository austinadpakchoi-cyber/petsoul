"""角色图与证件照校验：能不能解码、**真有没有透明**、主体框在哪、是不是只有一只、落地点在哪。

判据逐条照 P（ada5）的《世界角色导演模式》4.2 实现，见
`docs/coordination/WORLD-CHARACTER-DIRECTOR-SPEC-ada5.md`
（实现时对照的是 277 行那一版，① b3da9e30a4c0b4fa ② 909933bed703901c，**我自己算过，与 P 报的一致**；
这是 P 收到我的回执后修订的那一版，之前的 58fa5b8c 已作废。规范后来又扩充过，2026-09-24 已是 669 行——
这两个指纹只说明当时对照的是哪一版，不是现行版本）。

文件末尾的证件照一节照 P 的《宠物证件照导演规范》§4.2 实现，见
`docs/coordination/ID-PHOTO-DIRECTOR-SPEC-ada5.md`（154 行，00d156686f553897，与 P 日志登记的一致）。
证件照的胸口本来就该碰到底边，**不能照搬角色那套**，所以单独一节、单独的原因码。

为什么自己解 PNG 而不用 Pillow：`requirements.txt` 里**没有** Pillow，
全仓只有 `web_admin/assets.py` 把它包在 `try: from PIL import Image / except ImportError` 里当可选项。
角色发布是**付费调用之后的最后一道闸**，不能是"这套环境刚好装了库才生效"的闸。
这里只用 `zlib` / `struct` / `re`（标准库），一条实现，装没装 Pillow 行为完全一样。

**这条闸存在的理由**：GPT 适配器（`web_providers/gpt_images.py`）自 2026-09-23 起在角色（含姿态）和证件照链路上
请求 `background=transparent`，但**只请求、不验证 alpha**——请求了透明不等于拿到了透明：
中转可能把 RGBA 压平成棋盘格，也可能干脆忽略这个参数（两种的处置不同，见下文棋盘格一节）。
"返回了 PNG" 和 "是一张透明角色" 是两回事——一张白底方块的不透明 PNG 照样是合法 PNG。

只认 PNG：这条链上能带 alpha 的只有它。JPEG 没有 alpha 通道；WebP 的 alpha 要另写一套 VP8L 解码，
本版不做——不做就明说 `not_png`，不默默放行。

### 一处实现上的取巧：只还原需要的那条通道

PNG 的行过滤器（Sub/Up/Average/Paeth）的预测值**全部只引用同一通道**的邻居
（左边 `x-bpp`、正上方 `prev[x]`、左上 `prev[x-bpp]`，`bpp` 正好是一整像素的字节数）。
所以每条通道都能**脱离其它通道单独还原**，四种过滤器都成立。
alpha 判定因此只需还原 1/4 的字节；横向扫描再用 `translate` + `re` 交给 C，不在 Python 里逐像素比。

### 棋盘格检测（`checkerboard_drawn`）：现在可达了，所以现在才写

这个检测器**先前刻意没写**：那时棋盘格分支不可达，给不可达分支写检测器就是死代码。
不可达靠两个条件同时成立——提示词不提透明（否则模型把"透明"当图案画出来），
**且没有真的发出 `background=transparent`**（第二个是 P 指出来的：中转把 RGBA 压平到棋盘底，
只在真的请求了透明之后才可能发生）。当时守卫钉在第二个条件上，翻开那个开关的人会当场看到红。

**2026-09-23 那个开关翻了**：P 在用户授权下实测中转会透传 `background=transparent`，
用户随即批准本链路按调用请求透明底。**分支变为可达，所以检测器现在写，守卫同时退场。**

两种失败的处置完全不同，所以必须分开记：
  - 棋盘格 ⇒ alpha 在上游产出过、被传输压平了 ⇒ **改响应格式／端点**；
  - 纯不透明 ⇒ 参数被忽略 ⇒ **改参数或报能力缺失**。

**检测为什么用平移比较、不用网格分奇偶**：棋盘格的相位不固定（不一定从左上角那个像素对齐）。
按网格分奇偶格，错开半格时两组各含一半深一半浅，均值相等，**一定漏判**。
平移法与相位无关：方格边长为 p 时，**平移 p 必落到对面颜色、平移 2p 必落回同色**，
横竖两个方向都要成立（只有一个方向成立的是条纹，不是棋盘格）。

**只看左上角那一块**：还原底下几行要先把上面所有行还原完（行过滤器是逐行依赖的），
而棋盘格是铺满整个背景的全局图案，左上角有代表性；主体按规范居中、四周留一成空白，那一角通常是背景。
**宁可漏判不可误判**：误判会把一次"参数被忽略"说成"被传输压平"，让人去改错地方；
漏判只是退回到 `opaque_background`，那是更保守的原因码。阈值因此偏严。
"""

from __future__ import annotations

import re
import struct
import zlib
from dataclasses import dataclass

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# 超过这个像素数就不解了：纯 Python 还原一遍有成本，而角色图只有 1024×1536 这一档。
# **不是"太大就放行"**——是如实落 `too_large_to_check`，当作没通过。
MAX_PIXELS = 4 * 1024 * 1024
# 低于这个 alpha 算背景。不取 0：有些编码器会在边缘留 1–2 的噪声，那不是主体。
SUBJECT_ALPHA = 8
MIN_OPAQUE_RATIO, MAX_OPAQUE_RATIO = 0.15, 0.70  # P 4.2 第 4 条
EDGE_MARGIN_RATIO = 0.02  # P 4.2 第 3 条：四边各留 ≥2%
MAIN_BLOB_RATIO = 0.95  # P 4.2 第 5 条：最大连通块占全部不透明像素的比例

NOT_PNG = "not_png"
UNDECODABLE = "undecodable"
INTERLACED = "interlaced_unsupported"
PALETTE = "palette_unsupported"
BIT_DEPTH = "bit_depth_unsupported"
TOO_LARGE = "too_large_to_check"
NO_ALPHA_CHANNEL = "no_alpha_channel"
OPAQUE = "opaque_background"
CHECKERBOARD = "checkerboard_drawn"  # 不透明，而且背景是灰白相间的方格：alpha 在上游有过、被压平了
# 棋盘格探测：只看左上角这么大一块；方格边长的候选；判定阈值（偏严，宁可漏判不可误判）
PROBE = 128
PROBE_PERIODS = (4, 6, 8, 10, 12, 16, 20, 24, 32, 40)
PROBE_FLIP_MIN = 16  # 平移一个方格边长后的平均亮度差：至少这么大才像"换了颜色"
PROBE_SAME_MAX = 3  # 平移两个方格边长后的平均亮度差：至多这么大才像"回到同一颜色"
EMPTY = "empty_subject"
CUT_OFF = "subject_cut_off"
TOO_SMALL = "subject_too_small"
TOO_BIG = "subject_too_large"
MULTIPLE = "multiple_subjects"

_RUN = re.compile(rb"\x01+")
_TABLE = bytes(0 if value < SUBJECT_ALPHA else 1 for value in range(256))


@dataclass(frozen=True, slots=True)
class Verdict:
    """校验结论。`ok` 为假时 `reason` 一定有值，其余字段按当时已经算出多少给多少。"""

    ok: bool
    reason: str | None
    width: int = 0
    height: int = 0
    # 不透明内容的外接框，闭区间像素坐标 (left, top, right, bottom)
    content_box: tuple[int, int, int, int] | None = None
    # 落地点：`content_box` 底边中点（P 4.3），换算成相对宽高的比例，渲染层拿它对齐地面
    anchor: tuple[float, float] | None = None
    # 不透明像素占全图的比例（P 4.3 `opaque_ratio`）：回归时能看出"这一版忽然胖了一圈"
    opaque_ratio: float = 0.0


def _header(data: bytes) -> tuple[int, int, int, int, int]:
    """返回 (宽, 高, 位深, 颜色类型, 隔行)。结构不对抛 ValueError。"""
    # 签名 8 字节，接着是 IHDR 段：长度 4（8..12）、类型 4（12..16）、内容 13（16..29）。
    if len(data) < 33 or data[12:16] != b"IHDR":
        raise ValueError("no IHDR")
    width, height, depth, color, _comp, _filt, interlace = struct.unpack(">IIBBBBB", data[16:29])
    return width, height, depth, color, interlace


def _idat(data: bytes) -> bytes:
    """把所有 IDAT 段拼起来解压。遇到 IEND 停。"""
    parts: list[bytes] = []
    i = len(PNG_SIGNATURE)
    while i + 8 <= len(data):
        (length,) = struct.unpack(">I", data[i : i + 4])
        kind = data[i + 4 : i + 8]
        end = i + 12 + length
        if end > len(data):
            raise ValueError("truncated chunk")
        if kind == b"IDAT":
            parts.append(data[i + 8 : i + 8 + length])
        elif kind == b"IEND":
            break
        i = end
    if not parts:
        raise ValueError("no IDAT")
    return zlib.decompress(b"".join(parts))


def _restore_lane(raw: bytes, width: int, height: int, step: int, offset: int, sample: int) -> bytes:
    """还原**一条通道**。`step` 是整像素字节数，`offset` 是这条通道在像素内的起始字节，`sample` 是它自己的字节数。

    四种过滤器的预测值都只引用同一通道，所以单独还原成立（见模块抬头）。
    """
    stride = width * step
    lane = width * sample
    out = bytearray()
    prev = bytes(lane)
    i = 0
    for _ in range(height):
        if i + 1 + stride > len(raw):
            raise ValueError("short scanline")
        kind = raw[i]
        row = raw[i + 1 : i + 1 + stride]
        line = bytearray(row[offset::step] if sample == 1 else b"".join(row[x : x + sample] for x in range(offset, stride, step)))
        i += 1 + stride
        if kind == 1:
            for x in range(sample, lane):
                line[x] = (line[x] + line[x - sample]) & 0xFF
        elif kind == 2:
            for x in range(lane):
                line[x] = (line[x] + prev[x]) & 0xFF
        elif kind == 3:
            for x in range(lane):
                left = line[x - sample] if x >= sample else 0
                line[x] = (line[x] + ((left + prev[x]) >> 1)) & 0xFF
        elif kind == 4:
            for x in range(lane):
                left = line[x - sample] if x >= sample else 0
                upleft = prev[x - sample] if x >= sample else 0
                up = prev[x]
                guess = left + up - upleft
                dl, du, dul = abs(guess - left), abs(guess - up), abs(guess - upleft)
                pick = left if (dl <= du and dl <= dul) else (up if du <= dul else upleft)
                line[x] = (line[x] + pick) & 0xFF
        elif kind != 0:
            raise ValueError(f"filter {kind}")
        out += line
        prev = bytes(line)
    return bytes(out)


def _runs(alpha: bytes, width: int, height: int) -> list[list[tuple[int, int]]]:
    """逐行取出"算主体"的像素区段 [起, 止)。用 `translate` ＋ 正则交给 C 扫，不逐像素比。"""
    return [[m.span() for m in _RUN.finditer(alpha[y * width : (y + 1) * width].translate(_TABLE))] for y in range(height)]


def _box(rows: list[list[tuple[int, int]]]) -> tuple[int, int, int, int] | None:
    """全部区段的外接框（闭区间）。整幅没有主体像素返回 None。"""
    ys = [y for y, spans in enumerate(rows) if spans]
    if not ys:
        return None
    left = min(span[0] for spans in rows for span in spans)
    right = max(span[1] for spans in rows for span in spans) - 1
    return (left, ys[0], right, ys[-1])


def _largest_blob(rows: list[list[tuple[int, int]]]) -> tuple[int, int]:
    """返回 (最大连通块像素数, 全部主体像素数)。4 连通，按区段做并查集——区段数远少于像素数。

    尾巴、耳朵是通过身体连着的；出现第二块独立区域，多半是多画了物件或第二只动物。
    """
    parent: list[int] = []
    sizes: list[int] = []

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
            sizes[ra] += sizes[rb]
            sizes[rb] = 0

    previous: list[tuple[int, int, int]] = []  # 上一行的 (起, 止, 区段号)
    for spans in rows:
        current: list[tuple[int, int, int]] = []
        for start, stop in spans:
            index = len(parent)
            parent.append(index)
            sizes.append(stop - start)
            for above_start, above_stop, above_index in previous:
                if above_start < stop and start < above_stop:  # 与上一行这个区段有重叠 → 相连
                    union(above_index, index)
            current.append((start, stop, index))
        previous = current
    total = sum(stop - start for spans in rows for start, stop in spans)
    return (max(sizes) if sizes else 0, total)


def _flips(luma: list[int], cols: int, rows: int, p: int, dx: int, dy: int) -> bool:
    """沿 (dx, dy) 方向：平移 p 的平均亮度差够大（换了颜色）、平移 2p 的够小（回到同色）。

    这个判据**与棋盘格的相位无关**——边长为 p 的方格，平移 p 必落到对面格、平移 2p 必落回同色格，
    不管图案从哪个像素开始。按网格分奇偶格的写法在错开半格时两组均值相等，会漏判。
    """
    one = two = count = 0
    for y in range(rows - 2 * p * dy):
        base = y * cols
        for x in range(cols - 2 * p * dx):
            value = luma[base + x]
            one += abs(value - luma[(y + p * dy) * cols + x + p * dx])
            two += abs(value - luma[(y + 2 * p * dy) * cols + x + 2 * p * dx])
            count += 1
    return count > 0 and one / count >= PROBE_FLIP_MIN and two / count <= PROBE_SAME_MAX


def _checkerboard(raw: bytes, width: int, height: int, step: int) -> bool:
    """左上角那一块是不是灰白相间的方格。只支持 8 位 RGB / RGBA；其它格式一律答"不是"。

    **横竖两个方向都要成立**：只有一个方向成立的是条纹，不是棋盘格。
    还原不出来也答"不是"——**解不出来的时候不下强结论**，退回更保守的 `opaque_background`。
    """
    rows, cols = min(height, PROBE), min(width, PROBE)
    try:
        red, green, blue = (_restore_lane(raw, width, rows, step, offset, 1) for offset in (0, 1, 2))
    except (ValueError, struct.error):
        return False
    luma = [(2126 * red[y * width + x] + 7152 * green[y * width + x] + 722 * blue[y * width + x]) // 10000
            for y in range(rows) for x in range(cols)]  # Rec.709 亮度，整数
    for period in PROBE_PERIODS:
        if 2 * period >= min(cols, rows):
            break
        if _flips(luma, cols, rows, period, 1, 0) and _flips(luma, cols, rows, period, 0, 1):
            return True
    return False


def _no_alpha_verdict(data: bytes) -> Verdict:
    """真彩图（颜色类型 2）根本没有 alpha 通道：再看一眼是不是把棋盘格画进去了。

    单独拎出来是为了**带上宽高**——先前这一类直接返回原因码，宽高丢成 0×0，
    真图复核时（P 的 S1-C）看起来像"解不出来"，其实只是没填。
    """
    width, height, depth, color, _ = _header(data)
    if color == 2 and depth == 8 and width * height <= MAX_PIXELS:
        try:
            if _checkerboard(_idat(data), width, height, 3):
                return Verdict(False, CHECKERBOARD, width, height)
        except (ValueError, struct.error, zlib.error):
            pass
    return Verdict(False, NO_ALPHA_CHANNEL, width, height)


def _shape(data: bytes) -> tuple[int, int, int, int, int] | str:
    """读出 (宽, 高, 位深, 颜色类型, 隔行)，或者返回一个原因码字符串表示不该继续。"""
    if not data.startswith(PNG_SIGNATURE):
        return UNDECODABLE
    try:
        width, height, depth, color, interlace = _header(data)
    except (ValueError, struct.error):
        return UNDECODABLE
    if interlace:
        return INTERLACED  # Adam7 要另写一套还原，本版不做，也不默默放行
    if color == 3:
        return PALETTE  # 调色板 + tRNS 也能透明，但要先解调色板；本版不做
    if color in (0, 2):
        return NO_ALPHA_CHANNEL  # 灰度 / 真彩**根本没有 alpha 通道**
    if color not in (4, 6) or depth not in (8, 16):
        return BIT_DEPTH
    if width <= 0 or height <= 0:
        return UNDECODABLE
    if width * height > MAX_PIXELS:
        return TOO_LARGE
    return (width, height, depth, color, interlace)


def inspect(data: bytes, content_type: str) -> Verdict:
    """校验一张角色图。**任何一项不过都返回 `ok=False` 加具体原因码**，不做"大概能用"的放行。"""
    if content_type != "image/png":
        return Verdict(False, NOT_PNG)
    shape = _shape(data)
    if shape == NO_ALPHA_CHANNEL:
        return _no_alpha_verdict(data)
    if isinstance(shape, str):
        return Verdict(False, shape)
    width, height, depth, color, _ = shape
    sample = depth // 8
    step = (2 if color == 4 else 4) * sample
    try:
        raw = _idat(data)
        lane = _restore_lane(raw, width, height, step, step - sample, sample)
    except (ValueError, struct.error, zlib.error):
        return Verdict(False, UNDECODABLE, width, height)
    alpha = lane if sample == 1 else lane[0::2]  # 16 位深取高位字节就够判断有没有、在哪里
    if len(alpha) != width * height:
        return Verdict(False, UNDECODABLE, width, height)
    if min(alpha) > 0:
        # 有 alpha 通道、却连一个全透明像素都没有：P 4.2 第 2 条说的**假透明**。
        # 再分一层：背景是灰白方格 ⇒ alpha 在上游有过、被压平了（改响应格式）；否则是参数被忽略（改参数）。
        if color == 6 and sample == 1 and _checkerboard(raw, width, height, step):
            return Verdict(False, CHECKERBOARD, width, height)
        return Verdict(False, OPAQUE, width, height)
    rows = _runs(alpha, width, height)
    box = _box(rows)
    if box is None:
        return Verdict(False, EMPTY, width, height)
    blob, opaque = _largest_blob(rows)
    ratio = opaque / float(width * height)
    if ratio < MIN_OPAQUE_RATIO:
        return Verdict(False, TOO_SMALL, width, height, box, None, ratio)  # 主体太远/太小
    if ratio > MAX_OPAQUE_RATIO:
        # 不透明占了七成以上：多半是背景没去掉。P 的"透明像素 ≥10%"被这一条覆盖（≤70% ⇒ 透明 ≥30%）。
        return Verdict(False, TOO_BIG, width, height, box, None, ratio)
    margin_x, margin_y = max(1, int(width * EDGE_MARGIN_RATIO)), max(1, int(height * EDGE_MARGIN_RATIO))
    if box[0] < margin_x or box[1] < margin_y or box[2] > width - 1 - margin_x or box[3] > height - 1 - margin_y:
        return Verdict(False, CUT_OFF, width, height, box, None, ratio)  # 贴边 ＝ 身体被裁断
    if blob < opaque * MAIN_BLOB_RATIO:
        return Verdict(False, MULTIPLE, width, height, box, None, ratio)
    anchor = ((box[0] + box[2] + 1) / 2.0 / width, (box[3] + 1) / float(height))
    return Verdict(True, None, width, height, box, anchor, ratio)


# ---- 证件照（CR-6C2B-IDPHOTO）：P《宠物证件照导演规范》§4.2 的 5 条，**不照搬上面角色那套** ----
# 角色要求四边都不触边；证件照的胸口**本来就该**碰到底边，照搬会把每一张合格证件照都判成 `subject_cut_off`。
# 这 5 条是 P 按道理定的门槛，**未经真图验证**，真图出来后可调。
PHOTO_MIN_CLEAR_RATIO = 0.10  # ① 透明像素至少占一成
PHOTO_BOTTOM_RATIO = 0.97  # ② 主体外接框下沿到画面高度的 97%：胸口到底
PHOTO_HEADROOM = (0.03, 0.20)  # ③ 外接框上沿在画面高度的 3%–20%：头顶留空
PHOTO_NOT_TO_BOTTOM = "photo_not_to_bottom"  # 胸口没到底边：拍成了全身或半身，不是头和上半身
PHOTO_HEADROOM_OFF = "photo_headroom_off"  # 头顶留空不在 3%–20%：太挤或太空
PHOTO_HEAD_CUT_OFF = "photo_head_cut_off"  # 上方正方形里主体贴到左右边：做头像时耳朵会被裁掉
# 不透明备选路线（适配器不请求透明时）自己的三条，判定在 `id_photo.py`（要用 `raster` 解真彩图）
PHOTO_TOO_SMALL = "photo_too_small"
PHOTO_WRONG_SHAPE = "photo_wrong_shape"
PHOTO_BLANK = "photo_blank"


def inspect_id_photo(data: bytes, content_type: str) -> Verdict:
    """证件照（透明路线）的校验：① 真透明 ② 胸口到底 ③ 头顶留空 ④ 头部没被裁 ⑤ 单一主体。不过就给具体原因码。"""
    if content_type != "image/png":
        return Verdict(False, NOT_PNG)
    shape = _shape(data)
    if shape == NO_ALPHA_CHANNEL:
        return _no_alpha_verdict(data)
    if isinstance(shape, str):
        return Verdict(False, shape)
    width, height, depth, color, _ = shape
    sample = depth // 8
    step = (2 if color == 4 else 4) * sample
    try:
        raw = _idat(data)
        lane = _restore_lane(raw, width, height, step, step - sample, sample)
    except (ValueError, struct.error, zlib.error):
        return Verdict(False, UNDECODABLE, width, height)
    alpha = lane if sample == 1 else lane[0::2]
    if len(alpha) != width * height:
        return Verdict(False, UNDECODABLE, width, height)
    rows = _runs(alpha, width, height)
    opaque = sum(stop - start for spans in rows for start, stop in spans)
    clear = width * height - opaque
    if min(alpha) > 0 or clear < width * height * PHOTO_MIN_CLEAR_RATIO:  # ① 假透明：背景没抠掉
        if color == 6 and sample == 1 and _checkerboard(raw, width, height, step):
            return Verdict(False, CHECKERBOARD, width, height)
        return Verdict(False, OPAQUE, width, height)
    box = _box(rows)
    if box is None:
        return Verdict(False, EMPTY, width, height)
    ratio = opaque / float(width * height)
    if box[3] + 1 < height * PHOTO_BOTTOM_RATIO:  # ②
        return Verdict(False, PHOTO_NOT_TO_BOTTOM, width, height, box, None, ratio)
    if not PHOTO_HEADROOM[0] <= box[1] / height <= PHOTO_HEADROOM[1]:  # ③
        return Verdict(False, PHOTO_HEADROOM_OFF, width, height, box, None, ratio)
    head = _box(rows[:min(width, height)])  # ④ 只看上方正方形那一截：头像就从这里裁
    margin = max(1, int(width * EDGE_MARGIN_RATIO))
    if head is not None and (head[0] < margin or head[2] > width - 1 - margin):
        return Verdict(False, PHOTO_HEAD_CUT_OFF, width, height, box, None, ratio)
    blob, total = _largest_blob(rows)  # ⑤
    if blob < total * MAIN_BLOB_RATIO:
        return Verdict(False, MULTIPLE, width, height, box, None, ratio)
    return Verdict(True, None, width, height, box, None, ratio)
