from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from json import JSONDecodeError
import json
import re
from typing import Protocol
from urllib import error, request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Settings
from .schemas import PlaceSignal, TravelMode
from .storage import PetRecord


@dataclass(frozen=True, slots=True)
class TransportScheduleRequest:
    pet: PetRecord
    mode: TravelMode
    origin: PlaceSignal
    destination: PlaceSignal
    depart_after: datetime
    now: datetime
    context: str


@dataclass(frozen=True, slots=True)
class TransportScheduleCandidate:
    mode: TravelMode
    carrier: str | None
    service_number: str
    origin_name: str
    destination_name: str
    scheduled_departure: datetime
    scheduled_arrival: datetime
    terminal_or_platform: str | None = None
    source_urls: tuple[str, ...] = ()
    confidence: str = "medium"
    search_query: str | None = None
    notes: str | None = None
    reality_level: str = "web_reference_schedule"
    is_simulated: bool = True


class TransportScheduleProvider(Protocol):
    provider_name: str

    def best_candidate(self, search: TransportScheduleRequest) -> TransportScheduleCandidate | None:
        ...

    def best_itinerary(self, search: TransportScheduleRequest) -> list[TransportScheduleCandidate]:
        ...


class MockTransportScheduleProvider:
    provider_name = "mock-transport-schedule-provider"

    def best_candidate(self, search: TransportScheduleRequest) -> TransportScheduleCandidate | None:
        return None

    def best_itinerary(self, search: TransportScheduleRequest) -> list[TransportScheduleCandidate]:
        return []


class OpenAIWebSearchTransportScheduleProvider:
    provider_name = "openai-web-search-transport-schedule-provider"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.last_remote_call_succeeded = False
        self.last_remote_error = ""

    @property
    def configured(self) -> bool:
        return bool(self.settings.openai_api_key and self.settings.transport_web_search_enabled)

    def best_candidate(self, search: TransportScheduleRequest) -> TransportScheduleCandidate | None:
        candidates = self.best_itinerary(search)
        return candidates[0] if candidates else None

    def best_itinerary(self, search: TransportScheduleRequest) -> list[TransportScheduleCandidate]:
        self.last_remote_call_succeeded = False
        self.last_remote_error = ""
        if not self.configured or search.mode not in {TravelMode.flight, TravelMode.train}:
            return []

        try:
            response = self._post_json("/responses", self.build_responses_payload(search))
            data = self._extract_json_object(response)
            candidates = self._candidates_from_data(search, data)
        except Exception as exc:
            self.last_remote_error = self._redact_error(str(exc))
            return []

        self.last_remote_call_succeeded = bool(candidates)
        return candidates

    def build_responses_payload(self, search: TransportScheduleRequest) -> dict[str, object]:
        return {
            "model": self.settings.transport_search_model,
            "tools": [{"type": "web_search_preview"}],
            "tool_choice": "auto",
            "text": {
                "verbosity": "low",
                "format": {
                    "type": "json_schema",
                    "name": "transport_schedule_itinerary",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "found",
                            "mode",
                            "itinerary_summary",
                            "confidence",
                            "notes",
                            "segments",
                        ],
                        "properties": {
                            "found": {"type": "boolean"},
                            "mode": {"type": "string", "enum": ["flight", "train"]},
                            "itinerary_summary": {"type": ["string", "null"]},
                            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                            "notes": {"type": ["string", "null"]},
                            "segments": {
                                "type": "array",
                                "minItems": 1,
                                "maxItems": 4,
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": [
                                        "mode",
                                        "carrier",
                                        "service_number",
                                        "origin_name",
                                        "origin_city",
                                        "destination_name",
                                        "destination_city",
                                        "scheduled_departure",
                                        "scheduled_arrival",
                                        "terminal_or_platform",
                                        "source_urls",
                                        "confidence",
                                        "notes",
                                    ],
                                    "properties": {
                                        "mode": {"type": "string", "enum": ["flight", "train"]},
                                        "carrier": {"type": ["string", "null"]},
                                        "service_number": {"type": ["string", "null"]},
                                        "origin_name": {"type": ["string", "null"]},
                                        "origin_city": {"type": ["string", "null"]},
                                        "destination_name": {"type": ["string", "null"]},
                                        "destination_city": {"type": ["string", "null"]},
                                        "scheduled_departure": {"type": ["string", "null"]},
                                        "scheduled_arrival": {"type": ["string", "null"]},
                                        "terminal_or_platform": {"type": ["string", "null"]},
                                        "source_urls": {"type": "array", "items": {"type": "string"}},
                                        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                                        "notes": {"type": ["string", "null"]},
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "input": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": json.dumps(self._context_payload(search), ensure_ascii=False)},
            ],
        }

    def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        url = f"{self.settings.openai_base_url.rstrip('/')}{path}"
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(req, timeout=self.settings.transport_search_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"transport web search failed: {exc.code} {detail}") from exc

    def _extract_json_object(self, response: dict[str, object]) -> dict[str, object]:
        candidate = response.get("output_text")
        if isinstance(candidate, str):
            return self._parse_json_candidate(candidate)

        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, str):
                return self._parse_json_candidate(content)

        output = response.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for content_item in content:
                    if not isinstance(content_item, dict):
                        continue
                    text = content_item.get("text") or content_item.get("output_text")
                    if isinstance(text, str):
                        return self._parse_json_candidate(text)

        raise ValueError("web search response did not contain parseable JSON")

    def _parse_json_candidate(self, value: str) -> dict[str, object]:
        text = value.strip()
        if text.startswith("```"):
            text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            parsed = json.loads(text)
        except JSONDecodeError as exc:
            raise ValueError("web search returned non-json text") from exc
        if not isinstance(parsed, dict):
            raise ValueError("web search returned non-object JSON")
        return parsed

    def _candidates_from_data(
        self,
        search: TransportScheduleRequest,
        data: dict[str, object],
    ) -> list[TransportScheduleCandidate]:
        if data.get("found") is not True:
            return []
        mode = TravelMode(str(data.get("mode") or search.mode.value))
        if mode not in {TravelMode.flight, TravelMode.train}:
            return []

        segments = data.get("segments")
        if isinstance(segments, list):
            candidates: list[TransportScheduleCandidate] = []
            for index, segment in enumerate(segments):
                if not isinstance(segment, dict):
                    continue
                candidate = self._candidate_from_segment_data(search, segment, index, len(segments))
                if candidate:
                    candidates.append(candidate)
            return candidates

        candidate = self._candidate_from_segment_data(search, data, 0, 1)
        return [candidate] if candidate else []

    def _candidate_from_segment_data(
        self,
        search: TransportScheduleRequest,
        data: dict[str, object],
        index: int,
        total: int,
    ) -> TransportScheduleCandidate | None:
        mode = TravelMode(str(data.get("mode") or search.mode.value))
        if mode not in {TravelMode.flight, TravelMode.train}:
            return None
        service_number = self._clean_required_string(data.get("service_number"))
        origin_city = self._clean_optional_string(data.get("origin_city")) or search.origin.city
        destination_city = self._clean_optional_string(data.get("destination_city")) or search.destination.city
        departure = self._parse_datetime(
            data.get("scheduled_departure"),
            fallback_date=search.depart_after,
            timezone_name=self._timezone_for_city(origin_city),
        )
        arrival_fallback_date = departure or search.depart_after
        arrival = self._parse_datetime(
            data.get("scheduled_arrival"),
            fallback_date=arrival_fallback_date,
            timezone_name=self._timezone_for_city(destination_city),
        )
        if departure and arrival and arrival <= departure:
            arrival = arrival + timedelta(days=1)
        if not service_number or not departure or not arrival or arrival <= departure:
            return None

        source_urls = tuple(
            url.strip()
            for url in data.get("source_urls", [])
            if isinstance(url, str) and url.strip().startswith(("http://", "https://"))
        )
        return TransportScheduleCandidate(
            mode=mode,
            carrier=self._clean_optional_string(data.get("carrier")),
            service_number=service_number,
            origin_name=self._clean_optional_string(data.get("origin_name")) or search.origin.name,
            destination_name=self._clean_optional_string(data.get("destination_name")) or search.destination.name,
            scheduled_departure=departure,
            scheduled_arrival=arrival,
            terminal_or_platform=self._clean_optional_string(data.get("terminal_or_platform")),
            source_urls=source_urls,
            confidence=self._normalized_confidence(data.get("confidence")),
            search_query=self._search_query(search),
            notes=self._segment_notes(data.get("notes"), index, total),
        )

    def _parse_datetime(
        self,
        value: object,
        *,
        fallback_date: datetime,
        timezone_name: str | None,
    ) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            parsed_time = self._parse_local_time(text)
            if not parsed_time:
                return None
            tzinfo = self._zoneinfo(timezone_name)
            local_date = fallback_date.astimezone(tzinfo).date()
            return datetime.combine(local_date, parsed_time, tzinfo=tzinfo)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=self._zoneinfo(timezone_name))
        return parsed

    def _parse_local_time(self, value: str) -> time | None:
        match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", value.strip())
        if not match:
            return None
        try:
            hour = int(match.group(1))
            minute = int(match.group(2))
        except ValueError:
            return None
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        return time(hour=hour, minute=minute)

    def _zoneinfo(self, timezone_name: str | None) -> timezone | ZoneInfo:
        if not timezone_name:
            return timezone.utc
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            return timezone.utc

    def _timezone_for_city(self, city: str) -> str | None:
        mapping = {
            "厦门": "Asia/Shanghai",
            "北京": "Asia/Shanghai",
            "上海": "Asia/Shanghai",
            "广州": "Asia/Shanghai",
            "深圳": "Asia/Shanghai",
            "杭州": "Asia/Shanghai",
            "成都": "Asia/Shanghai",
            "重庆": "Asia/Shanghai",
            "南京": "Asia/Shanghai",
            "武汉": "Asia/Shanghai",
            "西安": "Asia/Shanghai",
            "香港": "Asia/Hong_Kong",
            "台北": "Asia/Taipei",
            "多哈": "Asia/Qatar",
            "迪拜": "Asia/Dubai",
            "阿布扎比": "Asia/Dubai",
            "伊斯坦布尔": "Europe/Istanbul",
            "新加坡": "Asia/Singapore",
            "曼谷": "Asia/Bangkok",
            "首尔": "Asia/Seoul",
            "洛杉矶": "America/Los_Angeles",
            "东京": "Asia/Tokyo",
            "巴黎": "Europe/Paris",
            "伦敦": "Europe/London",
            "纽约": "America/New_York",
        }
        return mapping.get(city)

    def _context_payload(self, search: TransportScheduleRequest) -> dict[str, object]:
        return {
            "need": (
                "one realistic public transport itinerary; direct is preferred, but one or two transfer "
                "segments are acceptable when there is no direct service; no booking, no price, no seat availability"
            ),
            "mode": search.mode.value,
            "origin": {
                "name": search.origin.name,
                "city": search.origin.city,
                "lat": search.origin.lat,
                "lng": search.origin.lng,
            },
            "destination": {
                "name": search.destination.name,
                "city": search.destination.city,
                "lat": search.destination.lat,
                "lng": search.destination.lng,
            },
            "depart_after": search.depart_after.isoformat(),
            "now": search.now.isoformat(),
            "context": search.context,
            "pet": {
                "name": search.pet.name,
                "type": search.pet.pet_type.value,
            },
            "query_hint": self._search_query(search),
        }

    def _search_query(self, search: TransportScheduleRequest) -> str:
        label = "flight" if search.mode == TravelMode.flight else "train"
        return (
            f"{search.origin.city} to {search.destination.city} {label} direct or connecting "
            f"schedule number departure arrival"
        )

    def _system_prompt(self) -> str:
        return (
            "You search public web pages for one realistic transport itinerary for PetSoul. Prefer a direct "
            "flight or train when public sources support it. If no direct service is apparent, return a "
            "reasonable connecting itinerary with each segment's service number and scheduled departure/arrival "
            "time. You may use airline, railway, airport, official tourism, reputable timetable, travel, or "
            "ticketing websites only as public timetable references. Do not collect, infer, or return prices, "
            "seat availability, booking status, purchase links, or ticketing advice. If service numbers and "
            "times are not supported by public sources, set found=false. Prefer ISO 8601 datetimes with timezone "
            "offsets. If the source only publishes local HH:MM times, return those exact local times and city "
            "names for timezone normalization. Return only JSON matching the schema."
        )

    def _clean_required_string(self, value: object) -> str | None:
        cleaned = self._clean_optional_string(value)
        return cleaned if cleaned else None

    def _clean_optional_string(self, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value or None

    def _normalized_confidence(self, value: object) -> str:
        if value in {"low", "medium", "high"}:
            return str(value)
        return "medium"

    def _segment_notes(self, value: object, index: int, total: int) -> str | None:
        note = self._clean_optional_string(value)
        if total <= 1:
            return note
        prefix = f"中转行程第 {index + 1}/{total} 段；"
        return f"{prefix}{note}" if note else prefix.rstrip("；")

    def _redact_error(self, message: str) -> str:
        if self.settings.openai_api_key:
            return message.replace(self.settings.openai_api_key, "[REDACTED]")
        return message


def build_transport_schedule_provider(settings: Settings | None = None) -> TransportScheduleProvider:
    if settings and (
        settings.transport_schedule_provider == "openai" or settings.transport_web_search_enabled
    ):
        return OpenAIWebSearchTransportScheduleProvider(settings)
    return MockTransportScheduleProvider()
