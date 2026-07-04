from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from urllib import error, parse, request

from .config import Settings
from .schemas import PlaceSignal, ReverseGeocodeResult, TravelMode


@dataclass(frozen=True, slots=True)
class GoogleRouteResult:
    distance_meters: int | None
    duration_seconds: int | None
    polyline: str | None
    provider: str


class GoogleMapsServiceClient:
    provider_name = "google-maps-service-client"

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.google_maps_api_key)

    def places_nearby(
        self,
        *,
        city_name: str,
        lat: float,
        lng: float,
        theme: str = "street",
        radius: int = 3500,
        limit: int = 5,
    ) -> list[PlaceSignal]:
        if not self.configured:
            return []
        payload = {
            "includedTypes": self._place_types_for_theme(theme),
            "maxResultCount": max(1, min(20, limit * 3)),
            "rankPreference": "POPULARITY",
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": max(500, min(50_000, radius)),
                }
            },
            "languageCode": "zh-CN",
        }
        response = self._post_json(
            "https://places.googleapis.com/v1/places:searchNearby",
            payload,
            headers={
                "X-Goog-Api-Key": self.settings.google_maps_api_key or "",
                "X-Goog-FieldMask": (
                    "places.id,places.displayName,places.formattedAddress,places.location,"
                    "places.rating,places.userRatingCount,places.primaryType,places.types,"
                    "places.priceLevel,places.regularOpeningHours,places.photos.name"
                ),
            },
        )
        places = response.get("places")
        if not isinstance(places, list):
            return []

        parsed_places: list[PlaceSignal] = []
        seen_names: set[str] = set()
        for item in places:
            if not isinstance(item, dict):
                continue
            place = self._place_from_payload(city_name, item, lat, lng)
            if not place or place.name in seen_names:
                continue
            if not self._is_relevant_place(place):
                continue
            parsed_places.append(place)
            seen_names.add(place.name)
            if len(parsed_places) >= limit:
                break
        return sorted(parsed_places, key=lambda place: place.guide_score or 0, reverse=True)[:limit]

    def route_between(
        self,
        *,
        mode: TravelMode,
        origin_lng: float,
        origin_lat: float,
        destination_lng: float,
        destination_lat: float,
    ) -> GoogleRouteResult | None:
        if not self.configured:
            return None
        travel_mode = self._travel_mode(mode)
        if not travel_mode:
            return None
        payload: dict[str, object] = {
            "origin": {"location": {"latLng": {"latitude": origin_lat, "longitude": origin_lng}}},
            "destination": {"location": {"latLng": {"latitude": destination_lat, "longitude": destination_lng}}},
            "travelMode": travel_mode,
            "computeAlternativeRoutes": False,
            "languageCode": "zh-CN",
            "units": "METRIC",
        }
        if mode == TravelMode.drive:
            payload["routingPreference"] = "TRAFFIC_AWARE"
        response = self._post_json(
            "https://routes.googleapis.com/directions/v2:computeRoutes",
            payload,
            headers={
                "X-Goog-Api-Key": self.settings.google_maps_api_key or "",
                "X-Goog-FieldMask": "routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline",
            },
        )
        routes = response.get("routes")
        if not isinstance(routes, list) or not routes:
            return None
        first = routes[0]
        if not isinstance(first, dict):
            return None
        polyline = first.get("polyline")
        encoded_polyline = polyline.get("encodedPolyline") if isinstance(polyline, dict) else None
        return GoogleRouteResult(
            distance_meters=self._to_int(first.get("distanceMeters")),
            duration_seconds=self._duration_to_seconds(first.get("duration")),
            polyline=encoded_polyline if isinstance(encoded_polyline, str) else None,
            provider=self.provider_name,
        )

    def reverse_geocode(self, *, lat: float, lng: float) -> ReverseGeocodeResult | None:
        if not self.configured:
            return None
        query = parse.urlencode(
            {
                "latlng": f"{lat},{lng}",
                "key": self.settings.google_maps_api_key,
                "language": "zh-CN",
            }
        )
        payload = self._get_json(f"https://maps.googleapis.com/maps/api/geocode/json?{query}")
        if str(payload.get("status")) != "OK":
            return None
        results = payload.get("results")
        if not isinstance(results, list) or not results:
            return None
        first = results[0]
        if not isinstance(first, dict):
            return None
        components = first.get("address_components")
        if not isinstance(components, list):
            components = []
        by_type = self._components_by_type(components)
        return ReverseGeocodeResult(
            formatted_address=str(first.get("formatted_address") or ""),
            province=self._component_name(by_type, "administrative_area_level_1"),
            city=self._component_name(by_type, "locality") or self._component_name(by_type, "postal_town"),
            district=self._component_name(by_type, "sublocality") or self._component_name(by_type, "sublocality_level_1"),
            township=None,
            adcode=None,
            street=self._component_name(by_type, "route"),
            number=self._component_name(by_type, "street_number"),
            poi_name=None,
            source=self.provider_name,
        )

    def config_snapshot(self) -> dict[str, str | bool]:
        return {
            "provider": self.provider_name,
            "configured": self.configured,
            "places_api": self.configured,
            "routes_api": self.configured,
            "geocoding_api": self.configured,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _post_json(self, url: str, payload: dict[str, object], headers: dict[str, str]) -> dict[str, object]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={**headers, "Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with request.urlopen(req, timeout=self.settings.map_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"google maps request failed: {exc.code} {self._redact(detail)}") from exc

    def _get_json(self, url: str) -> dict[str, object]:
        req = request.Request(url, method="GET", headers={"Accept": "application/json"})
        try:
            with request.urlopen(req, timeout=self.settings.map_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"google maps request failed: {exc.code} {self._redact(detail)}") from exc

    def _place_from_payload(self, city_name: str, item: dict[str, object], anchor_lat: float, anchor_lng: float) -> PlaceSignal | None:
        display_name = item.get("displayName")
        name = display_name.get("text") if isinstance(display_name, dict) else None
        location = item.get("location")
        if not isinstance(name, str) or not isinstance(location, dict):
            return None
        lat = self._to_float(location.get("latitude"))
        lng = self._to_float(location.get("longitude"))
        if lat is None or lng is None:
            return None
        primary_type = str(item.get("primaryType") or "")
        types = item.get("types")
        if not isinstance(types, list):
            types = []
        category = self._category_for(name, primary_type, [str(value) for value in types])
        rating = self._to_float(item.get("rating"))
        user_rating_count = self._to_int(item.get("userRatingCount"))
        distance = self._rough_distance_meters(anchor_lat, anchor_lng, lat, lng)
        guide_score = self._guide_score(
            category=category,
            rating=rating,
            user_rating_count=user_rating_count,
            distance_meters=distance,
        )
        return PlaceSignal(
            id=f"google-{item.get('id') or sanitize_place_id(name)}",
            name=name,
            category=category,
            city=city_name,
            lat=lat,
            lng=lng,
            activity_hint=self._activity_hint(name, category),
            detail_hint=self._detail_hint(name, category),
            source=self.provider_name,
            rating=rating,
            distance_meters=distance,
            guide_score=guide_score,
            guide_reason=self._guide_reason(name, category, rating, user_rating_count, distance),
            raw={
                "provider": "google",
                "primary_type": primary_type,
                "types": types,
                "formatted_address": item.get("formattedAddress"),
                "user_rating_count": user_rating_count,
                "photo_count": len(item.get("photos") or []) if isinstance(item.get("photos"), list) else 0,
            },
        )

    def _place_types_for_theme(self, theme: str) -> list[str]:
        normalized = theme.strip().lower()
        if normalized in {"coffee", "cafe", "咖啡", "甜品"}:
            return ["cafe", "bakery"]
        if normalized in {"night", "late", "深夜", "夜间"}:
            return ["restaurant", "cafe", "convenience_store", "store"]
        if normalized in {"photo", "selfie", "拍照", "照片"}:
            return ["tourist_attraction", "park", "cafe", "shopping_mall"]
        if normalized in {"rain", "rainy", "雨天", "躲雨"}:
            return ["cafe", "shopping_mall", "store", "museum"]
        if normalized in {"local", "street", "扫街", "小吃", "烟火"}:
            return ["restaurant", "cafe", "store", "park", "tourist_attraction"]
        return ["restaurant", "cafe", "park", "tourist_attraction", "store"]

    def _travel_mode(self, mode: TravelMode) -> str | None:
        if mode == TravelMode.walk:
            return "WALK"
        if mode == TravelMode.drive:
            return "DRIVE"
        if mode == TravelMode.transit:
            return "TRANSIT"
        return None

    def _category_for(self, name: str, primary_type: str, types: list[str]) -> str:
        text = " ".join([name, primary_type, *types]).lower()
        if any(token in text for token in ("cafe", "coffee", "bakery")):
            return "cafe"
        if any(token in text for token in ("restaurant", "food", "meal")):
            return "food"
        if any(token in text for token in ("park", "garden")):
            return "park"
        if any(token in text for token in ("store", "shopping", "mall", "convenience")):
            return "shop"
        if any(token in text for token in ("tourist", "museum", "stadium")):
            return "sight"
        return "place"

    def _is_relevant_place(self, place: PlaceSignal) -> bool:
        return place.category in {"food", "cafe", "shop", "park", "sight", "place"}

    def _activity_hint(self, name: str, category: str) -> str:
        hints = {
            "cafe": f"在 {name} 靠窗坐下喝一杯店里的特色咖啡",
            "food": f"在 {name} 看了菜单，点了一份招牌餐食",
            "park": f"在 {name} 找到一小块可以玩一会儿的地方",
            "shop": f"走进 {name} 挑了一个小小的补给品",
            "sight": f"在 {name} 里面或附近听见城市的声音",
        }
        return hints.get(category, f"路过 {name} 时停下来认真看了看")

    def _detail_hint(self, name: str, category: str) -> str:
        hints = {
            "cafe": "适合短暂停靠、发回照片或写一张小卡片。",
            "food": "这里有真实的本地味道，TA 可以进店看菜单，选择店里有代表性的菜或小吃。",
            "park": "适合散步、玩一会儿、停留和恢复精力。",
            "shop": "本地生活感强，适合让 TA 看见真实城市细节。",
            "sight": "这里可以成为一段城市记忆，TA 会先观察周围再决定停多久。",
        }
        return hints.get(category, f"{name} 是附近真实可抵达的地点，可作为旅程中的短暂停留点。")

    def _guide_score(
        self,
        *,
        category: str,
        rating: float | None,
        user_rating_count: int | None,
        distance_meters: int | None,
    ) -> float:
        score = 50.0
        score += {"cafe": 18.0, "park": 14.0, "food": 13.0, "sight": 10.0, "shop": 8.0}.get(category, 0.0)
        if rating is not None:
            score += max(0.0, min(22.0, (rating - 3.0) * 11.0))
        if user_rating_count is not None:
            if user_rating_count >= 1_000:
                score += 8
            elif user_rating_count >= 200:
                score += 5
            elif user_rating_count >= 50:
                score += 3
        if distance_meters is not None:
            if distance_meters <= 800:
                score += 7
            elif distance_meters <= 2_000:
                score += 4
        return round(score, 1)

    def _guide_reason(
        self,
        name: str,
        category: str,
        rating: float | None,
        user_rating_count: int | None,
        distance_meters: int | None,
    ) -> str:
        parts = [self._detail_hint(name, category)]
        if rating is not None:
            parts.append(f"Google 评分 {rating:.1f}")
        if user_rating_count:
            parts.append(f"{user_rating_count} 条评价")
        if distance_meters is not None:
            parts.append(f"距离约 {distance_meters} 米")
        return "；".join(parts)

    def _components_by_type(self, components: list[object]) -> dict[str, dict[str, object]]:
        result: dict[str, dict[str, object]] = {}
        for component in components:
            if not isinstance(component, dict):
                continue
            types = component.get("types")
            if not isinstance(types, list):
                continue
            for item in types:
                if isinstance(item, str):
                    result[item] = component
        return result

    def _component_name(self, components: dict[str, dict[str, object]], key: str) -> str | None:
        value = components.get(key)
        if not value:
            return None
        name = value.get("long_name")
        return name if isinstance(name, str) and name else None

    def _duration_to_seconds(self, value: object) -> int | None:
        if not isinstance(value, str) or not value.endswith("s"):
            return None
        return self._to_int(value[:-1])

    def _rough_distance_meters(self, origin_lat: float, origin_lng: float, lat: float, lng: float) -> int:
        from math import cos, radians, sqrt

        dy = (lat - origin_lat) * 111_320
        dx = (lng - origin_lng) * 111_320 * cos(radians((lat + origin_lat) / 2))
        return int(sqrt(dx * dx + dy * dy))

    def _to_float(self, value: object) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _to_int(self, value: object) -> int | None:
        try:
            if value is None or value == "":
                return None
            return int(float(str(value)))
        except (TypeError, ValueError):
            return None

    def _redact(self, message: str) -> str:
        if self.settings.google_maps_api_key:
            return message.replace(self.settings.google_maps_api_key, "[REDACTED]")
        return message


def build_google_maps_service(settings: Settings) -> GoogleMapsServiceClient:
    return GoogleMapsServiceClient(settings)


def sanitize_place_id(name: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in name).strip("-") or "place"
