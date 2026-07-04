from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib import error, parse, request
import uuid

from .config import Settings
from .schemas import MapSearchTip, ReverseGeocodeResult, StaticMapAsset, TravelMode


@dataclass(frozen=True, slots=True)
class AMapRouteResult:
    distance_meters: int | None
    duration_seconds: int | None
    polyline: str | None
    provider: str


class AMapWebServiceClient:
    provider_name = "amap-web-service-client"

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.amap_api_key)

    def route_between(
        self,
        *,
        mode: TravelMode,
        origin_lng: float,
        origin_lat: float,
        destination_lng: float,
        destination_lat: float,
    ) -> AMapRouteResult | None:
        if not self.configured:
            return None
        if mode == TravelMode.walk:
            payload = self._get_json(
                "/v3/direction/walking",
                {
                    "origin": f"{origin_lng},{origin_lat}",
                    "destination": f"{destination_lng},{destination_lat}",
                    "output": "JSON",
                },
            )
        elif mode == TravelMode.drive:
            payload = self._get_json(
                "/v3/direction/driving",
                {
                    "origin": f"{origin_lng},{origin_lat}",
                    "destination": f"{destination_lng},{destination_lat}",
                    "strategy": "10",
                    "extensions": "base",
                    "output": "JSON",
                },
            )
        else:
            return None
        return self._parse_route(payload)

    def input_tips(self, *, keywords: str, city: str | None = None, limit: int = 10) -> list[MapSearchTip]:
        if not self.configured or not keywords.strip():
            return []
        params = {
            "keywords": keywords.strip(),
            "datatype": "all",
            "output": "JSON",
        }
        if city:
            params["city"] = city
        payload = self._get_json("/v3/assistant/inputtips", params)
        tips = payload.get("tips")
        if not isinstance(tips, list):
            return []
        return [tip for tip in (self._tip_from_payload(item) for item in tips[:limit]) if tip is not None]

    def reverse_geocode(self, *, lat: float, lng: float) -> ReverseGeocodeResult | None:
        if not self.configured:
            return None
        payload = self._get_json(
            "/v3/geocode/regeo",
            {
                "location": f"{lng},{lat}",
                "extensions": "base",
                "output": "JSON",
            },
        )
        regeocode = payload.get("regeocode")
        if not isinstance(regeocode, dict):
            return None
        component = regeocode.get("addressComponent")
        if not isinstance(component, dict):
            component = {}
        street_number = component.get("streetNumber")
        if not isinstance(street_number, dict):
            street_number = {}
        return ReverseGeocodeResult(
            formatted_address=self._clean(regeocode.get("formatted_address")) or "",
            province=self._clean(component.get("province")),
            city=self._clean(component.get("city")),
            district=self._clean(component.get("district")),
            township=self._clean(component.get("township")),
            adcode=self._clean(component.get("adcode")),
            street=self._clean(street_number.get("street")),
            number=self._clean(street_number.get("number")),
            poi_name=None,
            source=self.provider_name,
        )

    def static_map_asset(
        self,
        *,
        center_lat: float,
        center_lng: float,
        zoom: int = 14,
        markers: str | None = None,
        paths: str | None = None,
    ) -> StaticMapAsset:
        generated_at = datetime.now(timezone.utc)
        if not self.configured:
            return StaticMapAsset(
                provider="mock-static-map",
                center_lat=center_lat,
                center_lng=center_lng,
                zoom=zoom,
                media_url=None,
                fallback_url=None,
                generated_at=generated_at,
            )

        params = {
            "location": f"{center_lng},{center_lat}",
            "zoom": str(max(3, min(18, zoom))),
            "size": "750*420",
            "scale": "2",
        }
        if markers:
            params["markers"] = markers
        if paths:
            params["paths"] = paths
        query = parse.urlencode({**params, "key": self.settings.amap_api_key})
        url = f"https://restapi.amap.com/v3/staticmap?{query}"

        media_url = self._download_static_map(url)
        return StaticMapAsset(
            provider=self.provider_name,
            center_lat=center_lat,
            center_lng=center_lng,
            zoom=zoom,
            media_url=media_url,
            fallback_url=None if media_url else self._redacted_static_map_url(params),
            generated_at=generated_at,
        )

    def _parse_route(self, payload: dict[str, object]) -> AMapRouteResult | None:
        route = payload.get("route")
        if not isinstance(route, dict):
            return None
        paths = route.get("paths")
        if not isinstance(paths, list) or not paths:
            return None
        path = paths[0]
        if not isinstance(path, dict):
            return None
        steps = path.get("steps")
        polyline_parts: list[str] = []
        if isinstance(steps, list):
            for step in steps:
                if isinstance(step, dict):
                    polyline = self._clean(step.get("polyline"))
                    if polyline:
                        polyline_parts.append(polyline)
        return AMapRouteResult(
            distance_meters=self._to_int(path.get("distance")),
            duration_seconds=self._to_int(path.get("duration")),
            polyline=self._join_polylines(polyline_parts),
            provider=self.provider_name,
        )

    def _tip_from_payload(self, item: object) -> MapSearchTip | None:
        if not isinstance(item, dict):
            return None
        name = self._clean(item.get("name"))
        if not name:
            return None
        lng = lat = None
        location = self._clean(item.get("location"))
        if location and "," in location:
            lng, lat = self._parse_location(location)
        return MapSearchTip(
            id=self._clean(item.get("id")),
            name=name,
            district=self._clean(item.get("district")),
            adcode=self._clean(item.get("adcode")),
            address=self._clean(item.get("address")),
            typecode=self._clean(item.get("typecode")),
            lat=lat,
            lng=lng,
            source=self.provider_name,
        )

    def _get_json(self, path: str, params: dict[str, str]) -> dict[str, object]:
        query = parse.urlencode({**params, "key": self.settings.amap_api_key})
        url = f"https://restapi.amap.com{path}?{query}"
        req = request.Request(url, method="GET", headers={"Accept": "application/json"})
        try:
            with request.urlopen(req, timeout=self.settings.map_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"amap request failed: {exc.code} {detail}") from exc

        if str(payload.get("status")) != "1":
            info = payload.get("info") or "unknown amap error"
            raise RuntimeError(f"amap request failed: {info}")
        return payload

    def _download_static_map(self, url: str) -> str | None:
        if not self.settings.public_base_url:
            return None
        try:
            req = request.Request(url, method="GET")
            with request.urlopen(req, timeout=self.settings.map_timeout_seconds) as response:
                data = response.read()
        except Exception:
            return None
        if not data:
            return None

        target_dir = self.settings.upload_dir / "static_maps"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{uuid.uuid4().hex}.png"
        target.write_bytes(data)
        media_path = str(target.relative_to(self.settings.upload_dir))
        return f"{self.settings.public_base_url.rstrip('/')}/media/{media_path}"

    def _redacted_static_map_url(self, params: dict[str, str]) -> str:
        query = parse.urlencode({**params, "key": "[REDACTED]"})
        return f"https://restapi.amap.com/v3/staticmap?{query}"

    def _parse_location(self, location: str) -> tuple[float | None, float | None]:
        parts = location.split(",", 1)
        if len(parts) != 2:
            return None, None
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            return None, None

    def _join_polylines(self, parts: list[str]) -> str | None:
        coordinates: list[str] = []
        for part in parts:
            for coordinate in part.split(";"):
                coordinate = coordinate.strip()
                if coordinate and (not coordinates or coordinates[-1] != coordinate):
                    coordinates.append(coordinate)
        return ";".join(coordinates) if coordinates else None

    def _to_int(self, value: object) -> int | None:
        try:
            if value is None or value == "":
                return None
            return int(float(str(value)))
        except (TypeError, ValueError):
            return None

    def _clean(self, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        value = value.strip()
        if not value or value == "[]":
            return None
        return value


def build_amap_web_service(settings: Settings) -> AMapWebServiceClient:
    return AMapWebServiceClient(settings)
