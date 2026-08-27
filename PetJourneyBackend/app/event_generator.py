from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from math import pi, sin
import mimetypes
from pathlib import Path
import uuid
from urllib import error, request

from .config import Settings
from .image_provider import ImageProvider, ImageReference
from .meal_rules import is_heavy_meal_place, is_morning, is_morning_appropriate_place
from .place_interactions import PlaceInteractionEngine
from .photo_pipeline import PhotoPipeline
from .photo_prompt_builder import PetPhotoPromptBuilder
from .providers import CompanionContentProvider, JourneyCity, MapProvider
from .schemas import JourneyStatus, PhotoMission, PhotoPerspective, SouvenirItem
from .storage import JourneyStorage, PetRecord


AppendThought = Callable[[PetRecord, JourneyCity, str, str, JourneyStatus | str, datetime | None], None]


class JourneyEventGenerator:
    def __init__(
        self,
        storage: JourneyStorage,
        content_provider: CompanionContentProvider,
        map_provider: MapProvider,
        image_provider: ImageProvider,
        place_interaction_engine: PlaceInteractionEngine,
        settings: Settings,
    ):
        self.storage = storage
        self.content_provider = content_provider
        self.map_provider = map_provider
        self.image_provider = image_provider
        self.place_interaction_engine = place_interaction_engine
        self.settings = settings
        self.photo_prompt_builder = PetPhotoPromptBuilder()
        self.photo_pipeline = PhotoPipeline()

    def advance(
        self,
        pet: PetRecord,
        city: JourneyCity,
        elapsed: float,
        now: datetime,
        status: JourneyStatus,
        append_agent_thought: AppendThought,
    ) -> None:
        thoughts = self.storage.list_thoughts(pet.pet_id, limit=18, include_translation=True)
        latest = thoughts[-1] if thoughts else None
        generated_event_turn = False

        if elapsed >= 10 and not any(item["tone"] == "connected" for item in thoughts):
            append_agent_thought(
                pet,
                city,
                "connected",
                "连接已经稳定了。我好像听见你在这边。",
                status,
                None,
            )
            generated_event_turn = True

        thought_index = max(0, int(elapsed // 5)) % len(city.thoughts)
        next_thought = city.thoughts[thought_index]
        is_recent_feedback = bool(
            latest
            and latest["tone"] in {"guide_saved", "guide_skipped"}
            and (now - latest["timestamp"]).total_seconds() < 8
        )
        latest_translation = latest["translation"] if latest and latest["translation"] else latest["text"] if latest else None
        latest_daily = next((item for item in reversed(thoughts) if item["tone"] == "daily"), None)
        daily_due = latest_daily is None or (
            now - latest_daily["timestamp"]
        ).total_seconds() >= self.settings.agent_turn_interval_seconds
        any_recent_agent_turn = bool(
            latest
            and latest["tone"] in {"connecting", "connected", "daily", "selfie", "guide_saved", "guide_skipped"}
            and (now - latest["timestamp"]).total_seconds() < self.settings.agent_turn_interval_seconds
        )

        if (
            (latest is None or latest_translation != next_thought)
            and not is_recent_feedback
            and daily_due
            and not any_recent_agent_turn
            and not generated_event_turn
        ):
            append_agent_thought(pet, city, "daily", next_thought, status, None)

        # 长途交通中（飞行/移动）不产生地点类明信片——TA 不可能同时在飞机上和咖啡馆里
        in_transit = status in {JourneyStatus.flying, JourneyStatus.traveling}
        if elapsed >= 35 and not in_transit and self.storage.count_postcards(pet.pet_id) == 0:
            postcard = self._create_postcard(pet=pet, city=city, elapsed=elapsed, now=now)
            places = self.map_provider.places_for_city(city)
            place = self._postcard_place(places, now=now, city_name=city.name)
            if place:
                self.storage.append_event(
                    pet.pet_id,
                    f"{pet.name} 寄来一张明信片",
                    f"{pet.name} 在 {place.name} 停了一会儿，把那里的光和味道寄了回来。",
                    timestamp=now,
                )
            elif postcard:
                self.storage.append_event(
                    pet.pet_id,
                    f"{pet.name} 寄来一张明信片",
                    f"{pet.name} 在 {city.name} 停了一会儿，把当下的画面寄回来了。",
                    timestamp=now,
                )

    def generate_selfie_postcard(
        self,
        pet: PetRecord,
        city: JourneyCity,
        now: datetime,
        mission: PhotoMission | None = None,
    ) -> dict:
        if mission:
            existing = self.storage.find_postcard_by_mission(pet.pet_id, mission.id)
            if existing:
                return existing
        latest = self.storage.latest_postcard(pet.pet_id)
        if latest and (now - latest["timestamp"]).total_seconds() < 20 * 60:
            return latest
        elapsed = (now - pet.created_at).total_seconds()
        postcard = self._create_postcard(pet=pet, city=city, elapsed=elapsed, now=now, mission=mission)
        self.storage.append_event(
            pet.pet_id,
            f"{pet.name} 传来一张此刻照片",
            f"{pet.name} 在 {postcard['location']} 停下，把这一刻拍给你看。",
            timestamp=now,
        )
        return postcard

    def _create_postcard(
        self,
        pet: PetRecord,
        city: JourneyCity,
        elapsed: float,
        now: datetime,
        mission: PhotoMission | None = None,
    ) -> dict:
        happiness = self._clamp(82 + self._wave(elapsed + 4, 18, 1), 20, 99)
        places = self.map_provider.places_for_city(city)
        place = mission.place if mission else self._postcard_place(places, now=now, city_name=city.name)
        if mission is None:
            mission_places = [place] if place else places
            mission = self.place_interaction_engine.build_photo_mission(
                pet=pet,
                activity=None,
                places=mission_places,
                weather=city.weather,
                now=now,
            )
            place = mission.place
        location_city = mission.city if mission else city.name
        location = f"{location_city} · {place.name}" if place else location_city
        image_url = self._postcard_image_url(pet=pet, city=city, place=place, mission=mission)
        return self.storage.add_postcard(
            pet.pet_id,
            location=location,
            text=self._postcard_text(pet=pet, city=city, place=place, mission=mission),
            weather=mission.weather if mission else city.weather,
            happiness=happiness,
            image_url=image_url,
            timestamp=now,
            mission_id=mission.id if mission else None,
        )

    def _wave(self, elapsed: float, period: float, offset: float) -> int:
        return int(round(sin((elapsed + offset) / period * 2 * pi) * 6))

    def _clamp(self, value: int, minimum: int, maximum: int) -> int:
        return max(minimum, min(maximum, value))

    def _postcard_place(self, places, *, now: datetime, city_name: str | None = None):
        if not places:
            return None
        candidates = list(places)
        if is_morning(now, city_name):
            morning_places = [
                place
                for place in candidates
                if is_morning_appropriate_place(place.name, place.category, str(place.raw.get("type") or ""))
            ]
            if morning_places:
                candidates = morning_places
            else:
                non_heavy_places = [
                    place
                    for place in candidates
                    if not is_heavy_meal_place(place.name, place.category, str(place.raw.get("type") or ""))
                ]
                if non_heavy_places:
                    candidates = non_heavy_places
        return max(
            candidates,
            key=lambda place: (
                place.guide_score or 0,
                1 if place.photo_url else 0,
                place.rating or 0,
            ),
        )

    def _postcard_text(self, pet: PetRecord, city: JourneyCity, place, mission: PhotoMission | None = None) -> str:
        if mission:
            return mission.postcard_text
        if not place:
            return self.content_provider.postcard_text(pet.name, city)
        reason = place.guide_reason or place.detail_hint
        return (
            f"今天我在 {place.name} 附近停了一会儿。这里{city.weather}，"
            f"{place.activity_hint}。我把这里的光、声音和路边细节都放进照片里：{reason}。"
            "我没有急着走，只是把这一小段路寄给你。"
        )

    def _postcard_image_url(self, pet: PetRecord, city: JourneyCity, place, mission: PhotoMission | None = None) -> str | None:
        prompt = mission.image_prompt if mission else self._postcard_image_prompt(pet=pet, city=city, place=place)
        mission_report = mission.quality_report if mission else None
        try:
            references = self._reference_images_for_generation(pet=pet, place=place)
            try:
                image = self._generate_image_once(prompt=prompt, references=references)
            except Exception as first_exc:
                failure_category = self.photo_pipeline.evaluator.classify_generation_error(first_exc)
                if mission and mission_report:
                    mission_report = mission_report.model_copy(update={"failure_category": failure_category, "retry_reason": failure_category})
                    repaired_prompt = self.photo_pipeline.repair_prompt(
                        prompt=prompt,
                        report=mission_report,
                        mission=mission,
                        pet=pet,
                    )
                    image = self._generate_image_once(prompt=repaired_prompt, references=references)
                else:
                    raise
        except Exception:
            return place.photo_url if place and place.photo_url else None

        return self._store_generated_image(image, subdir=f"postcards/{pet.pet_id}")

    def souvenir_image_url(self, *, pet: PetRecord, souvenir: SouvenirItem) -> str | None:
        try:
            references: list[ImageReference] = []
            pet_reference = self._reference_image_for_pet(pet)
            if pet_reference:
                references.append(pet_reference)
            image = self._generate_image_once(prompt=souvenir.image_prompt, references=references)
        except Exception:
            return None
        return self._store_generated_image(image, subdir=f"souvenirs/{pet.pet_id}")

    def _store_generated_image(self, image, *, subdir: str) -> str | None:
        suffix = mimetypes.guess_extension(image.mime_type) or ".png"
        if suffix in {".jpe", ".jpeg"}:
            suffix = ".jpg"
        target_dir = self.settings.upload_dir / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}{suffix}"
        target = target_dir / filename
        target.write_bytes(image.image_bytes)
        media_path = str(target.relative_to(self.settings.upload_dir))
        if not self.settings.public_base_url:
            return None
        return f"{self.settings.public_base_url.rstrip('/')}/media/{media_path}"

    def _generate_image_once(self, *, prompt: str, references: list[ImageReference]):
        if references:
            return self.image_provider.generate_image_with_references(
                self._prompt_with_reference_notes(prompt, references),
                references=references,
                size="1024x1024",
            )
        return self.image_provider.generate_image(prompt, size="1024x1024")

    def _reference_images_for_generation(self, pet: PetRecord, place) -> list[ImageReference]:
        references: list[ImageReference] = []
        pet_reference = self._reference_image_for_pet(pet)
        if pet_reference:
            references.append(pet_reference)

        place_reference = self._reference_image_for_place(place)
        if place_reference:
            references.append(place_reference)
        return references

    def _reference_image_for_pet(self, pet: PetRecord) -> ImageReference | None:
        if not pet.photo_path:
            return None
        path = Path(pet.photo_path)
        if not path.is_absolute():
            path = self.settings.upload_dir / path
        if not path.exists() or not path.is_file():
            return None
        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        if mime_type not in {"image/png", "image/jpeg", "image/jpg", "image/webp"}:
            mime_type = "image/png"
        suffix = self._suffix_for_mime_type(mime_type)
        return ImageReference(
            image_bytes=path.read_bytes(),
            mime_type=mime_type,
            filename=f"pet-reference-{pet.pet_id}{suffix}",
            role="pet_identity",
            source=str(path),
        )

    def _reference_image_for_place(self, place) -> ImageReference | None:
        if not self.settings.place_reference_images_enabled:
            return None
        if not place or not place.photo_url:
            return None
        try:
            req = request.Request(str(place.photo_url), method="GET", headers={"Accept": "image/*"})
            with request.urlopen(req, timeout=self.settings.map_timeout_seconds) as response:
                mime_type = response.headers.get_content_type() or "image/jpeg"
                if not mime_type.startswith("image/"):
                    return None
                max_bytes = self.settings.place_reference_image_max_bytes
                image_bytes = response.read(max_bytes + 1)
                if len(image_bytes) > max_bytes:
                    return None
        except (OSError, error.URLError):
            return None

        return ImageReference(
            image_bytes=image_bytes,
            mime_type=mime_type,
            filename=f"place-reference-{uuid.uuid4().hex}{self._suffix_for_mime_type(mime_type)}",
            role="place_environment",
            source=str(place.photo_url),
        )

    def _prompt_with_reference_notes(self, prompt: str, references: list[ImageReference]) -> str:
        roles = {reference.role for reference in references}
        return self.photo_prompt_builder.append_reference_contract(prompt, roles=roles)

    def _suffix_for_mime_type(self, mime_type: str) -> str:
        suffix = mimetypes.guess_extension(mime_type) or ".png"
        if suffix in {".jpe", ".jpeg"}:
            return ".jpg"
        if suffix not in {".png", ".jpg", ".webp"}:
            return ".png"
        return suffix

    def _postcard_image_prompt(self, pet: PetRecord, city: JourneyCity, place) -> str:
        return self.photo_prompt_builder.build_prompt(
            pet=pet,
            place=place,
            interaction=None,
            perspective=PhotoPerspective.first_person_selfie,
            weather=city.weather,
            time_of_day="current journey moment",
            landmark_hints=[place.detail_hint] if place else [],
            local_detail_hints=[place.activity_hint] if place else [],
            crowd_hints=[],
            base_prompt=(
                "PetSoul emotional companion travel photo. TA is sending a small lived-in image from another world; "
                "keep the tone warm, real, and restrained."
            ),
            has_pet_reference=bool(pet.photo_path),
            has_place_reference=bool(place and place.photo_url),
        )
