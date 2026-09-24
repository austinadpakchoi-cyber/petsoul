"""地图底图配置与高德安全代理（CR-6C2B-MAP W0）。

**全程不触网**：代理的出站请求走 `app.state.amap_fetch` 注入的替身（实现里那一行
`getattr(request_.app.state, "amap_fetch", None) or _http_fetch` 就是为此留的）。
**用的密钥是本文件当场编的假串**，不读也不打印 `data/secrets/web-providers.env`。

这里钉四件事，前两件是产品形状，后两件是安全边界：
  ① 没配 JS Key 时如实不可用，且**不给半套参数**；
  ② 配了就给 js_key ＋ 同源 service_host；
  ③ **放行名单之外一律 403**——服务类接口不能经代理被浏览器调用；
  ④ **安全密钥只往出站方向走**：补进转发 URL，但不出现在任何响应体里。
"""

from __future__ import annotations

import unittest

from web_base import WebPlatformTestBase

FAKE_JS_KEY = "js-key-for-test-0000"
FAKE_SECURITY_CODE = "security-code-for-test-1111"


class MapW0TestBase(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.sent: list[str] = []

        def fake_fetch(url: str) -> tuple[str, bytes]:
            self.sent.append(url)
            return "application/json", b'{"status":"1","info":"OK","infocode":"10000"}'

        self.app.state.amap_fetch = fake_fetch

    def configure(self, *, js_key: str | None = FAKE_JS_KEY, code: str | None = FAKE_SECURITY_CODE) -> None:
        """把两把 Key 装上。**先读后写**：属性不存在就当场 AttributeError，而不是静默挂一个新属性。"""
        assert hasattr(self.app.state.settings, "amap_js_key"), "config 里没有 amap_js_key 字段"
        assert hasattr(self.app.state.settings, "amap_js_security_code"), "config 里没有 amap_js_security_code 字段"
        self.app.state.settings.amap_js_key = js_key
        self.app.state.settings.amap_js_security_code = code

    def config_body(self) -> dict:
        response = self.client.get("/api/v1/web/map/config")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()


class MapConfigTests(MapW0TestBase):
    def test_without_a_js_key_it_says_so_and_gives_no_half_setup(self) -> None:
        """没配就整体不可用：给了 js_key 却没 service_host（或反之），前端会以为能画、实际画不出来。"""
        self.configure(js_key=None, code=None)
        body = self.config_body()
        self.assertFalse(body["available"])
        self.assertIsNone(body["js_key"])
        self.assertIsNone(body["service_host"])
        self.assertEqual(body["unavailable_reason"], "not_configured")
        self.assertTrue(body["style"] and body["style_dark"], "样式名是常量，不可用时也照常给")

    def test_with_a_js_key_it_gives_the_key_and_a_same_origin_service_host(self) -> None:
        self.configure()
        body = self.config_body()
        self.assertTrue(body["available"])
        self.assertEqual(body["js_key"], FAKE_JS_KEY)
        self.assertEqual(body["service_host"], "/_AMapService", "同源相对路径：不猜协议与端口")
        self.assertEqual(body["provider"], "amap")
        self.assertFalse(body["overseas_tiles"], "这把 Web 端 Key 没有境外详细瓦片（6c2b 实测）")
        self.assertIsNone(body["unavailable_reason"])

    def test_the_security_code_never_appears_in_the_config_response(self) -> None:
        """**安全边界**：配置接口是公开读的，安全密钥一旦混进去就等于公开了它。"""
        self.configure()
        raw = self.client.get("/api/v1/web/map/config").text
        self.assertNotIn(FAKE_SECURITY_CODE, raw)
        self.assertNotIn("security", raw.lower(), "连字段名都不该出现，免得下一个人以为这里可以放")

    def test_it_is_public_so_a_visitor_can_draw_the_map(self) -> None:
        """访客页也要画图：不带任何会话照样 200。"""
        self.configure()
        self.assertEqual(self.client.get("/api/v1/web/map/config").status_code, 200)


class AMapServiceProxyTests(MapW0TestBase):
    def test_a_whitelisted_render_path_is_forwarded_with_the_security_code(self) -> None:
        """放行名单内：转发到对应上游，并**在出站方向**补上安全密钥。"""
        self.configure()
        response = self.client.get("/_AMapService/v3/log/init", params={"key": FAKE_JS_KEY, "type": "0"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.sent), 1, "一次请求只该向上游发一次")
        url = self.sent[0]
        self.assertTrue(url.startswith("https://restapi.amap.com/v3/log/init?"), url)
        self.assertIn(f"jscode={FAKE_SECURITY_CODE}", url, "安全密钥要补进转发的查询串")
        self.assertIn(f"key={FAKE_JS_KEY}", url, "调用方原有的查询参数要原样带过去")
        self.assertNotIn(FAKE_SECURITY_CODE, response.text, "但它不能出现在回给浏览器的响应里")

    def test_the_script_list_is_a_subset_of_the_whitelist_and_is_exactly_this(self) -> None:
        """`SCRIPT_TARGETS` 与 `ALLOWED_TARGETS` 这对清单**此前没有任何东西看着**（Q 核出：
        `SCRIPT_TARGETS` 全仓只在实现里出现两次，`tests/` 零命中）。

        **两个方向的风险不对称，危险的是第二个**：
        · 加一个**不在白名单**的路径 → 死代码，无害；
        · 加一个**白名单内的 JSON 端点** → 那份 JSON 会以 `application/javascript` 送出去，
          **而 `nosniff` 恰恰不再保护它**——`nosniff` 防的是「浏览器猜类型」，
          **不防「服务端声明了错类型」**。

        所以第二条写成**白名单式而不是黑名单式**：加新脚本端点时必须同时改这条用例，
        **等于强迫写的人再确认一次「它真的是 `<script src>` 取的吗」**。
        """
        from app.routers.amap_service import ALLOWED_TARGETS, SCRIPT_TARGETS
        self.assertTrue(SCRIPT_TARGETS <= set(ALLOWED_TARGETS),
                        f"脚本端点必须在放行名单里：{sorted(SCRIPT_TARGETS - set(ALLOWED_TARGETS))}")
        self.assertEqual(SCRIPT_TARGETS, {"v3/log/init"},
                         "改这一行之前先回答：新加的那个端点真的是 <script src=...> 取的吗？"
                         "把一个 JSON 端点列进来，等于用 application/javascript 把它送出去")

    def test_a_script_loaded_endpoint_comes_back_as_javascript(self) -> None:
        """`v3/log/init` 是高德 JS 用 `<script src=...>` 取的，**必须按脚本类型回**。

        按上游的 JSON MIME ＋ `X-Content-Type-Options: nosniff` 返回，浏览器会**拒绝执行**它
        （6c2b 实测：每次打开地图控制台都有一条）。**`nosniff` 一个字都不去掉**——
        那是防 MIME 混淆的安全头；改的是给这个端点一个对的类型。

        **这条专门用来区分两种实现**：改回「一律用上游类型」它必红。
        """
        self.configure()
        response = self.client.get("/_AMapService/v3/log/init", params={"key": FAKE_JS_KEY})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("javascript", response.headers["content-type"],
                      "脚本加载的端点回 JSON 类型 → 浏览器拒绝执行")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff",
                         "**安全头不能为了让它能执行而去掉**")

    def test_a_fetched_endpoint_keeps_the_upstream_type(self) -> None:
        """反向对照：**其余端点是 fetch 取的，照旧用上游类型**——不要把所有端点都当脚本。

        没有这一条，「一律回 javascript」也能让上面那条绿，**而那是把 JSON 当脚本执行**。
        """
        self.configure()
        response = self.client.get("/_AMapService/v4/map/styles", params={"style": "x"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("javascript", response.headers["content-type"],
                         "样式是 fetch 取的，不该被改成脚本类型")

    def test_each_whitelisted_path_goes_to_its_own_upstream(self) -> None:
        """三条路径各有各的上游主机，不是同一个域名下的不同路径。"""
        self.configure()
        for path, host in (("v4/map/styles", "https://webapi.amap.com/v4/map/styles"),
                           ("v3/vectormap", "https://fmap01.amap.com/v3/vectormap"),
                           ("v3/log/init", "https://restapi.amap.com/v3/log/init")):
            self.sent.clear()
            self.assertEqual(self.client.get(f"/_AMapService/{path}").status_code, 200, path)
            self.assertTrue(self.sent[0].startswith(host + "?"), f"{path} → {self.sent[0]}")

    def test_service_class_paths_are_refused_and_never_reach_the_upstream(self) -> None:
        """**放行名单之外一律 403**，而且一次上游调用都不该发生。

        这条挡的不只是「多花钱」：服务类接口一旦能经代理调用，浏览器就能自己去判断事实，
        绕开「世界事实由后端取回并落库」那条规则。
        """
        self.configure()
        for path in ("v3/geocode/geo", "v3/place/text", "v3/direction/transit/integrated",
                     "v3/weather/weatherInfo", "v3/staticmap"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(f"/_AMapService/{path}").status_code, 403)
        self.assertEqual(self.sent, [], "被拒的请求一次都不该打到上游")

    def test_a_near_miss_path_is_refused_because_the_list_is_an_enumeration(self) -> None:
        """名单是**枚举**不是前缀匹配：`v3/log/init/x` 与 `v3/log` 都不放行。"""
        self.configure()
        for path in ("v3/log", "v3/log/init/extra", "v3/log/init2", "V3/LOG/INIT"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(f"/_AMapService/{path}").status_code, 403)
        self.assertEqual(self.sent, [])

    def test_without_a_security_code_it_refuses_instead_of_forwarding_bare(self) -> None:
        """没配安全密钥时**不裸转发**：那样上游会返回 INVALID_USER_SCODE、样式缺字，属于静默劣化。"""
        self.configure(code=None)
        self.assertEqual(self.client.get("/_AMapService/v3/log/init").status_code, 503)
        self.assertEqual(self.sent, [], "没有密钥就一次都不发")

    def test_only_get_is_allowed(self) -> None:
        self.configure()
        for method in (self.client.post, self.client.put, self.client.delete):
            with self.subTest(method=method.__name__):
                self.assertEqual(method("/_AMapService/v3/log/init").status_code, 405)
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
