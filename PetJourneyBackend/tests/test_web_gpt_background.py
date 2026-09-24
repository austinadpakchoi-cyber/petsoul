"""GPT 适配器的透明底：**按调用**请求，照片链路不受影响。纯单元，不联网、0 次付费调用。

为什么单独一个文件：`WebGPTProvider` 被**两条链路共用**——旅行自拍/手账走 `illustrations.py`，
世界角色走 `web_character/`。`quality` / `output_format` 可以无条件追加，因为两边都要；
**`background` 不行**：像它们那样塞进 `_post_json` / `_post_multipart`，旅行照片和手账页也会变成透明底，
那些图本来就该有背景。这个文件钉的是"两条链路各拿各的"。

透明参数本身是**实测过的**（P 2026-09-23，用户授权，各 n=1，有对照）：中转透传并生效。
这里不重测那件事，只测"我们发不发、发给谁"。
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.web_providers.gpt_images import TRANSPARENT, GPTIllustrator, WebGPTProvider
from app.web_providers.images import NoIllustrator, SeedreamIllustrator

SETTINGS = SimpleNamespace(image_model="gpt-test", image_api_key="k", image_base_url="http://unused")


class _Meter:
    def allow(self, kind: str) -> bool:
        return True

    def record(self, kind: str, ok: bool, detail: str = "") -> None:
        pass


class _Recorder:
    """替换掉真的 provider：只记是谁被叫了，不发请求。"""

    def __init__(self, label: str) -> None:
        self.label, self.calls = label, []

    def generate_image(self, prompt, *, size):
        self.calls.append(("generate", size))
        return self.label

    def generate_image_with_references(self, prompt, *, references, size):
        self.calls.append(("edit", size))
        return self.label


class BackgroundIsPerCallTests(unittest.TestCase):
    def test_the_default_provider_sends_no_background_at_all(self) -> None:
        """照片链路用的那个：一个字都不多发。**不是发 `opaque`，是根本不发**——不替中转做默认。"""
        extras = WebGPTProvider(SETTINGS)._extras()

        self.assertNotIn("background", extras)
        self.assertEqual(extras, {"quality": "medium", "output_format": "png"})

    def test_the_transparent_provider_sends_it(self) -> None:
        self.assertEqual(WebGPTProvider(SETTINGS, background=TRANSPARENT)._extras()["background"], "transparent")

    def test_render_without_background_goes_to_the_opaque_provider(self) -> None:
        """**这一条是整件事的要害**：照片链路调 `render` 时不传 `background`，必须走不透明那一个。"""
        illustrator = GPTIllustrator(SETTINGS, _Meter())
        illustrator._provider, illustrator._transparent = _Recorder("opaque"), _Recorder("transparent")

        result = illustrator.render("旅行自拍", (b"ref", "image/png"), size="2048x2048")

        self.assertEqual(result, "opaque", "旅行照片不能被顺手变成透明底")
        self.assertEqual(illustrator._transparent.calls, [])

    def test_render_with_transparent_goes_to_the_transparent_provider(self) -> None:
        illustrator = GPTIllustrator(SETTINGS, _Meter())
        illustrator._provider, illustrator._transparent = _Recorder("opaque"), _Recorder("transparent")

        result = illustrator.render("角色立绘", (b"ref", "image/png"), size="1024x1536", background=TRANSPARENT)

        self.assertEqual(result, "transparent")
        self.assertEqual(illustrator._provider.calls, [], "角色那一次不许走不透明那个")

    def test_the_two_providers_are_separate_instances(self) -> None:
        """两个实例而不是"调用前改一个实例的属性"：后者多线程下会串——
        插画线程刚把它改成透明，角色线程还没发，插画那张就被发成了透明底。"""
        illustrator = GPTIllustrator(SETTINGS, _Meter())

        self.assertIsNot(illustrator._provider, illustrator._transparent)
        self.assertIsNone(illustrator._provider.background)
        self.assertEqual(illustrator._transparent.background, TRANSPARENT)


class CapabilityFlagTests(unittest.TestCase):
    """能力标记只在"真的会发出去"时为真。调用方据此分辨"没请求"与"请求了没给"。"""

    def test_gpt_says_it_can(self) -> None:
        self.assertTrue(GPTIllustrator.requests_transparent_background)

    def test_seedream_says_it_cannot(self) -> None:
        """方舟参数表里**没有** `background`（P 只读核实，规范 §6-3）。它收下参数但不发——
        所以标记必须为假。静默丢弃却标为真，会把"接口不支持"误判成"请求了没给"，修错地方。"""
        self.assertFalse(SeedreamIllustrator.requests_transparent_background)

    def test_an_unconfigured_illustrator_says_it_cannot(self) -> None:
        self.assertFalse(NoIllustrator.requests_transparent_background)


if __name__ == "__main__":
    unittest.main()
