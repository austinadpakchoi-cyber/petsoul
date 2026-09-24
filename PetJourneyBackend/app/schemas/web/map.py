"""地图底图配置（CR-6C2B-MAP W0）：浏览器画高德底图所需的公开参数。

**这个文件里没有秘密，而且不该有。** `js_key` 按高德 JS API 的设计就是要交给浏览器的
（前端脚本必须带着它去加载），它的防护靠高德控制台的**域名白名单**、不靠保密。
**安全密钥（`amap_js_security_code`）不在这里、也不在任何响应里**——它只由站点根的
`/_AMapService` 代理在转发时补进查询串，见 `app/main.py`。

为什么把「白名单」写进契约注释而不只写在部署文档里：**这个接口是公开读的**
（访客页也要画图），所以只要它上了公网，那把 Key 就在外面。
**白名单必须早于任何公网可达的环境**（含临时预览），否则等于把额度开放给任何人。
"""

from __future__ import annotations

from enum import Enum

from .common import WebModel

# 没有它就不会进生成物（`app/schemas/web/__init__.py` 的文件说明写明了这条），
# 而且**不会报错**——契约里静静地少一个模型，只有数数才发现。
__all__ = ["MapProvider", "MapUnavailableReason", "MapConfig"]


class MapProvider(str, Enum):
    amap = "amap"


class MapUnavailableReason(str, Enum):
    not_configured = "not_configured"  # 没有配 AMAP_JS_KEY：前端退回示意底图，主面板照常


class MapConfig(WebModel):
    """`GET /map/config` 的响应。未配置时 `available=false` 且 `js_key`/`service_host` 为空。"""

    provider: MapProvider = MapProvider.amap
    available: bool
    js_key: str | None = None
    # 同源**相对路径**，不是绝对地址：浏览器按当前站点解析即可，既不用后端猜协议与端口，
    # 也不会在反向代理后面把内网地址发出去。开发期由 `PetJourneyWeb/vite.config.ts` 的
    # `/_AMapService` 代理转给后端；生产由反向代理转发（属部署，本批不做）。
    service_host: str | None = None
    style: str
    style_dark: str
    # 这把 Web 端 Key 没有境外详细瓦片：6c2b 实测东京/巴黎 zoom 13 返回
    # `TILE_ACCESS_OVERSEA_FORBIDDEN`（11000），只有世界级（zoom≈3）能看。
    # **此值为该窗口实测、本窗口未复算**（复算需要真实高德调用）。
    overseas_tiles: bool = False
    unavailable_reason: MapUnavailableReason | None = None
