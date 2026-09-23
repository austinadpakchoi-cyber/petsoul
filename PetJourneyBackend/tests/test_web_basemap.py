"""网页底图（高德静态地图代理）：范围与缩放规划、缓存复用、上限与失败降级、接口鉴权（假下载函数，不触网）。"""

from __future__ import annotations

import json
import unittest
from urllib import parse

from app.web_providers import BasemapService, WebProviders
from app.web_providers.basemap import PAD, in_amap_region, latlng_of, plan_basemap, world_px
from app.web_providers.meter import ProviderMeter
from web_base import WebPlatformTestBase

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
HOME = (22.2819, 114.1581)
CAFE = (22.2855, 114.1577)
MACAU = (22.1935, 113.5405)
TOKYO = (35.6812, 139.7707)


class FakeFetch:
    def __init__(self, content_type: str = "image/png;charset=UTF-8", body: bytes = PNG, fail: Exception | None = None) -> None:
        self.content_type, self.body, self.fail = content_type, body, fail
        self.urls: list[str] = []

    def __call__(self, url: str, timeout: float) -> tuple[str, bytes]:
        self.urls.append(url)
        if self.fail is not None:
            raise self.fail
        return self.content_type, self.body


def bbox(*points: tuple[float, float]) -> dict[str, float]:
    lats, lngs = [p[0] for p in points], [p[1] for p in points]
    return {"south": min(lats), "west": min(lngs), "north": max(lats), "east": max(lngs)}


class BasemapPlanTests(unittest.TestCase):
    def test_walk_route_gets_street_level_zoom_and_fits_with_padding(self) -> None:
        box = bbox(HOME, CAFE)
        plan = plan_basemap(**box, width=360, height=420)
        self.assertIsNotNone(plan)
        self.assertGreaterEqual(plan.zoom, 16)
        self.assertEqual((plan.width, plan.height), (352, 416))
        x0, y0 = world_px(box["north"], box["west"], plan.zoom)
        x1, y1 = world_px(box["south"], box["east"], plan.zoom)
        for x, y in ((x0, y0), (x1, y1)):
            self.assertGreaterEqual(x - (plan.center_x - plan.width / 2), PAD)
            self.assertLessEqual(x - (plan.center_x - plan.width / 2), plan.width - PAD)
            self.assertGreaterEqual(y - (plan.center_y - plan.height / 2), PAD)
            self.assertLessEqual(y - (plan.center_y - plan.height / 2), plan.height - PAD)

    def test_ferry_route_zooms_out_and_nearby_requests_share_one_image(self) -> None:
        box = bbox(HOME, MACAU)
        plan = plan_basemap(**box, width=360, height=420)
        self.assertLess(plan.zoom, 12)
        nudged = plan_basemap(**{k: v + 0.0003 for k, v in box.items()}, width=366, height=417)
        self.assertEqual(plan.basemap_id, nudged.basemap_id, "几像素的差别复用同一张图")

    def test_projection_round_trip_and_region(self) -> None:
        x, y = world_px(*CAFE, 16)
        lat, lng = latlng_of(x, y, 16)
        self.assertAlmostEqual(lat, CAFE[0], places=6)
        self.assertAlmostEqual(lng, CAFE[1], places=6)
        self.assertTrue(in_amap_region(**bbox(HOME, MACAU)))
        self.assertFalse(in_amap_region(**bbox(HOME, TOKYO)), "东京不混用高德底图")


class BasemapApiTests(WebPlatformTestBase):
    def install(self, fetch: FakeFetch, *, cap: int = 200, per_user: int = 40) -> BasemapService:
        meter = ProviderMeter(self.app.state.storage, {"amap_static": cap}, secrets=["amap-secret-key"])
        service = BasemapService(self.app.state.storage, self.settings.web_private_media_dir, meter, amap_key="amap-secret-key", timeout=1,
                                 fetch=fetch, per_user_daily=per_user)
        self.web.providers = WebProviders(enabled=True, chat=self.web.providers.chat, geo=None, illustrator=self.web.providers.illustrator,
                                          meter=meter, basemap=service)
        return service

    def query(self, user, points=(HOME, CAFE), width=360, height=420):
        return user.get("/map/basemap?" + parse.urlencode({**bbox(*points), "width": width, "height": height}))

    def test_disabled_providers_report_not_configured(self) -> None:
        body = self.query(self.user("bm-off")).json()
        self.assertEqual(body, {**body, "available": False, "reason": "not_configured", "image_url": None})

    def test_first_request_downloads_then_cache_serves_everyone(self) -> None:
        fetch = FakeFetch()
        self.install(fetch)
        alice, bob = self.user("bm-alice"), self.user("bm-bob")
        first = self.query(alice)
        self.assertEqual(first.status_code, 200, first.text)
        body = first.json()
        self.assertTrue(body["available"])
        self.assertEqual(body["provider"], "amap")
        self.assertEqual(body["attribution"], "底图：高德地图")
        self.assertEqual((body["width"], body["height"]), (352, 416))
        self.assertIsNotNone(body["expires_at"])
        sent = parse.parse_qs(parse.urlparse(fetch.urls[0]).query)
        self.assertEqual(sent["scale"], ["2"])
        self.assertEqual(sent["size"], ["352*416"])
        glng, glat = map(float, sent["location"][0].split(","))
        self.assertGreater(glng - body["center"]["lng"], 0.003, "请求高德时中心已转为 GCJ-02")
        self.assertEqual(self.query(bob).json()["image_url"], body["image_url"])
        self.assertEqual(len(fetch.urls), 1, "同一张图只下载一次")
        image = bob.get(body["image_url"].removeprefix("/api/v1/web"))
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.headers["content-type"], "image/png")
        self.assertEqual(image.content, PNG)

    def test_outside_region_and_invalid_bounds(self) -> None:
        fetch = FakeFetch()
        self.install(fetch)
        user = self.user("bm-tokyo")
        self.assertEqual(self.query(user, points=(HOME, TOKYO)).json()["reason"], "outside_region")
        bad = user.get("/map/basemap?" + parse.urlencode({"south": 23, "north": 22, "west": 114, "east": 115, "width": 300, "height": 300}))
        self.assert_envelope(bad, 422, "VALIDATION_FAILED")
        self.assertEqual(fetch.urls, [])

    def test_caps_and_upstream_errors_degrade_without_leaking_key(self) -> None:
        self.install(FakeFetch(content_type="application/json", body=json.dumps({"status": "0", "info": "INVALID_USER_KEY"}).encode()))
        user = self.user("bm-fail")
        self.assertEqual(self.query(user).json()["reason"], "upstream_error")
        usage = self.web.providers.meter.snapshot()["amap_static"]
        self.assertEqual((usage["calls"], usage["failures"]), (1, 1))
        self.install(FakeFetch(fail=OSError("timed out for key=amap-secret-key")))
        self.assertEqual(self.query(user, points=(HOME, MACAU)).json()["reason"], "upstream_error")
        with self.app.state.storage.connect() as conn:
            errors = [r["last_error"] for r in conn.execute("SELECT last_error FROM web_provider_usage").fetchall()]
        self.assertFalse(any("amap-secret-key" in (e or "") for e in errors))
        self.install(FakeFetch(), cap=0)
        self.assertEqual(self.query(user).json()["reason"], "daily_cap")
        self.install(FakeFetch(), per_user=1)
        self.assertTrue(self.query(user).json()["available"])
        self.assertEqual(self.query(user, points=(HOME, MACAU)).json()["reason"], "user_limit")

    def test_image_requires_login_and_expired_images_are_gone(self) -> None:
        self.install(FakeFetch())
        user = self.user("bm-auth")
        url = self.query(user).json()["image_url"].removeprefix("/api/v1/web")
        self.assert_envelope(self.client.get("/api/v1/web" + url), 401, "AUTH_REQUIRED")
        self.assert_envelope(user.get("/media/basemaps/..%2Fsecrets"), 404, "NOT_FOUND")
        with self.app.state.storage.connect() as conn:
            conn.execute("UPDATE web_basemap_cache SET expires_at = '2000-01-01T00:00:00+00:00'")
        self.assert_envelope(user.get(url), 404, "NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
