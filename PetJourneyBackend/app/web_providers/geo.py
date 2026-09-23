"""真实地点与路线估时（服务端）：港澳用高德 Web 服务，其他地区用 Google（Places/Routes，需项目开通计费与对应 API）。

- 输入输出统一 WGS-84；高德请求前转 GCJ-02，结果转回；
- 结果按请求缓存一天（web_geo_cache），同一路线/同一片区重复出发不再计费；
- 失败/超限/未配置返回 None，由调用方回退演示资料并如实标注，不编造地点或时长；
- 地点数据带来源与署名（高德地图 / Google），真实商家资料与动物世界内饰分开展示。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import timedelta
from typing import Literal
from urllib import error, parse, request

from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from .coords import gcj02_to_wgs84, wgs84_to_gcj02
from .meter import ProviderMeter

Region = Literal["amap", "google"]
CACHE_TTL = timedelta(hours=24)


@dataclass(frozen=True)
class PlaceCandidate:
    provider: str  # amap / google
    place_id: str  # 带命名空间：amap:<id> / google:<id>
    name: str
    address: str | None
    lat: float
    lng: float
    category: str | None
    attribution: str
    fetched_at: str | None = None  # 这份资料从供应商取回的时间（UTC ISO）；缓存命中时是当初取回的时间


@dataclass(frozen=True)
class RouteEstimate:
    provider: str
    mode: str  # walk / drive
    duration_seconds: int
    distance_meters: int | None
    points: list[tuple[float, float]]  # (lat, lng) WGS-84，已抽稀
    fetched_at: str | None = None


def _downsample(points: list[tuple[float, float]], limit: int = 60) -> list[tuple[float, float]]:
    if len(points) <= limit:
        return points
    step = (len(points) - 1) / (limit - 1)
    return [points[round(i * step)] for i in range(limit)]


_BRACKETS = re.compile(r"[（(][^）)]*[）)]|\s")
LODGING = ("酒店", "宾馆", "旅馆", "民宿", "客栈", "公寓")


def name_score(query: str, poi_name: str) -> int:
    """地名吻合度：3 完全相同，2 以它开头，1 包含且多出的字不超过 6 个，0 对不上。问的不是住处时，酒店民宿一律 0。"""
    q, n = _BRACKETS.sub("", query), _BRACKETS.sub("", poi_name)
    if not q or not n:
        return 0
    if any(k in n for k in LODGING) and not any(k in q for k in LODGING):
        return 0
    if n == q:
        return 3
    if n.startswith(q) or q.startswith(n):
        return 2
    if q in n and len(n) - len(q) <= 6:
        return 1
    return 0


def _decode_google_polyline(encoded: str) -> list[tuple[float, float]]:
    points, index, lat, lng = [], 0, 0, 0
    while index < len(encoded):
        for is_lng in (False, True):
            shift = result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if is_lng:
                lng += delta
            else:
                lat += delta
        points.append((lat / 1e5, lng / 1e5))
    return points


class GeoService:
    def __init__(self, storage: JourneyStorage, meter: ProviderMeter, *, amap_key: str | None, google_key: str | None, timeout: float) -> None:
        self.storage = storage
        self.meter = meter
        self._amap_key = amap_key
        self._google_key = google_key
        self.timeout = timeout

    def configured(self, region: Region) -> bool:
        return bool(self._amap_key if region == "amap" else self._google_key)

    # ---- 缓存 ----
    def _cache_get(self, key: str):
        with self.storage.connect() as conn:
            row = conn.execute("SELECT payload_json, fetched_at, expires_at FROM web_geo_cache WHERE cache_key = ?", (key,)).fetchone()
        if row is None or parse_dt(row["expires_at"]) <= utcnow():
            return None
        payload = json.loads(row["payload_json"])
        if isinstance(payload, dict) and payload and not payload.get("fetched_at"):
            payload["fetched_at"] = row["fetched_at"]  # 旧缓存没有记在内容里：用缓存行的取回时间
        return payload

    def _cache_put(self, key: str, provider: str, payload) -> None:
        now = utcnow()
        with self.storage.connect() as conn:
            conn.execute("INSERT INTO web_geo_cache (cache_key, provider, payload_json, fetched_at, expires_at) VALUES (?, ?, ?, ?, ?) "
                         "ON CONFLICT(cache_key) DO UPDATE SET payload_json = excluded.payload_json, fetched_at = excluded.fetched_at, expires_at = excluded.expires_at",
                         (key, provider, json.dumps(payload, ensure_ascii=False), iso(now), iso(now + CACHE_TTL)))

    @staticmethod
    def _key(*parts: object) -> str:
        return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()

    # ---- HTTP ----
    def _http_json(self, provider: str, req: request.Request) -> dict | None:
        if not self.meter.allow(provider):
            return None
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            self.meter.record(provider, False, f"http {exc.code}: {detail}")
            return None
        except Exception as exc:  # noqa: BLE001
            self.meter.record(provider, False, f"{type(exc).__name__}: {exc}")
            return None
        if provider == "amap" and str(data.get("status")) != "1":
            self.meter.record(provider, False, f"amap: {data.get('info')}")
            return None
        if provider == "google" and data.get("error"):
            self.meter.record(provider, False, f"google: {data['error'].get('status')} {data['error'].get('message')}")
            return None
        self.meter.record(provider, True)
        return data

    # ---- 地点 ----
    def place_near(self, region: Region, lat: float, lng: float, *, keyword: str = "咖啡", google_type: str = "cafe", radius: int = 800) -> PlaceCandidate | None:
        if not self.configured(region):
            return None
        key = self._key("place", region, round(lat, 4), round(lng, 4), keyword, google_type, radius)
        cached = self._cache_get(key)
        if cached is not None:
            return PlaceCandidate(**cached) if cached else None
        found = self._amap_place(lat, lng, keyword, radius) if region == "amap" else self._google_place(lat, lng, google_type, radius)
        if found is not None:
            found = replace(found, fetched_at=iso(utcnow()))
            self._cache_put(key, region, asdict(found))
        return found

    def _amap_place(self, lat: float, lng: float, keyword: str, radius: int) -> PlaceCandidate | None:
        glat, glng = wgs84_to_gcj02(lat, lng)
        query = parse.urlencode({"key": self._amap_key, "location": f"{glng:.6f},{glat:.6f}", "keywords": keyword, "radius": radius,
                                 "sortrule": "distance", "offset": 10, "page": 1, "extensions": "base", "output": "JSON"})
        data = self._http_json("amap", request.Request(f"https://restapi.amap.com/v3/place/around?{query}"))
        for poi in (data or {}).get("pois") or []:
            name, location = poi.get("name"), poi.get("location")
            if not name or not isinstance(location, str) or "," not in location:
                continue
            plng, plat = (float(v) for v in location.split(",", 1))
            wlat, wlng = gcj02_to_wgs84(plat, plng)
            address = poi.get("address") if isinstance(poi.get("address"), str) else None
            category = str(poi.get("type") or "").split(";")[-1] or None
            return PlaceCandidate(provider="amap", place_id=f"amap:{poi.get('id')}", name=name, address=address, lat=round(wlat, 6), lng=round(wlng, 6),
                                  category=category, attribution="地点资料：高德地图")
        return None

    def _google_place(self, lat: float, lng: float, place_type: str, radius: int) -> PlaceCandidate | None:
        body = {"includedTypes": [place_type], "maxResultCount": 5, "rankPreference": "DISTANCE", "languageCode": "zh-CN",
                "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius}}}
        req = request.Request("https://places.googleapis.com/v1/places:searchNearby", data=json.dumps(body).encode("utf-8"), method="POST",
                              headers={"Content-Type": "application/json", "X-Goog-Api-Key": self._google_key or "",
                                       "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.primaryType"})
        data = self._http_json("google", req)
        for place in (data or {}).get("places") or []:
            loc = place.get("location") or {}
            name = (place.get("displayName") or {}).get("text")
            if not name or "latitude" not in loc:
                continue
            return PlaceCandidate(provider="google", place_id=f"google:{place.get('id')}", name=name, address=place.get("formattedAddress"),
                                  lat=float(loc["latitude"]), lng=float(loc["longitude"]), category=place.get("primaryType"), attribution="地点资料：Google 地图")
        return None

    # ---- 路线估时 ----
    def place_in_city(self, region: Region, name: str, city: str) -> PlaceCandidate | None:
        """按名字在某座城市里找真实地点（核对攻略里写到的站点）。目前只接高德；Google 未开通前返回 None。

        只接受名字对得上的结果（完全相同 > 以它开头 > 包含且多出的字不多），问的不是住处时不接受酒店民宿，
        避免把“中山路”核对成“某某酒店（中山路地铁站店）”。"""
        if region != "amap" or not self.configured(region) or not name.strip():
            return None
        key = self._key("text", region, name.strip(), city)
        cached = self._cache_get(key)
        if cached is not None:
            return PlaceCandidate(**cached) if cached else None
        query = parse.urlencode({"key": self._amap_key, "keywords": name.strip(), "city": city, "citylimit": "true", "offset": 5, "page": 1,
                                 "extensions": "base", "output": "JSON"})
        data = self._http_json("amap", request.Request(f"https://restapi.amap.com/v3/place/text?{query}"))
        found, best = None, 0
        for poi in (data or {}).get("pois") or []:
            poi_name, location = poi.get("name"), poi.get("location")
            if not poi_name or not isinstance(location, str) or "," not in location:
                continue
            score = name_score(name, poi_name)
            if score <= best:
                continue
            plng, plat = (float(v) for v in location.split(",", 1))
            wlat, wlng = gcj02_to_wgs84(plat, plng)
            address = poi.get("address") if isinstance(poi.get("address"), str) else None
            found, best = PlaceCandidate(provider="amap", place_id=f"amap:{poi.get('id')}", name=poi_name, address=address, lat=round(wlat, 6), lng=round(wlng, 6),
                                         category=str(poi.get("type") or "").split(";")[-1] or None, attribution="地点资料：高德地图"), score
        if found is not None:
            found = replace(found, fetched_at=iso(utcnow()))
        if data is not None:
            self._cache_put(key, region, asdict(found) if found else {})
        return found

    def route(self, region: Region, mode: str, origin: tuple[float, float], destination: tuple[float, float],
              max_age: timedelta | None = None) -> RouteEstimate | None:
        """max_age：缓存里的估算比这更旧就重新取（出门前按最新路况复核用）。"""
        if not self.configured(region) or mode not in ("walk", "drive"):
            return None
        key = self._key("route", region, mode, round(origin[0], 5), round(origin[1], 5), round(destination[0], 5), round(destination[1], 5))
        cached = self._cache_get(key)
        fresh_enough = cached is not None and (max_age is None or (cached.get("fetched_at") and parse_dt(cached["fetched_at"]) >= utcnow() - max_age))
        if cached is not None and fresh_enough:
            return RouteEstimate(**{**cached, "points": [tuple(p) for p in cached["points"]]}) if cached else None
        found = self._amap_route(mode, origin, destination) if region == "amap" else self._google_route(mode, origin, destination)
        if found is not None:
            found = replace(found, fetched_at=iso(utcnow()))
            self._cache_put(key, region, asdict(found))
        return found

    def _amap_route(self, mode: str, origin: tuple[float, float], destination: tuple[float, float]) -> RouteEstimate | None:
        olat, olng = wgs84_to_gcj02(*origin)
        dlat, dlng = wgs84_to_gcj02(*destination)
        params = {"key": self._amap_key, "origin": f"{olng:.6f},{olat:.6f}", "destination": f"{dlng:.6f},{dlat:.6f}", "output": "JSON"}
        path = "/v3/direction/walking" if mode == "walk" else "/v3/direction/driving"
        if mode == "drive":
            params.update({"strategy": "10", "extensions": "base"})
        data = self._http_json("amap", request.Request(f"https://restapi.amap.com{path}?{parse.urlencode(params)}"))
        paths = ((data or {}).get("route") or {}).get("paths") or []
        if not paths:
            return None
        best = paths[0]
        points: list[tuple[float, float]] = []
        for step in best.get("steps") or []:
            for pair in str(step.get("polyline") or "").split(";"):
                if "," in pair:
                    plng, plat = (float(v) for v in pair.split(",", 1))
                    wlat, wlng = gcj02_to_wgs84(plat, plng)
                    point = (round(wlat, 6), round(wlng, 6))
                    if not points or points[-1] != point:
                        points.append(point)
        try:
            duration = int(float(best.get("duration")))
        except (TypeError, ValueError):
            return None
        distance = int(float(best["distance"])) if best.get("distance") not in (None, "") else None
        return RouteEstimate(provider="amap", mode=mode, duration_seconds=duration, distance_meters=distance, points=_downsample(points or [origin, destination]))

    def _google_route(self, mode: str, origin: tuple[float, float], destination: tuple[float, float]) -> RouteEstimate | None:
        body = {"origin": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}},
                "destination": {"location": {"latLng": {"latitude": destination[0], "longitude": destination[1]}}},
                "travelMode": "WALK" if mode == "walk" else "DRIVE"}
        req = request.Request("https://routes.googleapis.com/directions/v2:computeRoutes", data=json.dumps(body).encode("utf-8"), method="POST",
                              headers={"Content-Type": "application/json", "X-Goog-Api-Key": self._google_key or "",
                                       "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline"})
        data = self._http_json("google", req)
        routes = (data or {}).get("routes") or []
        if not routes:
            return None
        route = routes[0]
        try:
            duration = int(str(route.get("duration", "")).rstrip("s"))
        except ValueError:
            return None
        points = _decode_google_polyline((route.get("polyline") or {}).get("encodedPolyline") or "")
        return RouteEstimate(provider="google", mode=mode, duration_seconds=duration, distance_meters=route.get("distanceMeters"),
                             points=_downsample(points or [origin, destination]))
