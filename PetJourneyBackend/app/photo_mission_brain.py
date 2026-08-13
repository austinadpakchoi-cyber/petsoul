from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from json import JSONDecodeError
import json
from typing import Protocol
from urllib import error, request

from .config import Settings
from .schemas import PhotoPerspective, PlaceSignal, WorldActivity
from .storage import PetRecord


@dataclass(frozen=True, slots=True)
class PhotoMissionContext:
    pet: PetRecord
    place: PlaceSignal
    activity: WorldActivity | None
    weather: str
    now: datetime
    time_of_day: str
    worldcup_event: bool = False


@dataclass(frozen=True, slots=True)
class PhotoMissionDraft:
    interaction_type: str
    title: str
    detail: str
    pet_action: str
    emotional_tone: str
    dwell_minutes: int
    camera_perspective: PhotoPerspective
    scene_anchor: str
    landmark_hints: list[str]
    local_detail_hints: list[str]
    crowd_hints: list[str]
    image_prompt: str
    postcard_text: str
    safety_notes: list[str]
    model: str
    provider: str


class PhotoMissionBrain(Protocol):
    provider_name: str

    def draft(self, context: PhotoMissionContext) -> PhotoMissionDraft | None:
        ...

    def config_snapshot(self) -> dict[str, str | bool | float]:
        ...


class MockPhotoMissionBrain:
    provider_name = "mock-photo-mission-brain"

    def __init__(self, settings: Settings):
        self.settings = settings

    def draft(self, context: PhotoMissionContext) -> PhotoMissionDraft | None:
        return None

    def config_snapshot(self) -> dict[str, str | bool | float]:
        return {
            "provider": self.provider_name,
            "photo_mission_model": self.settings.photo_mission_model,
            "remote_configured": False,
            "remote_call_active": False,
            "remote_call_enabled": False,
            "last_remote_success": False,
            "last_remote_error": "",
            "timeout_seconds": self.settings.agent_timeout_seconds,
        }


class OpenAICompatiblePhotoMissionBrain:
    provider_name = "openai-compatible-photo-mission-brain"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.last_remote_call_succeeded = False
        self.last_remote_error = ""
        self.last_remote_prompt_tokens = 0
        self.last_remote_completion_tokens = 0

    def draft(self, context: PhotoMissionContext) -> PhotoMissionDraft | None:
        self.last_remote_call_succeeded = False
        self.last_remote_error = ""
        if not self.settings.openai_api_key:
            self.last_remote_error = "OpenAI-compatible API key is not configured"
            return None

        try:
            payload = self.build_chat_completions_payload(context)
            response = self._post_json("/chat/completions", payload)
            self._record_usage(response)
            data = self._extract_json_object(response)
        except Exception as chat_error:
            self.last_remote_error = self._redact_error(str(chat_error))
            return None

        try:
            draft = self._draft_from_data(data, response, context.pet)
        except (TypeError, ValueError, KeyError) as exc:
            self.last_remote_error = self._redact_error(str(exc))
            return None
        if not self._is_productive_draft(draft):
            self.last_remote_error = "model returned an unavailable or non-actionable photo mission"
            return None

        self.last_remote_call_succeeded = True
        return draft

    def config_snapshot(self) -> dict[str, str | bool | float]:
        return {
            "provider": self.provider_name,
            "photo_mission_model": self.settings.photo_mission_model,
            "remote_configured": bool(self.settings.openai_api_key),
            "remote_call_active": bool(self.settings.openai_api_key),
            "remote_call_enabled": bool(self.settings.openai_api_key),
            "base_url": self.settings.openai_base_url.rstrip("/"),
            "last_remote_success": self.last_remote_call_succeeded,
            "last_remote_error": self.last_remote_error,
            "timeout_seconds": self.settings.agent_timeout_seconds,
            "last_remote_prompt_tokens": float(self.last_remote_prompt_tokens),
            "last_remote_completion_tokens": float(self.last_remote_completion_tokens),
        }

    def build_chat_completions_payload(self, context: PhotoMissionContext) -> dict[str, object]:
        return {
            "model": self.settings.photo_mission_model,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": json.dumps(self._context_payload(context), ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": self.settings.photo_mission_max_tokens,
        }

    def _json_schema(self) -> dict[str, object]:
        string_array = {
            "type": "array",
            "items": {"type": "string"},
        }
        return {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "interaction_type",
                "title",
                "detail",
                "pet_action",
                "emotional_tone",
                "dwell_minutes",
                "camera_perspective",
                "scene_anchor",
                "landmark_hints",
                "local_detail_hints",
                "crowd_hints",
                "image_prompt",
                "postcard_text",
                "safety_notes",
            ],
            "properties": {
                "interaction_type": {"type": "string"},
                "title": {"type": "string"},
                "detail": {"type": "string"},
                "pet_action": {"type": "string"},
                "emotional_tone": {"type": "string"},
                "dwell_minutes": {"type": "integer"},
                "camera_perspective": {
                    "type": "string",
                    "enum": [
                        PhotoPerspective.first_person_selfie.value,
                        PhotoPerspective.passerby_third_person.value,
                        PhotoPerspective.communicator_view.value,
                    ],
                },
                "scene_anchor": {"type": "string"},
                "landmark_hints": string_array,
                "local_detail_hints": string_array,
                "crowd_hints": string_array,
                "image_prompt": {"type": "string"},
                "postcard_text": {"type": "string"},
                "safety_notes": string_array,
            },
        }

    def _system_prompt(self) -> str:
        return (
            "You are PetSoul's Photo Mission Brain. Your job is not to write a generic image prompt. "
            "You convert the pet agent's current real-world context into a structured photo mission for the image generator. "
            "The pet is autonomous in a parallel-world emotional companion simulation; the owner does not command its feelings or route. "
            "Use the provided place, public map/place details, weather, current activity, pet DNA, and time. "
            "Invent only plausible local visual details; never require a place that is not in the context. "
            "For cafes, restaurants, food stalls, bakeries, tea shops, and convenience stores, make the pet participate in normal human city life: going inside, reading the menu, noticing what nearby people order, and choosing a signature coffee, seasonal drink, local dish, snack, dessert, or small purchase based on the place name and public metadata. "
            "Do not over-constrain food scenes as safe pet food, tiny portions, warm water, or only smelling outside; this is a parallel-world simulation, not real pet feeding advice. "
            "Never mention provider names, API names, source fields, raw IDs, or internal implementation details in title, detail, pet_action, hints, or postcard_text. "
            "The image_prompt must be directly usable by the image generator and must ask it to use the reference pet image as identity guidance for a full new generated photo. "
            "Default every mission to a first-person pet selfie from the pet's own communicator/phone: close pet face, paw, wing, nose, whiskers, collar, or chest can be in the foreground, with the real place behind. "
            "Even for landmarks, stadiums, airports, stations, and scenic spots, prefer a candid handheld pet selfie over a third-person postcard composition. "
            "Do not ask for cutout, paste, sticker, collage, overlay, or compositing; ask for coherent second-creation with natural lighting, shadows, scale, and perspective. "
            "If place.photo_url_available is true, assume the image generator may receive an additional place_environment reference image; use it for location layout, storefront/scenery, lighting, and material details, not for pet identity. "
            "Never output unavailable, cannot_generate, insufficient_information, or a refusal-style mission; choose the best plausible photo mission from the context. "
            "When the scene involves sports or public events, use generic crowd colors and atmosphere, but no official logos, readable marks, real athletes, or public figures. "
            "Do not claim medical, religious, or supernatural proof. "
            "The user-facing postcard_text should feel like a small message from the pet, warm and restrained. "
            "If the pet addresses the owner directly, use pet.owner_title exactly. Never default to 宝宝, 宝贝, darling, or baby unless owner_title is exactly that. "
            "Respond with a single JSON object only that matches this schema exactly: "
            + json.dumps(self._json_schema(), ensure_ascii=False)
            + ". Do not wrap the JSON in markdown fences and do not add commentary outside the JSON."
        )

    def _context_payload(self, context: PhotoMissionContext) -> dict[str, object]:
        pet = context.pet
        place = context.place
        activity = context.activity
        return {
            "pet": {
                "id": pet.pet_id,
                "name": pet.name,
                "type": pet.pet_type.value,
                "owner_title": pet.dna.owner_title,
                "personality": pet.dna.personality,
                "favorite_places": pet.dna.favorite_places,
                "hobbies": pet.dna.hobby,
                "catchphrase": pet.dna.catchphrase,
                "voice_style": pet.dna.voice_style,
                "has_reference_photo": bool(pet.photo_path),
            },
            "current_activity": None
            if activity is None
            else {
                "kind": activity.kind,
                "status": activity.status.value,
                "title": activity.title,
                "detail": activity.detail,
                "city": activity.city,
                "place_name": activity.place_name,
                "lat": activity.lat,
                "lng": activity.lng,
                "dwell_minutes": activity.dwell_minutes,
                "can_generate_photo": activity.can_generate_photo,
                "can_send_postcard": activity.can_send_postcard,
            },
            "place": {
                "id": place.id,
                "name": place.name,
                "category": place.category,
                "city": place.city,
                "lat": place.lat,
                "lng": place.lng,
                "activity_hint": place.activity_hint,
                "detail_hint": place.detail_hint,
                "photo_url_available": bool(place.photo_url),
                "rating": place.rating,
                "cost": place.cost,
                "business_area": place.business_area,
                "distance_meters": place.distance_meters,
                "guide_score": place.guide_score,
                "guide_reason": place.guide_reason,
                "public_place_metadata": self._compact_raw(place.raw),
            },
            "environment": {
                "weather": context.weather,
                "time_of_day": context.time_of_day,
                "iso_time": context.now.isoformat(),
                "worldcup_event": context.worldcup_event,
            },
            "product_rules": [
                "This is a parallel-world emotional companion simulation.",
                "The pet chooses and experiences the place autonomously.",
                "The generated image should make the real place recognizable through visual clues.",
                "First-person pet selfies are the default; the place should be recognizable behind the pet rather than replacing the pet with a pasted landmark pose.",
                "For food and drink places, use place name, category, hints, guide_reason, and public metadata to pick signature menu details; TA can go inside and share the human-world dining/cafe atmosphere.",
                "Avoid official logos, readable brand marks, real athletes, public figures, religious proof, and medical claims.",
            ],
        }

    def _compact_raw(self, raw: dict[str, object]) -> dict[str, object]:
        keep = {"type", "address", "tag", "keytag", "rectag", "opentime_today", "opentime_week"}
        compact: dict[str, object] = {}
        for key in keep:
            value = raw.get(key)
            if value is None:
                continue
            compact[key] = str(value)[:180]
        return compact

    def _record_usage(self, response: dict[str, object]) -> None:
        usage = response.get("usage")
        if isinstance(usage, dict):
            self.last_remote_prompt_tokens = int(usage.get("prompt_tokens") or 0)
            self.last_remote_completion_tokens = int(usage.get("completion_tokens") or 0)

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
            with request.urlopen(req, timeout=self.settings.agent_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"photo mission relay request failed: {exc.code} {detail}") from exc

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

        raise ValueError("model response did not contain parseable JSON")

    def _parse_json_candidate(self, value: str) -> dict[str, object]:
        text = value.strip()
        if text.startswith("```"):
            text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            parsed = json.loads(text)
        except JSONDecodeError as exc:
            raise ValueError("model returned non-json text") from exc
        if not isinstance(parsed, dict):
            raise ValueError("model returned non-object JSON")
        return parsed

    def _draft_from_data(self, data: dict[str, object], response: dict[str, object], pet: PetRecord) -> PhotoMissionDraft:
        return PhotoMissionDraft(
            interaction_type=self._required_string(data, "interaction_type"),
            title=self._clean_owner_title(self._required_string(data, "title"), pet),
            detail=self._clean_owner_title(self._required_string(data, "detail"), pet),
            pet_action=self._clean_owner_title(self._required_string(data, "pet_action"), pet),
            emotional_tone=self._clean_owner_title(self._required_string(data, "emotional_tone"), pet),
            dwell_minutes=self._bounded_int(data.get("dwell_minutes"), minimum=5, maximum=240, fallback=25),
            camera_perspective=PhotoPerspective(self._required_string(data, "camera_perspective")),
            scene_anchor=self._clean_owner_title(self._required_string(data, "scene_anchor"), pet),
            landmark_hints=[self._clean_owner_title(item, pet) for item in self._string_list(data.get("landmark_hints"), limit=6)],
            local_detail_hints=[self._clean_owner_title(item, pet) for item in self._string_list(data.get("local_detail_hints"), limit=8)],
            crowd_hints=[self._clean_owner_title(item, pet) for item in self._string_list(data.get("crowd_hints"), limit=6)],
            image_prompt=self._clean_owner_title(self._required_string(data, "image_prompt"), pet),
            postcard_text=self._clean_owner_title(self._required_string(data, "postcard_text"), pet),
            safety_notes=[self._clean_owner_title(item, pet) for item in self._string_list(data.get("safety_notes"), limit=8)],
            model=str(response.get("model") or self.settings.photo_mission_model),
            provider=self.provider_name,
        )

    def _is_productive_draft(self, draft: PhotoMissionDraft) -> bool:
        joined = " ".join(
            [
                draft.interaction_type,
                draft.title,
                draft.detail,
                draft.pet_action,
                draft.image_prompt,
                draft.postcard_text,
            ]
        ).lower()
        blocked = {
            "unavailable",
            "cannot_generate",
            "cannot generate",
            "insufficient_information",
            "insufficient information",
            "not enough information",
            "无法生成",
            "不可用",
            "信息不足",
            "不能生成",
        }
        if any(token in joined for token in blocked):
            return False
        if len(draft.image_prompt) < 160:
            return False
        if not draft.landmark_hints and not draft.local_detail_hints:
            return False
        return True

    def _required_string(self, data: dict[str, object], key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"model response missing {key}")
        return value.strip()

    def _string_list(self, value: object, *, limit: int) -> list[str]:
        if not isinstance(value, list):
            return []
        items: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                items.append(item.strip())
            if len(items) >= limit:
                break
        return items

    def _bounded_int(self, value: object, *, minimum: int, maximum: int, fallback: int) -> int:
        if isinstance(value, bool):
            return fallback
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return fallback
        return min(max(parsed, minimum), maximum)

    def _clean_owner_title(self, text: str, pet: object) -> str:
        owner_title = getattr(getattr(pet, "dna", None), "owner_title", None)
        clean_title = " ".join(str(owner_title or "").strip().split())
        if not clean_title or clean_title in {"宝宝", "宝贝"}:
            return text
        for token in ("宝宝", "宝贝", "baby", "Baby", "darling", "Darling"):
            text = text.replace(token, clean_title)
        return text

    def _redact_error(self, message: str) -> str:
        if self.settings.openai_api_key:
            return message.replace(self.settings.openai_api_key, "[REDACTED]")
        return message


def build_photo_mission_brain(settings: Settings) -> PhotoMissionBrain:
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return OpenAICompatiblePhotoMissionBrain(settings)
    return MockPhotoMissionBrain(settings)
