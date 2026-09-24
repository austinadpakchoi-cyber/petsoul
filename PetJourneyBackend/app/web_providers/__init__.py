"""网页真实供应商（服务端）：对话模型、地点/路线、底图、插画。总开关 PETJOURNEY_WEB_PROVIDERS 默认关闭。

关闭或缺密钥时所有入口都是“不可用”实现，调用方按能力如实降级；测试注入假实现，不触网。
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from ..config import Settings
from ..storage import JourneyStorage
from .basemap import BasemapResult, BasemapService
from .geo import GeoService, PlaceCandidate, RouteEstimate
from .images import Illustrator, ImageUnavailable, NoIllustrator, SeedreamIllustrator
from .llm import ChatResult, ChatUnavailable, NoChat, OpenAICompatibleChat, WebChat
from .meter import ProviderMeter, provider_status


@dataclass
class WebProviders:
    enabled: bool
    chat: WebChat
    geo: GeoService | None
    illustrator: Illustrator
    meter: ProviderMeter | None
    basemap: BasemapService | None = None


def disabled_providers() -> WebProviders:
    return WebProviders(enabled=False, chat=NoChat(), geo=None, illustrator=NoIllustrator(), meter=None)


def build_web_providers(settings: Settings, storage: JourneyStorage) -> WebProviders:
    if not settings.web_providers_enabled:
        return disabled_providers()
    secrets = [settings.openai_api_key, settings.amap_api_key, settings.google_maps_api_key, settings.doubao_api_key, settings.image_api_key]
    meter = ProviderMeter(storage, {"llm": settings.web_llm_daily_cap, "image": settings.web_image_daily_cap,
                                    "amap": settings.web_map_daily_cap, "google": settings.web_map_daily_cap,
                                    "amap_static": settings.web_map_static_daily_cap}, secrets=[s for s in secrets if s])
    chat: WebChat = NoChat()
    if settings.openai_api_key and settings.llm_provider not in ("mock", ""):
        label = "DeepSeek" if "deepseek" in settings.openai_base_url else "OpenAI 兼容模型"
        chat = OpenAICompatibleChat(base_url=settings.openai_base_url, api_key=settings.openai_api_key, model=settings.agent_model,
                                    timeout=settings.web_llm_timeout_seconds, meter=meter, provider_label=label)
    illustrator: Illustrator = NoIllustrator()
    if settings.image_provider_type == "volcengine" and (settings.doubao_api_key or settings.image_api_key):
        from ..image_provider.seedream import DoubaoSeedreamImageProvider

        illustrator = SeedreamIllustrator(DoubaoSeedreamImageProvider(dataclasses.replace(settings, volcengine_image_model=settings.web_image_model)), meter)
    elif settings.image_provider_type in {"openai", "openai-compatible"} and settings.image_api_key:
        from .gpt_images import GPTIllustrator

        illustrator = GPTIllustrator(dataclasses.replace(settings, image_model=settings.web_image_model), meter)
    geo = GeoService(storage, meter, amap_key=settings.amap_api_key, google_key=settings.google_maps_api_key, timeout=settings.map_timeout_seconds)
    basemap = (BasemapService(storage, settings.web_private_media_dir, meter, amap_key=settings.amap_api_key, timeout=settings.map_timeout_seconds)
               if settings.amap_api_key else None)
    return WebProviders(enabled=True, chat=chat, geo=geo, illustrator=illustrator, meter=meter, basemap=basemap)


__all__ = [
    "BasemapResult",
    "BasemapService",
    "ChatResult",
    "ChatUnavailable",
    "GeoService",
    "ImageUnavailable",
    "PlaceCandidate",
    "RouteEstimate",
    "WebProviders",
    "build_web_providers",
    "disabled_providers",
    "provider_status",
]
