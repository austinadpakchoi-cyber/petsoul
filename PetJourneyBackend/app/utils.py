"""跨模块共享的工具函数。

集中放置纯函数，避免在 storage / providers / google_maps_services 中重复定义。
"""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """当前 UTC 时间。"""
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    """把时间归一化为 UTC ISO 字符串。"""
    return dt.astimezone(timezone.utc).isoformat()


def parse_dt(value: str) -> datetime:
    """解析 ISO 时间字符串。"""
    return datetime.fromisoformat(value)


def sanitize_place_id(name: str) -> str:
    """把地点名规范化为安全的 id（仅保留字母数字，其余转连字符）。"""
    return "".join(ch if ch.isalnum() else "-" for ch in name).strip("-") or "place"
