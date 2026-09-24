"""高德 JS API 安全代理（站点根 `/_AMapService/*`，CR-6C2B-MAP W0）。

**为什么必须挂在站点根、而不是 `/api/v1/web` 下面**：高德要求安全代理以 `_AMapService`
作为**一级路由**，`serviceHost` 指向别处时 JS API 直接拒绝、自定义样式随之失效
（6c2b 2026-09-24 实测，**本窗口未复算**）。所以这个路由不带任何业务前缀。

**它只做一件事**：把三条**渲染类**请求转发给高德，并在转发时补上安全密钥 `jscode`。

    v4/map/styles   →  https://webapi.amap.com/v4/map/styles
    v3/vectormap    →  https://fmap01.amap.com/v3/vectormap
    v3/log/init     →  https://restapi.amap.com/v3/log/init

**白名单之外一律 403，这是本文件的要点，不是保守起见。** 地理编码、关键字搜索、路线规划、
天气这些**服务类**接口一旦能经代理调用，浏览器就能拿着我们的额度随便打，而且会绕过
「世界事实由后端取回并落库」这条规则——变成前端自己判断事实。所以放行名单是**枚举**，不是模式匹配。

**安全密钥只在这里用，不出现在任何响应体、日志与前端产物中。** 由此派生两条实现约束：
  · **不记录查询串**（里面既有 JS Key 也有 jscode），日志只记路径与状态码；
  · 只转发响应体与 Content-Type，不回传上游的其它响应头。
"""

from __future__ import annotations

import logging
import time
import urllib.parse
from collections import deque
from typing import Callable
from urllib import error, request

from fastapi import APIRouter, Request, Response

logger = logging.getLogger(__name__)

router = APIRouter(tags=["amap-service"])

# 放行名单：**枚举，不是前缀匹配**。键是 `/_AMapService/` 之后的完整路径。
# 这些端点是高德 JS 用 `<script src=...>` 加载的，必须按脚本类型回；其余是 fetch。
# **只列实测遇到的**，不预先把别的端点也当脚本——猜错的方向是「把 JSON 当脚本执行」。
SCRIPT_TARGETS = frozenset({"v3/log/init"})

ALLOWED_TARGETS: dict[str, str] = {
    "v4/map/styles": "https://webapi.amap.com/v4/map/styles",
    "v3/vectormap": "https://fmap01.amap.com/v3/vectormap",
    "v3/log/init": "https://restapi.amap.com/v3/log/init",
}

TIMEOUT_SECONDS = 10.0
MAX_BYTES = 8 * 1024 * 1024  # 矢量瓦片与样式包都远小于此；超出即视为异常上游
RATE_LIMIT_PER_MINUTE = 240  # 一次开图会连续拉多块瓦片，阈值按「一个正常用户的突发」留余量

Fetch = Callable[[str], tuple[str, bytes]]


def _http_fetch(url: str) -> tuple[str, bytes]:
    with request.urlopen(url, timeout=TIMEOUT_SECONDS) as resp:  # noqa: S310 - 目标仅限上面的枚举
        return resp.headers.get("Content-Type") or "application/octet-stream", resp.read(MAX_BYTES + 1)


class _IpRateLimiter:
    """按 IP 的滑动窗口计数。

    进程内、不持久：**它挡的是「一个来源把额度打光」，不是分布式防刷**。
    多进程部署时各进程各算一份——这一点写明，免得有人把它当成全局配额。
    """

    def __init__(self, per_minute: int = RATE_LIMIT_PER_MINUTE) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = {}

    def allow(self, client: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        seen = self._hits.setdefault(client, deque())
        while seen and now - seen[0] > 60.0:
            seen.popleft()
        if len(seen) >= self.per_minute:
            return False
        seen.append(now)
        return True


_limiter = _IpRateLimiter()


@router.get("/_AMapService/{target:path}")
def amap_service(target: str, request_: Request) -> Response:
    """转发渲染类请求并补安全密钥。**只 GET**（路由未声明其它方法，其余自然 405）。"""
    upstream = ALLOWED_TARGETS.get(target)
    if upstream is None:
        # 只记路径，不记查询串。403 不区分「不存在」与「不放行」——对调用方是同一件事。
        logger.info("amap proxy refused path=%s", target)
        return Response(status_code=403, content=b"", media_type="text/plain")

    settings = request_.app.state.settings
    code = getattr(settings, "amap_js_security_code", None)
    if not code:
        logger.info("amap proxy not configured path=%s", target)
        return Response(status_code=503, content=b"", media_type="text/plain")

    client = request_.client.host if request_.client else "-"
    if not _limiter.allow(client):
        logger.info("amap proxy rate limited path=%s", target)
        return Response(status_code=429, content=b"", media_type="text/plain")

    query = dict(urllib.parse.parse_qsl(str(request_.url.query), keep_blank_values=True))
    query["jscode"] = code  # 安全密钥在这里补进去，只走出站方向
    url = f"{upstream}?{urllib.parse.urlencode(query)}"

    fetch: Fetch = getattr(request_.app.state, "amap_fetch", None) or _http_fetch
    try:
        content_type, body = fetch(url)
    except error.HTTPError as exc:  # 上游明确拒绝：把状态码如实传回，正文不传（可能含提示信息）
        logger.info("amap proxy upstream http error path=%s status=%s", target, exc.code)
        return Response(status_code=exc.code, content=b"", media_type="text/plain")
    except Exception:  # 网络故障等：不泄露内部细节
        logger.info("amap proxy upstream failed path=%s", target)
        return Response(status_code=502, content=b"", media_type="text/plain")

    if len(body) > MAX_BYTES:
        logger.info("amap proxy oversize path=%s", target)
        return Response(status_code=502, content=b"", media_type="text/plain")
    # `v3/log/init` 是高德 JS 用 `<script src=...>` 取的（JSONP 形态），**不是 fetch**。
    # 按上游的 JSON MIME ＋ `nosniff` 返回，浏览器会**拒绝执行**它——6c2b 报「每次打开地图都有」。
    # `nosniff` 一个字都不去掉（那是防 MIME 混淆的安全头）；改的是**给它一个对的类型**。
    # 其余端点是 fetch 取的，照旧用上游类型。
    if target in SCRIPT_TARGETS:
        content_type = "application/javascript; charset=utf-8"
    return Response(content=body, media_type=content_type,
                    headers={"Cache-Control": "public, max-age=600", "X-Content-Type-Options": "nosniff"})
