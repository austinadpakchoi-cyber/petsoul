"""网页生图（服务端，复用既有 Seedream 生图适配器）：冒险照片、明信片自拍。计量、上限与失败降级在这里统一处理。

网页使用 Seedream 4.5（PETJOURNEY_WEB_IMAGE_MODEL），它要求每张图至少约 369 万像素，默认 2048x2048。
供应商默认会加“AI生成”水印，这里不关闭（合规标识）；页面另外标注“AI 生成”。
"""

from __future__ import annotations

from typing import Protocol

from ..image_provider.models import GeneratedImage, ImageReference
from .meter import ProviderMeter


class ImageUnavailable(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# 超时与传输中断：请求很可能已经被受理并计费，所以既不能当作"没发出"，也不能盲目自动重试（包 A 的 CR-A3）。
UNKNOWN_MARKERS = ("timeout", "timedout", "remotedisconnected", "incompleteread", "connectionreset", "chunkedencoding")
# 这些调用阶段跑到了，说明供应商的响应已经回来、生成多半已经受理并计费：
# 之后再失败（响应结构不对、base64 解不开、取图失败）都不能算作"生成失败"，更不能自动重发。
ACCEPTED_STAGES = frozenset({"_extract_image", "_download_image"})
# 确定连都没连上（连接被拒、域名解析不了）：确定没受理，过一会儿重试是合理的。
# 这里**不含 SSL**：SSL 错误也可能发生在请求发出之后的读取阶段，那种情况可能已经受理，按结果不明处理。
UNREACHABLE_MARKERS = ("connectionrefused", "nameorservicenotknown", "nodenamenorservname",
                       "getaddrinfofailed", "temporaryfailureinnameresolution", "nosuchhost", "networkisunreachable")


def call_stage(exc: BaseException) -> str | None:
    """异常是在哪一步抛出来的。'accepted'＝响应已经回来、生成已受理，之后（解析、解码、取图）才失败。

    顺着 __cause__ / __context__ 看调用栈里的函数名；适配器改名时这里认不出来，会落到下面的保守默认值。
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        frame = current.__traceback__
        while frame is not None:
            if frame.tb_frame.f_code.co_name in ACCEPTED_STAGES:
                return "accepted"
            frame = frame.tb_next
        current = current.__cause__ or current.__context__
    return None


def http_status(exc: BaseException) -> int | None:
    """异常链里带的 HTTP 状态码（适配器把 HTTPError 包成 RuntimeError，原异常在 __cause__ 上）。按码判断，不看文案。"""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        code = getattr(current, "code", None)
        if isinstance(code, int) and 100 <= code < 600:
            return code
        current = current.__cause__ or current.__context__
    return None


def failure_reason(exc: BaseException) -> str:
    """按**调用阶段**与证据判断**本地记账口径**（不是对供应商实际计费的判定，真实费用一律按"未验证"对待）。
    四种取值分别是"本地要不要按可能计费记账"与"该不该自动重试"的组合：

    - not_configured：没有密钥，根本没发出——释放本地预占，重试也没用；
    - rejected：供应商当场拒绝（4xx：参数、认证、配置）——确定没受理，但**重试同一请求同样会被拒**，所以不自动重试；
    - provider_error：连都没连上，或被限流（429）——确定没受理，过一会儿自动重试是合理的；
    - timeout：发出去了没等到响应（含 408）——结果不明，不自动重发；
    - unconfirmed：响应已经回来、生成已受理之后才失败，或 5xx、或认不出来的异常——结果不明，不自动重发。

    认不出来的阶段一律按结果不明：宁可让主人点一次"重画"，也不要替他自动再发一次可能已被受理的请求。
    """
    if call_stage(exc) == "accepted":
        return "unconfirmed"
    status = http_status(exc)
    if status is not None:
        if status == 408:  # 明确按状态码判，不依赖错误文案里恰好有 timeout
            return "timeout"
        if status == 429:
            return "provider_error"
        return "rejected" if 400 <= status < 500 else "unconfirmed"
    if isinstance(exc, TimeoutError):
        return "timeout"
    text = f"{type(exc).__name__} {exc}".lower().replace("_", "").replace(" ", "")
    if any(marker in text for marker in UNKNOWN_MARKERS):
        return "timeout"
    if "apikeyisnotconfigured" in text:
        return "not_configured"
    if any(marker in text for marker in UNREACHABLE_MARKERS):
        return "provider_error"
    return "unconfirmed"


class Illustrator(Protocol):
    """`background` 是**可选的、按调用传的**：只有世界角色要透明底，旅行自拍与手账页照常有背景。

    `requests_transparent_background` 是能力标记：实现**真的会把这个参数发出去**才为真。
    调用方据此分辨"拿回来的不透明是**没请求**还是**请求了没给**"——两者处置完全不同
    （前者改参数或核实中转，后者报能力缺失）。**默认假**：不声明就是不支持，不猜。
    """

    available: bool
    provider_label: str
    requests_transparent_background: bool

    def render(self, prompt: str, reference: tuple[bytes, str] | None = None, size: str = "2048x2048",
               background: str | None = None) -> GeneratedImage: ...


class NoIllustrator:
    available = False
    provider_label = "未配置"
    requests_transparent_background = False

    def render(self, prompt: str, reference: tuple[bytes, str] | None = None, size: str = "2048x2048",
               background: str | None = None) -> GeneratedImage:
        raise ImageUnavailable("not_configured")


class SeedreamIllustrator:
    available = True
    provider_label = "火山方舟 Seedream"
    # 方舟的参数表里**没有** `background`（P 2026-09-23 只读核实，规范 §6-3）。
    # 所以这里收下这个参数**但不发出去**，并如实标记为假——
    # 静默丢弃且标记为真，会让调用方把"接口不支持"误判成"请求了没给"，修错地方。
    requests_transparent_background = False

    def __init__(self, provider, meter: ProviderMeter) -> None:  # provider: DoubaoSeedreamImageProvider
        self._provider = provider
        self.meter = meter

    def render(self, prompt: str, reference: tuple[bytes, str] | None = None, size: str = "2048x2048",
               background: str | None = None) -> GeneratedImage:
        if not self.meter.allow("image"):
            raise ImageUnavailable("daily_cap")
        refs = [ImageReference(image_bytes=reference[0], mime_type=reference[1], filename="pet-reference", role="pet_identity")] if reference else []
        try:
            image = self._provider.generate_image_with_references(prompt, references=refs, size=size)
        except Exception as exc:  # noqa: BLE001 - 适配器内部已脱敏；这里只记类型与摘要
            self.meter.record("image", False, f"{type(exc).__name__}: {exc}")
            raise ImageUnavailable(failure_reason(exc)) from exc
        self.meter.record("image", True)
        return image
