"""网页底图：服务端代理高德静态地图（密钥只在服务端）。

- 前端给出要显示的范围（WGS-84）和容器尺寸。服务端选整数缩放级别，中心吸附到 32 像素网格，尺寸取 32 的倍数，
  所以同一片区的请求会复用同一张图（缓存 24 小时），不会因为几个像素的差别重复计费；
- 只在高德服务区（目前是港澳及珠三角）提供。东京等海外范围不混用高德底图：总方案规定国外用 Google，而 Google 目前未开通计费；
- 图片原样保存和返回（含高德标志与审图号），不改绘；
- 每日总量（amap_static）和每人每日新增张数都有上限。失败或超限时如实返回不可用，由前端退回示意地图。

坐标：返回的 center 是 WGS-84。请求高德时把中心转成 GCJ-02。图幅内的偏移量近似不变（在所用缩放级别下误差不到 1 像素），
因此前端可以直接用 WGS-84 做 Web Mercator 投影，叠加的路线和车辆能与底图街道对齐。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib import error, parse, request

from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from .coords import wgs84_to_gcj02
from .meter import ProviderMeter

AMAP_STATIC_URL = "https://restapi.amap.com/v3/staticmap"
PROVIDER = "amap_static"
ATTRIBUTION = "底图：高德地图"
TILE = 256
GRID = 32
PAD = 48
MIN_ZOOM, MAX_ZOOM = 3, 17
SIZE_STEP, MIN_SIZE, MAX_SIZE = 32, 256, 1024
PER_USER_DAILY = 40
CACHE_TTL = timedelta(hours=24)
MAX_BYTES = 4 * 1024 * 1024
_ID = re.compile(r"^bm_[0-9a-f]{20}$")

# (名称, 南, 西, 北, 东)。扩大高德底图范围时在这里追加片区。
AMAP_REGIONS: tuple[tuple[str, float, float, float, float], ...] = (("港澳及珠三角", 21.4, 112.8, 24.0, 115.0),)

Fetch = Callable[[str, float], tuple[str, bytes]]


def world_px(lat: float, lng: float, zoom: int) -> tuple[float, float]:
    """Web Mercator 世界像素（256 像素瓦片）。"""
    size = TILE * 2**zoom
    s = math.sin(math.radians(max(-85.05, min(85.05, lat))))
    return (lng + 180.0) / 360.0 * size, (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * size


def latlng_of(x: float, y: float, zoom: int) -> tuple[float, float]:
    size = TILE * 2**zoom
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / size)))), x / size * 360.0 - 180.0


def quantize_size(value: float) -> int:
    return int(min(MAX_SIZE, max(MIN_SIZE, round(value / SIZE_STEP) * SIZE_STEP)))


def in_amap_region(south: float, west: float, north: float, east: float) -> bool:
    return any(s <= south and w <= west and north <= n and east <= e for _, s, w, n, e in AMAP_REGIONS)


@dataclass(frozen=True)
class BasemapPlan:
    zoom: int
    center_x: int  # 该缩放级别下的世界像素（已吸附网格）
    center_y: int
    width: int  # 逻辑像素；图片为 2 倍清晰度
    height: int

    @property
    def center(self) -> tuple[float, float]:
        return latlng_of(self.center_x, self.center_y, self.zoom)

    @property
    def basemap_id(self) -> str:
        key = f"amap|{self.zoom}|{self.center_x}|{self.center_y}|{self.width}|{self.height}"
        return "bm_" + hashlib.sha1(key.encode("ascii")).hexdigest()[:20]


def plan_basemap(south: float, west: float, north: float, east: float, width: float, height: float) -> BasemapPlan | None:
    """选能把范围（含边距与吸附余量）放进图幅的最大整数缩放级别。"""
    w, h = quantize_size(width), quantize_size(height)
    for zoom in range(MAX_ZOOM, MIN_ZOOM - 1, -1):
        x0, y0 = world_px(north, west, zoom)
        x1, y1 = world_px(south, east, zoom)
        if (x1 - x0) + 2 * PAD + GRID <= w and (y1 - y0) + 2 * PAD + GRID <= h:
            return BasemapPlan(zoom, round((x0 + x1) / 2 / GRID) * GRID, round((y0 + y1) / 2 / GRID) * GRID, w, h)
    return None


@dataclass(frozen=True)
class BasemapResult:
    available: bool
    reason: str | None = None  # outside_region / daily_cap / user_limit / upstream_error
    plan: BasemapPlan | None = None
    expires_at: datetime | None = None


def _http_fetch(url: str, timeout: float) -> tuple[str, bytes]:
    with request.urlopen(url, timeout=timeout) as resp:
        return resp.headers.get("Content-Type") or "", resp.read(MAX_BYTES + 1)


class BasemapService:
    def __init__(self, storage: JourneyStorage, media_dir: Path, meter: ProviderMeter, *, amap_key: str, timeout: float,
                 fetch: Fetch | None = None, per_user_daily: int = PER_USER_DAILY) -> None:
        self.storage = storage
        self.dir = media_dir / "basemaps"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.meter = meter
        self._key = amap_key
        self.timeout = timeout
        self._fetch = fetch or _http_fetch
        self.per_user_daily = per_user_daily
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    # ---- 查询 ----
    def view(self, user_id: str, south: float, west: float, north: float, east: float, width: float, height: float) -> BasemapResult:
        if not in_amap_region(south, west, north, east):
            return BasemapResult(False, "outside_region")
        plan = plan_basemap(south, west, north, east, width, height)
        if plan is None:
            return BasemapResult(False, "outside_region")
        with self._lock_for(plan.basemap_id):
            expires = self._fresh_until(plan.basemap_id)
            if expires is not None:
                return BasemapResult(True, plan=plan, expires_at=expires)
            if self._requested_today(user_id) >= self.per_user_daily:
                return BasemapResult(False, "user_limit")
            if not self.meter.allow(PROVIDER):
                return BasemapResult(False, "daily_cap")
            downloaded = self._download(plan)
            if downloaded is None:
                return BasemapResult(False, "upstream_error")
            expires = self._store(plan, user_id, *downloaded)
        return BasemapResult(True, plan=plan, expires_at=expires)

    def file_for(self, basemap_id: str) -> tuple[Path, str] | None:
        if not _ID.match(basemap_id):
            return None
        with self.storage.connect() as conn:
            row = conn.execute("SELECT content_type, expires_at FROM web_basemap_cache WHERE basemap_id = ?", (basemap_id,)).fetchone()
        path = self.dir / f"{basemap_id}.img"
        if row is None or parse_dt(row["expires_at"]) <= utcnow() or not path.exists():
            return None
        return path, row["content_type"]

    # ---- 内部 ----
    def _lock_for(self, basemap_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(basemap_id, threading.Lock())

    def _fresh_until(self, basemap_id: str) -> datetime | None:
        if self.file_for(basemap_id) is None:
            return None
        with self.storage.connect() as conn:
            row = conn.execute("SELECT expires_at FROM web_basemap_cache WHERE basemap_id = ?", (basemap_id,)).fetchone()
        return parse_dt(row["expires_at"]) if row else None

    def _requested_today(self, user_id: str) -> int:
        start = datetime.combine(utcnow().date(), time.min, tzinfo=timezone.utc)
        with self.storage.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM web_basemap_cache WHERE requested_by = ? AND fetched_at >= ?", (user_id, iso(start))).fetchone()
        return int(row["n"])

    def _download(self, plan: BasemapPlan) -> tuple[str, bytes] | None:
        glat, glng = wgs84_to_gcj02(*plan.center)
        query = {"location": f"{glng:.6f},{glat:.6f}", "zoom": plan.zoom, "size": f"{plan.width}*{plan.height}", "scale": 2, "key": self._key}
        try:
            content_type, body = self._fetch(f"{AMAP_STATIC_URL}?{parse.urlencode(query)}", self.timeout)
        except error.HTTPError as exc:
            self.meter.record(PROVIDER, False, f"http {exc.code}")
            return None
        except Exception as exc:  # noqa: BLE001 - 网络/超时：如实记录并退回示意地图
            self.meter.record(PROVIDER, False, f"{type(exc).__name__}: {exc}")
            return None
        if not content_type.lower().startswith("image/"):
            try:
                info = json.loads(body.decode("utf-8", "replace")).get("info")
            except ValueError:
                info = "non-image response"
            self.meter.record(PROVIDER, False, f"amap: {info}")
            return None
        if len(body) > MAX_BYTES or not body.startswith((b"\x89PNG", b"\xff\xd8")):
            self.meter.record(PROVIDER, False, "amap: unexpected image payload")
            return None
        self.meter.record(PROVIDER, True)
        return ("image/png" if body.startswith(b"\x89PNG") else "image/jpeg"), body

    def _store(self, plan: BasemapPlan, user_id: str, content_type: str, body: bytes) -> datetime:
        path = self.dir / f"{plan.basemap_id}.img"
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(body)
        tmp.replace(path)
        lat, lng = plan.center
        now = utcnow()
        with self.storage.connect() as conn:
            conn.execute(
                "INSERT INTO web_basemap_cache (basemap_id, provider, zoom, center_lat, center_lng, width, height, content_type, requested_by, fetched_at, expires_at) "
                "VALUES (?, 'amap', ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(basemap_id) DO UPDATE SET content_type = excluded.content_type, "
                "requested_by = excluded.requested_by, fetched_at = excluded.fetched_at, expires_at = excluded.expires_at",
                (plan.basemap_id, plan.zoom, lat, lng, plan.width, plan.height, content_type, user_id, iso(now), iso(now + CACHE_TTL)),
            )
        return now + CACHE_TTL
