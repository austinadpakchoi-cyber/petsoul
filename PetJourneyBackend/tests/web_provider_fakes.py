"""网页真实供应商测试用的假实现（不触网）。非测试模块。"""

from __future__ import annotations

from app.image_provider.models import GeneratedImage
from app.web_providers import ChatResult, ImageUnavailable, PlaceCandidate, RouteEstimate


class FakeChat:
    available = True
    provider_label = "测试模型"

    def __init__(self, replies=None, error: Exception | None = None) -> None:
        self.replies = list(replies or ["收到啦，我在家晒太阳呢。"])
        self.error = error
        self.calls: list[list[dict]] = []

    def complete(self, messages, *, max_tokens=200, temperature=0.7, json_mode=False) -> ChatResult:
        self.calls.append(messages)
        if self.error:
            raise self.error
        text = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        return ChatResult(text=text, requested_model="fake", effective_model="fake-effective", latency_ms=5)


class FakeGeo:
    def __init__(self, place=None, minutes=8, fail=False) -> None:
        self.place, self.minutes, self.fail = place, minutes, fail
        self.route_calls = 0

    def configured(self, region: str) -> bool:
        return region == "amap"

    def place_near(self, region, lat, lng, **kwargs):
        if self.fail:
            raise RuntimeError("boom")
        return self.place

    known: dict = {}

    def place_in_city(self, region, name, city):
        return self.known.get(name)

    def route(self, region, mode, origin, destination, max_age=None):
        self.route_calls += 1
        return RouteEstimate(provider="amap", mode=mode, duration_seconds=self.minutes * 60 - 20, distance_meters=550,
                             points=[origin, ((origin[0] + destination[0]) / 2, origin[1]), destination])


class FakeIllustrator:
    available = True
    provider_label = "测试生图"

    def __init__(self, fail_reason: str | None = None) -> None:
        self.fail_reason = fail_reason
        self.prompts: list[str] = []

    def render(self, prompt, reference=None, size="2048x2048") -> GeneratedImage:
        self.prompts.append(prompt)
        if self.fail_reason:
            raise ImageUnavailable(self.fail_reason)
        return GeneratedImage(image_bytes=b"\x89PNG\r\n\x1a\nfake", mime_type="image/png", model="fake-seedream", provider="fake", source="url")


REAL_CAFE = PlaceCandidate(provider="amap", place_id="amap:B0TEST", name="真实咖啡店（信德中心）", address="上环干诺道中 168 号", lat=22.2872,
                           lng=114.1522, category="咖啡厅", attribution="地点资料：高德地图")
