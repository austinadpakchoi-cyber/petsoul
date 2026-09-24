"""地图底图配置（/api/v1/web/map/config，CR-6C2B-MAP W0）。

**公开读**：访客页也要画图，所以不要求登录。纯读——不推进世界、不调任何供应商、不写库。

**这个接口按设计会把 `AMAP_JS_KEY` 发给浏览器**，那是高德 JS API 的固有形态（前端脚本必须带着它
去加载底图）。它的防护是高德控制台的**域名白名单**，不是保密。由此推出一条硬要求：
**白名单必须早于任何公网可达的环境**（含临时预览）配好，否则这个公开接口等于把额度开放给任何人。

**安全密钥（`AMAP_JS_SECURITY_CODE`）绝不出现在这里**——它只由站点根的 `/_AMapService`
反向代理在转发时补进查询串（见 `app/main.py`）。本文件不读它、不返回它、不记录它。

为什么 `available` 只看 JS Key、不看 `web_providers_enabled` 总开关：那个总开关管的是
**后端要不要去调供应商**（会产生费用），而底图是**浏览器直接向高德请求**、不经过后端计费口。
实际效果上两者也不冲突——JS Key 只存在于 `data/secrets/web-providers.env`，而那个文件只在
`PETSOUL_DEV_PROVIDERS=1` 时才被 `scripts/dev-backend.mjs` 读进来，没开就根本没有 key。
"""

from __future__ import annotations

from fastapi import Request

from ...schemas.web.common import Capability, CapabilityStatus
from ...schemas.web.map import MapConfig, MapUnavailableReason
from ._shared import cap, web_router

router = web_router("map")

# 6c2b 2026-09-24 实测过的两套官方样式：不走安全代理时 `whitesmoke` 缺文字、`macaron` 空白，
# 补上 jscode 之后 `whitesmoke` / `darkblue` 都完整渲染。**此为该窗口实测，本窗口未复算。**
STYLE_LIGHT = "amap://styles/whitesmoke"
STYLE_DARK = "amap://styles/darkblue"

# 同源相对路径。高德要求安全代理以 `_AMapService` 作**一级路由**——放在 `/api/v1/web` 下面
# 会被 JS API 拒绝（6c2b 实测，本窗口未复算），所以它挂在站点根，不在本路由的前缀里。
SERVICE_PATH = "/_AMapService"


def capabilities(settings) -> list[Capability]:
    """能力键是 `map.js_api`，**不是** `map.basemap`。

    `map.basemap`（`journey.py`）指的是**服务端代理的静态底图**（Web 服务 Key，缓存 24 小时，
    港澳范围）；这里是**浏览器端可交互底图**（Web 端 JS Key，浏览器直接向高德请求）。
    两把 Key 不同、计费口不同、失败表现也不同——**共用一个键会让「地图可用」这句话失去意义**。
    """
    ready = bool(settings.amap_js_key)
    return [cap("map.js_api", "map",
                CapabilityStatus.available if ready else CapabilityStatus.not_configured,
                "高德 JS API 交互底图：公开下发 JS Key（靠控制台域名白名单防护），"
                "安全密钥只在后端、由 /_AMapService 代理补进转发；与静态底图 map.basemap 是两条链路"
                if ready else "未配置 AMAP_JS_KEY：前端退回示意底图，主面板照常")]


@router.get("/map/config", response_model=MapConfig)
def map_config(request: Request) -> MapConfig:
    """画底图需要的公开参数。没配 JS Key 时如实返回不可用，**不给半套参数**。

    没配时 `js_key` 与 `service_host` 都为空：给了其中一个而另一个为空，前端会以为能画、
    实际画不出来——不可用就整体不可用，让调用方一眼看出来。
    """
    settings = request.app.state.settings
    js_key = settings.amap_js_key or None
    if not js_key:
        return MapConfig(available=False, js_key=None, service_host=None,
                         style=STYLE_LIGHT, style_dark=STYLE_DARK,
                         unavailable_reason=MapUnavailableReason.not_configured)
    return MapConfig(available=True, js_key=js_key, service_host=SERVICE_PATH,
                     style=STYLE_LIGHT, style_dark=STYLE_DARK, unavailable_reason=None)
