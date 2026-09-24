"""供应商就绪判断（只看配置与最近一次脱敏错误，不发请求）。供各路由的 capabilities() 如实声明能力。"""

from __future__ import annotations

from .meter import provider_status


def _enabled(settings) -> bool:
    return bool(getattr(settings, "web_providers_enabled", False))


def llm_ready(settings) -> bool:
    return _enabled(settings) and bool(settings.openai_api_key) and settings.llm_provider not in ("mock", "")


def amap_ready(settings) -> bool:
    return _enabled(settings) and bool(settings.amap_api_key)


def google_state(settings) -> tuple[bool, str]:
    """(可用, 说明)。有 key 但最近一次调用被拒（例如项目未开通计费）时如实返回不可用。"""
    if not (_enabled(settings) and settings.google_maps_api_key):
        return False, "未配置"
    error = provider_status("google") or ""
    if "PERMISSION_DENIED" in error or "REQUEST_DENIED" in error or "billing" in error.lower() or "http 403" in error:
        return False, "Google 地图调用被拒（项目未开通计费或未启用 Places/Routes API）"
    return True, "服务端 Places/Routes（港澳以外地区）"


def image_ready(settings) -> bool:
    if not _enabled(settings):
        return False
    if settings.image_provider_type == "volcengine":
        return bool(settings.doubao_api_key or settings.image_api_key)
    return settings.image_provider_type in {"openai", "openai-compatible"} and bool(settings.image_api_key)
