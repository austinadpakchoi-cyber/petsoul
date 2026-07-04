from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from urllib import error, parse, request
from typing import Protocol

from .config import Settings
from .google_maps_services import GoogleMapsServiceClient
from .providers import JourneyCity, is_china_city


AMAP_CITY_ADCODES: dict[str, str] = {
    "北京": "110000",
    "上海": "310000",
    "广州": "440100",
    "深圳": "440300",
    "杭州": "330100",
    "南京": "320100",
    "苏州": "320500",
    "成都": "510100",
    "重庆": "500000",
    "西安": "610100",
    "厦门": "350200",
}


class WeatherProvider(Protocol):
    provider_name: str

    def city_with_weather(self, city: JourneyCity, now: datetime | None = None) -> JourneyCity:
        ...


class MockWeatherProvider:
    provider_name = "mock-weather-provider"

    def city_with_weather(self, city: JourneyCity, now: datetime | None = None) -> JourneyCity:
        return city


class AMapWeatherProvider:
    provider_name = "amap-weather-provider"

    def __init__(self, settings: Settings, cache_ttl_seconds: int = 600):
        self.settings = settings
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._cache: dict[str, tuple[datetime, str]] = {}

    def city_with_weather(self, city: JourneyCity, now: datetime | None = None) -> JourneyCity:
        now = self._aware(now or datetime.now(timezone.utc))
        adcode = AMAP_CITY_ADCODES.get(city.name)
        if not adcode or not self.settings.amap_api_key:
            return city

        cached = self._cache.get(adcode)
        if cached and now - cached[0] < self.cache_ttl:
            return replace(city, weather=cached[1])

        try:
            weather = self._fetch_live_weather(adcode)
        except Exception:
            return city

        self._cache[adcode] = (now, weather)
        return replace(city, weather=weather)

    def _fetch_live_weather(self, adcode: str) -> str:
        payload = self._get_json(
            "/v3/weather/weatherInfo",
            {
                "city": adcode,
                "extensions": "base",
                "output": "JSON",
            },
        )
        lives = payload.get("lives")
        if not isinstance(lives, list) or not lives:
            raise RuntimeError("amap weather response missing lives")
        live = lives[0]
        if not isinstance(live, dict):
            raise RuntimeError("amap weather live item is invalid")
        return self._format_live_weather(live)

    def _format_live_weather(self, live: dict[str, object]) -> str:
        weather = self._clean(live.get("weather"))
        temperature = self._clean(live.get("temperature"))
        wind_direction = self._clean(live.get("winddirection"))
        wind_power = self._clean(live.get("windpower"))
        humidity = self._clean(live.get("humidity"))

        parts: list[str] = []
        if weather:
            parts.append(weather)
        if temperature:
            parts.append(f"{temperature}°C")
        if wind_direction and wind_power:
            parts.append(f"{wind_direction}风{wind_power}级")
        elif wind_direction:
            parts.append(f"{wind_direction}风")
        elif wind_power:
            parts.append(f"风力{wind_power}级")
        if humidity:
            parts.append(f"湿度{humidity}%")
        if not parts:
            raise RuntimeError("amap weather live item has no usable fields")
        return "，".join(parts)

    def _get_json(self, path: str, params: dict[str, str]) -> dict[str, object]:
        query = parse.urlencode({**params, "key": self.settings.amap_api_key})
        url = f"https://restapi.amap.com{path}?{query}"
        req = request.Request(url, method="GET", headers={"Accept": "application/json"})
        try:
            with request.urlopen(req, timeout=self.settings.map_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"amap weather request failed: {exc.code} {detail}") from exc

        if str(payload.get("status")) != "1":
            info = payload.get("info") or "unknown amap weather error"
            raise RuntimeError(f"amap weather request failed: {info}")
        return payload

    def _clean(self, value: object) -> str:
        if not isinstance(value, str):
            return ""
        value = value.strip()
        return "" if value in {"-", "无"} else value

    def _aware(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class GoogleWeatherProvider:
    provider_name = "google-weather-provider"

    def __init__(
        self,
        settings: Settings,
        google_client: GoogleMapsServiceClient | None = None,
        cache_ttl_seconds: int = 600,
    ):
        self.settings = settings
        self.google_client = google_client or GoogleMapsServiceClient(settings)
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._cache: dict[str, tuple[datetime, str]] = {}

    def city_with_weather(self, city: JourneyCity, now: datetime | None = None) -> JourneyCity:
        now = self._aware(now or datetime.now(timezone.utc))
        if not self.google_client.configured:
            return city

        cache_key = f"{round(city.lat, 4)},{round(city.lng, 4)}"
        cached = self._cache.get(cache_key)
        if cached and now - cached[0] < self.cache_ttl:
            return replace(city, weather=cached[1])

        try:
            weather = self._fetch_current_weather(city.lat, city.lng)
        except Exception:
            return city

        self._cache[cache_key] = (now, weather)
        return replace(city, weather=weather)

    def _fetch_current_weather(self, lat: float, lng: float) -> str:
        payload = self._get_json(
            "https://weather.googleapis.com/v1/currentConditions:lookup",
            {
                "location.latitude": str(lat),
                "location.longitude": str(lng),
                "languageCode": "zh-CN",
                "unitsSystem": "METRIC",
            },
        )
        return self._format_current_weather(payload)

    def _format_current_weather(self, payload: dict[str, object]) -> str:
        condition = payload.get("weatherCondition")
        if not isinstance(condition, dict):
            condition = {}
        description = condition.get("description")
        if not isinstance(description, dict):
            description = {}

        parts: list[str] = []
        weather_text = self._clean(description.get("text"))
        if weather_text:
            parts.append(weather_text)

        temperature = self._temperature_text(payload.get("temperature"))
        if temperature:
            parts.append(temperature)

        feels_like = self._temperature_text(payload.get("feelsLikeTemperature"))
        if feels_like and feels_like != temperature:
            parts.append(f"体感{feels_like}")

        humidity = payload.get("relativeHumidity")
        if isinstance(humidity, (int, float)):
            parts.append(f"湿度{int(round(humidity))}%")

        wind = self._wind_text(payload.get("wind"))
        if wind:
            parts.append(wind)

        uv_index = payload.get("uvIndex")
        if isinstance(uv_index, (int, float)):
            parts.append(f"UV {int(round(uv_index))}")

        if not parts:
            raise RuntimeError("google weather response has no usable fields")
        return "，".join(parts)

    def _temperature_text(self, value: object) -> str:
        if not isinstance(value, dict):
            return ""
        degrees = value.get("degrees")
        if not isinstance(degrees, (int, float)):
            return ""
        return f"{degrees:.0f}°C"

    def _wind_text(self, value: object) -> str:
        if not isinstance(value, dict):
            return ""
        direction = value.get("direction")
        if not isinstance(direction, dict):
            direction = {}
        speed = value.get("speed")
        if not isinstance(speed, dict):
            speed = {}
        direction_text = self._localized_cardinal(self._clean(direction.get("cardinal")))
        speed_value = speed.get("value")
        if direction_text and isinstance(speed_value, (int, float)):
            return f"{direction_text}风{speed_value:.0f}km/h"
        if isinstance(speed_value, (int, float)):
            return f"风速{speed_value:.0f}km/h"
        return ""

    def _get_json(self, url: str, params: dict[str, str]) -> dict[str, object]:
        query = parse.urlencode({**params, "key": self.settings.google_maps_api_key})
        req = request.Request(f"{url}?{query}", method="GET", headers={"Accept": "application/json"})
        try:
            with request.urlopen(req, timeout=self.settings.map_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"google weather request failed: {exc.code} {self._redact(detail)}") from exc

    def _redact(self, message: str) -> str:
        if self.settings.google_maps_api_key:
            return message.replace(self.settings.google_maps_api_key, "[REDACTED]")
        return message

    def _localized_cardinal(self, value: str) -> str:
        mapping = {
            "NORTH": "北",
            "NORTH_NORTHEAST": "东北偏北",
            "NORTHEAST": "东北",
            "EAST_NORTHEAST": "东北偏东",
            "EAST": "东",
            "EAST_SOUTHEAST": "东南偏东",
            "SOUTHEAST": "东南",
            "SOUTH_SOUTHEAST": "东南偏南",
            "SOUTH": "南",
            "SOUTH_SOUTHWEST": "西南偏南",
            "SOUTHWEST": "西南",
            "WEST_SOUTHWEST": "西南偏西",
            "WEST": "西",
            "WEST_NORTHWEST": "西北偏西",
            "NORTHWEST": "西北",
            "NORTH_NORTHWEST": "西北偏北",
        }
        return mapping.get(value, value)

    def _clean(self, value: object) -> str:
        if not isinstance(value, str):
            return ""
        return value.strip()

    def _aware(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class HybridWeatherProvider:
    provider_name = "hybrid-amap-google-weather-provider"

    def __init__(self, settings: Settings, google_client: GoogleMapsServiceClient | None = None):
        self.amap_provider = AMapWeatherProvider(settings)
        self.google_provider = GoogleWeatherProvider(settings, google_client=google_client)

    def city_with_weather(self, city: JourneyCity, now: datetime | None = None) -> JourneyCity:
        if is_china_city(city):
            return self.amap_provider.city_with_weather(city, now=now)
        return self.google_provider.city_with_weather(city, now=now)


def build_weather_provider(settings: Settings, google_client: GoogleMapsServiceClient | None = None) -> WeatherProvider:
    if settings.amap_api_key and settings.google_maps_api_key:
        return HybridWeatherProvider(settings, google_client=google_client)
    if settings.google_maps_api_key:
        return GoogleWeatherProvider(settings, google_client=google_client)
    if settings.amap_api_key:
        return AMapWeatherProvider(settings)
    return MockWeatherProvider()
