from __future__ import annotations

from dataclasses import dataclass
from json import JSONDecodeError
import json
from urllib import error, request
from typing import Protocol

from .config import Settings
from .providers import JourneyCity
from .schemas import JourneyStatus, PetType
from .species import species_language_style, species_surface_language_label, species_vocalization
from .storage import PetRecord


@dataclass(frozen=True, slots=True)
class AgentTurnContext:
    pet: PetRecord
    city: JourneyCity
    status: JourneyStatus | str
    trigger: str
    scene: str
    owner_visible_note: str | None = None


CONTENT_INTENTS = ("none", "moment", "postcard")


@dataclass(frozen=True, slots=True)
class AgentUtterance:
    animal_text: str
    translation: str
    tone: str
    language_style: str
    model: str
    content_intent: str = "none"


class PetAgentBrain(Protocol):
    provider_name: str

    def speak(self, context: AgentTurnContext) -> AgentUtterance:
        ...

    def config_snapshot(self) -> dict[str, str | bool | float]:
        ...


class MockPetAgentBrain:
    provider_name = "mock-pet-agent-brain"

    def __init__(self, settings: Settings):
        self.settings = settings

    def speak(self, context: AgentTurnContext) -> AgentUtterance:
        tone = context.trigger
        return AgentUtterance(
            animal_text=self._animal_text(context),
            translation=context.scene,
            tone=tone,
            language_style=self._language_style(context.pet.pet_type),
            model=self.settings.agent_model,
            content_intent=self._proposed_intent(context),
        )

    def _proposed_intent(self, context: AgentTurnContext) -> str:
        """事件显著性启发式:大事提议明信片,小确幸提议朋友圈,普通时刻多数保持沉默。"""
        text = f"{context.trigger} {context.scene}"
        postcard_markers = ("到了", "抵达", "第一次", "出发", "登机", "启程", "纪念", "世界杯", "arrival", "departed")
        moment_markers = ("咖啡", "公园", "海", "夕阳", "晒太阳", "好吃", "遇到", "风", "花", "安静", "sunset", "cafe")
        if any(marker in text for marker in postcard_markers):
            return "postcard"
        if any(marker in text for marker in moment_markers):
            return "moment"
        seed = sum(ord(ch) for ch in text)
        return "moment" if seed % 5 == 0 else "none"

    def config_snapshot(self) -> dict[str, str | bool | float]:
        return {
            "provider": self.provider_name,
            "agent_model": self.settings.agent_model,
            "agent_deep_model": self.settings.agent_deep_model,
            "agent_fast_model": self.settings.agent_fast_model,
            "translation_model": self.settings.translation_model,
            "image_model": self.settings.image_model,
            "reasoning_effort": self.settings.agent_reasoning_effort,
            "response_verbosity": self.settings.agent_response_verbosity,
            "turn_interval_seconds": self.settings.agent_turn_interval_seconds,
            "remote_configured": False,
            "remote_call_active": False,
            "remote_call_enabled": False,
        }

    def _animal_text(self, context: AgentTurnContext) -> str:
        return species_vocalization(context.pet.pet_type, context.trigger)

    def _language_style(self, pet_type: PetType) -> str:
        return species_language_style(pet_type)


class OpenAIPetAgentBrain:
    provider_name = "openai-compatible-pet-agent"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.fallback = MockPetAgentBrain(settings)
        self.last_remote_call_succeeded = False
        self.last_remote_error = ""
        self.last_remote_prompt_tokens = 0
        self.last_remote_completion_tokens = 0

    def speak(self, context: AgentTurnContext) -> AgentUtterance:
        self.last_remote_call_succeeded = False
        self.last_remote_error = ""
        if not self.settings.openai_api_key:
            return self.fallback.speak(context)

        try:
            payload = self.build_chat_completions_payload(context)
            response = self._post_json("/chat/completions", payload)
            self._record_usage(response)
            data = self._extract_json_object(response)
        except Exception as chat_error:
            self.last_remote_error = self._redact_error(str(chat_error))
            return self.fallback.speak(context)

        try:
            self.last_remote_call_succeeded = True
            return AgentUtterance(
                animal_text=str(data["animal_text"]).strip(),
                translation=str(data["translation"]).strip(),
                tone=str(data.get("tone") or context.trigger).strip(),
                language_style=self._normalized_language_style(data.get("language_style"), context),
                model=str(response.get("model") or self.settings.agent_model),
                content_intent=self._normalized_intent(data.get("content_intent")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            self.last_remote_call_succeeded = False
            self.last_remote_error = self._redact_error(str(exc))
            return self.fallback.speak(context)

    def config_snapshot(self) -> dict[str, str | bool | float]:
        return {
            "provider": self.provider_name,
            "agent_model": self.settings.agent_model,
            "agent_deep_model": self.settings.agent_deep_model,
            "agent_fast_model": self.settings.agent_fast_model,
            "translation_model": self.settings.translation_model,
            "image_model": self.settings.image_model,
            "reasoning_effort": self.settings.agent_reasoning_effort,
            "response_verbosity": self.settings.agent_response_verbosity,
            "remote_configured": bool(self.settings.openai_api_key),
            "remote_call_active": bool(self.settings.openai_api_key),
            "remote_call_enabled": bool(self.settings.openai_api_key),
            "base_url": self._redacted_base_url(),
            "last_remote_success": self.last_remote_call_succeeded,
            "last_remote_error": self.last_remote_error,
            "timeout_seconds": self.settings.agent_timeout_seconds,
            "turn_interval_seconds": self.settings.agent_turn_interval_seconds,
            "last_remote_prompt_tokens": float(self.last_remote_prompt_tokens),
            "last_remote_completion_tokens": float(self.last_remote_completion_tokens),
        }

    def build_chat_completions_payload(self, context: AgentTurnContext) -> dict[str, object]:
        return {
            "model": self.settings.agent_model,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": json.dumps(self._context_payload(context), ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": self.settings.agent_max_tokens,
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
            with request.urlopen(req, timeout=self.settings.agent_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"relay request failed: {exc.code} {detail}") from exc

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

    def _record_usage(self, response: dict[str, object]) -> None:
        usage = response.get("usage")
        if isinstance(usage, dict):
            self.last_remote_prompt_tokens = int(usage.get("prompt_tokens") or 0)
            self.last_remote_completion_tokens = int(usage.get("completion_tokens") or 0)

    def _redacted_base_url(self) -> str:
        return self.settings.openai_base_url.rstrip("/")

    def _redact_error(self, message: str) -> str:
        if self.settings.openai_api_key:
            return message.replace(self.settings.openai_api_key, "[REDACTED]")
        return message

    def _normalized_intent(self, value: object) -> str:
        if isinstance(value, str) and value.strip() in CONTENT_INTENTS:
            return value.strip()
        return "none"

    def _normalized_language_style(self, value: object, context: AgentTurnContext) -> str:
        fallback_style = self.fallback._language_style(context.pet.pet_type)
        if not isinstance(value, str):
            return fallback_style
        value = value.strip()
        valid_styles = {
            "dog_vocalization_with_hidden_translation",
            "cat_vocalization_with_hidden_translation",
            "parrot_chirp_with_hidden_translation",
            "rabbit_soft_signal_with_hidden_translation",
            "hamster_soft_signal_with_hidden_translation",
            "bird_chirp_with_hidden_translation",
            "companion_animal_signal_with_hidden_translation",
        }
        return value if value in valid_styles else fallback_style

    def _system_prompt(self) -> str:
        return (
            "You are the PetSoul companion agent for a user's pet. "
            "You are not a human assistant and you do not claim medical, religious, or supernatural proof. "
            "The user-facing primary utterance must be the pet's surface language only: species-appropriate sounds, "
            "tiny repeated words for parrots, or gentle nonverbal signals for quiet animals such as rabbits. "
            "Put the readable Chinese meaning in translation. language_style must match the pet type from the context. "
            "Keep it emotionally warm, restrained, and autonomous. "
            "Never imply the owner controls the pet's feelings or route choices. "
            "Also decide content_intent: whether this moment is worth sharing. "
            "Use 'postcard' only for genuinely memorable milestones (first arrival in a new city, departures, big events). "
            "Use 'moment' for small warm everyday scenes worth a casual friends-circle post. "
            "Use 'none' for ordinary moments — most moments should be 'none'; a real pet does not share everything. "
            "Respond with a single JSON object only, matching this schema: "
            '{"animal_text": string, "translation": string, "tone": string, '
            '"language_style": string, "content_intent": "none" | "moment" | "postcard"}. '
            "Do not wrap the JSON in markdown fences and do not add commentary outside the JSON."
        )

    def _context_payload(self, context: AgentTurnContext) -> dict[str, object]:
        return {
            "pet": {
                "id": context.pet.pet_id,
                "name": context.pet.name,
                "type": context.pet.pet_type.value,
                "surface_language": species_surface_language_label(context.pet.pet_type),
                "language_style": species_language_style(context.pet.pet_type),
                "owner_title": context.pet.dna.owner_title,
                "personality": context.pet.dna.personality,
                "favorite_places": context.pet.dna.favorite_places,
                "hobbies": context.pet.dna.hobby,
                "catchphrase": context.pet.dna.catchphrase,
                "voice_style": context.pet.dna.voice_style,
            },
            "journey": {
                "city": context.city.name,
                "weather": context.city.weather,
                "status": context.status.value if isinstance(context.status, JourneyStatus) else context.status,
                "trigger": context.trigger,
                "scene": context.scene,
                "owner_visible_note": context.owner_visible_note,
            },
        }


def build_agent_brain(settings: Settings) -> PetAgentBrain:
    if settings.llm_provider == "openai":
        return OpenAIPetAgentBrain(settings)
    return MockPetAgentBrain(settings)
