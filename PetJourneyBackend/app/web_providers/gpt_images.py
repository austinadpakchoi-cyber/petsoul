"""GPT image transport for the web worker, sharing its existing meter and failure semantics.

The scene service requests Seedream-sized canvases. Map those explicit canvases to
GPT sizes here, preserving orientation. No retry or fallback to a second provider.

### 透明底是**按调用**请求的，不是全局开关

`WebGPTProvider` 被**两条链路共用**：旅行自拍/手账走 `illustrations.py`，世界角色走 `web_character/`。
`quality` 与 `output_format` 可以无条件追加，因为两条链路都要；**`background` 不行**——
把它塞进 `_post_json` / `_post_multipart` 会让旅行照片和手账页也变成透明底，那些图本来就该有背景。

所以这里持**两个 provider**（不透明 / 透明），`render(..., background=)` 选一个。
`OpenAICompatibleImageProvider.__init__` 只存 settings、每次调用现开 urllib，**构造是零成本的**，
两个实例既不占连接也不共享可变状态（比"调用前改一个实例属性"安全：那种写法多线程下会串）。

### 这个参数是实测过的，不是照文档加的

2026-09-23，P（ada5）在用户授权下做了真实付费对照（各 n=1，用户在自己终端发出）：
带 `background=transparent` 返回 RGBA、60.3% 像素 alpha=0、响应回显 `"background": "transparent"`；
不带则返回 RGB、无 alpha 通道、回显 `"opaque"`。**中转确实透传该参数并生效。**
证据：`data/reviews/character-gpt25-20260923T142932Z/`（`VERDICT-stage1.md`，`SHA256SUMS-stage1` `121377206b6b80fc`）。

**各 n=1**；中转不返回模型字段，上游模型身份无法独立证明；单价未知、账单未核。
"""
from __future__ import annotations

from ..image_provider.models import ImageReference
from ..image_provider.openai import OpenAICompatibleImageProvider
from .images import ImageUnavailable, failure_reason

TRANSPARENT = "transparent"


class WebGPTProvider(OpenAICompatibleImageProvider):
    """在通用适配器之上追加网页端固定要的那几个字段。`background` 为空时一个字都不发。"""

    def __init__(self, settings, *, background: str | None = None) -> None:
        super().__init__(settings)
        self.background = background

    def _extras(self) -> dict[str, str]:
        extra = {"quality": "medium", "output_format": "png"}
        if self.background:
            extra["background"] = self.background
        return extra

    def _post_json(self, path, payload):
        return super()._post_json(path, {**payload, **self._extras()})

    def _post_multipart(self, path, *, fields, files):
        return super()._post_multipart(path, fields={**fields, **self._extras()}, files=files)


class GPTIllustrator:
    available = True
    # 调用方据此判断"拿回来的不透明是**没请求**还是**请求了没给**"——两者处置完全不同
    # （前者改参数/核实中转，后者报能力缺失）。装配把它读进 `CharacterService.transparency_requested`，
    # **不用 isinstance**：换实现时不必回头改判断。
    requests_transparent_background = True

    def __init__(self, settings, meter):
        self._provider = WebGPTProvider(settings)
        self._transparent = WebGPTProvider(settings, background=TRANSPARENT)
        self.meter = meter
        self.provider_label = f"GPT 生图 · {settings.image_model}"

    def render(self, prompt, reference=None, size="2048x2048", background: str | None = None):
        """`background="transparent"` 只由角色链路传；照片链路不传，画面照常有背景。"""
        size = {"2048x2048": "1024x1024", "1440x2560": "1024x1536"}.get(size, size)
        if size not in {"1024x1024", "1024x1536", "1536x1024", "auto"}:
            raise ImageUnavailable("rejected")
        if not self.meter.allow("image"):
            raise ImageUnavailable("daily_cap")
        provider = self._transparent if background == TRANSPARENT else self._provider
        try:
            if reference is None:
                image = provider.generate_image(prompt, size=size)
            else:
                suffix = ".jpg" if reference[1] in {"image/jpeg", "image/jpg"} else ".png"
                refs = [ImageReference(reference[0], reference[1], "pet-reference" + suffix, "pet_identity")]
                image = provider.generate_image_with_references(prompt, references=refs, size=size)
        except Exception as exc:
            self.meter.record("image", False, f"{type(exc).__name__}: {exc}")
            # The common adapter wraps transport exceptions in RuntimeError;
            # preserve a timeout even when the original exception has no text.
            raise ImageUnavailable(failure_reason(exc.__cause__ or exc)) from exc
        self.meter.record("image", True)
        return image
