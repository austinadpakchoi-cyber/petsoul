"""地点交互引擎 mission mixin：照片任务生成与丰富。"""

from __future__ import annotations

from datetime import datetime
import re
import uuid

from ..photo_mission_brain import PhotoMissionBrain, PhotoMissionContext, PhotoMissionDraft
from ..photo_pipeline import PhotoPipeline
from ..photo_prompt_builder import PetPhotoPromptBuilder
from ..schemas import (
    PhotoMission,
    PhotoPerspective,
    PlaceInteraction,
    PlaceSignal,
    WorldActivity,
)
from ..storage import PetRecord


class PlaceInteractionMissionMixin:
    provider_name = "place-interaction-engine"
    _source_phrase_pattern = re.compile(
        r"[\s·。；;，,]*(?:地点来源|数据来源|来源|source|provider)\s*[:：]\s*[\w.+/\- ]+",
        re.IGNORECASE,
    )
    _provider_token_pattern = re.compile(
        r"\b(?:amap|google|mock|hybrid|openai|web|map|provider|service|engine|client|route|planner|mission)"
        r"(?:[-_][A-Za-z0-9]+)+\b",
        re.IGNORECASE,
    )

    _mission_cache_ttl_seconds = 30 * 60

    def __init__(self, photo_mission_brain: PhotoMissionBrain | None = None, photo_pipeline: PhotoPipeline | None = None):
        self.photo_mission_brain = photo_mission_brain
        self.photo_prompt_builder = PetPhotoPromptBuilder()
        self.photo_pipeline = photo_pipeline or PhotoPipeline()
        self._mission_cache: dict[str, tuple[float, PhotoMission]] = {}
    def _cached_mission(self, cache_key: str, now: datetime) -> PhotoMission | None:
        entry = self._mission_cache.get(cache_key)
        if not entry:
            return None
        cached_at, mission = entry
        if (now - cached_at).total_seconds() > self._mission_cache_ttl_seconds:
            self._mission_cache.pop(cache_key, None)
            return None
        return mission.model_copy(deep=True)
    def build_photo_mission(
        self,
        *,
        pet: PetRecord,
        activity: WorldActivity | None,
        places: list[PlaceSignal],
        weather: str,
        now: datetime,
        worldcup_event: bool = False,
    ) -> PhotoMission:
        place = self._select_place(activity=activity, places=places)
        if not place:
            place = self._fallback_place(activity)
        time_of_day = self._time_of_day(now, place.city or (activity.city if activity else None))
        cache_key = self._stable_photo_id(pet=pet, place=place, now=now)
        cached = self._cached_mission(cache_key, now)
        if cached is not None:
            return cached
        if self.photo_mission_brain is not None:
            draft = self.photo_mission_brain.draft(
                PhotoMissionContext(
                    pet=pet,
                    place=place,
                    activity=activity,
                    weather=weather,
                    now=now,
                    time_of_day=time_of_day,
                    worldcup_event=worldcup_event,
                )
            )
            if draft is not None:
                mission = self._mission_from_draft(
                    pet=pet,
                    place=place,
                    weather=weather,
                    time_of_day=time_of_day,
                    now=now,
                    draft=draft,
                )
                mission = self._enrich_mission(mission=mission, pet=pet)
                self._mission_cache[cache_key] = (now, mission)
                return mission

        mission = self._rule_based_photo_mission(
            pet=pet,
            place=place,
            activity=activity,
            weather=weather,
            now=now,
            time_of_day=time_of_day,
            worldcup_event=worldcup_event,
        )
        mission = self._enrich_mission(mission=mission, pet=pet)
        self._mission_cache[cache_key] = (now, mission)
        return mission
    def _enrich_mission(self, *, mission: PhotoMission, pet: PetRecord) -> PhotoMission:
        try:
            return self.photo_pipeline.enrich_mission(mission=mission, pet=pet)
        except Exception:
            return mission
    def _rule_based_photo_mission(
        self,
        *,
        pet: PetRecord,
        place: PlaceSignal,
        activity: WorldActivity | None,
        weather: str,
        now: datetime,
        time_of_day: str,
        worldcup_event: bool,
    ) -> PhotoMission:
        interaction = self._interaction_for_place(
            pet=pet,
            place=place,
            activity=activity,
            worldcup_event=worldcup_event,
        )
        perspective = self._perspective_for(place, worldcup_event)
        landmark_hints = self._landmark_hints(place, worldcup_event)
        local_detail_hints = self._local_detail_hints(place)
        crowd_hints = self._crowd_hints(place, worldcup_event)
        image_prompt = self._image_prompt(
            pet=pet,
            place=place,
            interaction=interaction,
            perspective=perspective,
            landmark_hints=landmark_hints,
            local_detail_hints=local_detail_hints,
            crowd_hints=crowd_hints,
            weather=weather,
            time_of_day=time_of_day,
        )
        return PhotoMission(
            id=self._stable_photo_id(pet=pet, place=place, now=now),
            pet_id=pet.pet_id,
            generated_at=now,
            provider=self.provider_name,
            city=place.city,
            place=place,
            interaction=interaction,
            camera_perspective=perspective,
            scene_anchor=self._scene_anchor(place, landmark_hints),
            landmark_hints=landmark_hints,
            local_detail_hints=local_detail_hints,
            crowd_hints=crowd_hints,
            weather=weather,
            time_of_day=time_of_day,
            image_prompt=image_prompt,
            postcard_text=self._postcard_text(pet, place, interaction, perspective),
            safety_notes=[
                "Preserve the user's pet identity from the reference photo when available.",
                "Do not use official sports logos, readable brand marks, or recognizable real players.",
                "This is an emotional companion simulation, not proof of a real spiritual event.",
                "Rule-based fallback used because the photo mission brain was unavailable.",
                self._prompt_quality_note(image_prompt, pet=pet, place=place),
            ],
        )
    def _mission_from_draft(
        self,
        *,
        pet: PetRecord,
        place: PlaceSignal,
        weather: str,
        time_of_day: str,
        now: datetime,
        draft: PhotoMissionDraft,
    ) -> PhotoMission:
        interaction = PlaceInteraction(
            id=self._stable_interaction_id(pet=pet, place=place, now=now),
            pet_id=pet.pet_id,
            place=place,
            interaction_type=self._clean_user_text(draft.interaction_type, fallback="parallel_world_stop"),
            title=self._clean_user_text(draft.title, fallback=f"在 {place.name} 停了一会儿"),
            detail=self._clean_user_text(
                draft.detail,
                fallback=f"{pet.name} 在 {place.name} 附近按自己的节奏停留了一会儿。",
            ),
            pet_action=self._clean_user_text(
                draft.pet_action,
                fallback=f"在 {place.name} 附近停下来认真看了看",
            ),
            emotional_tone=self._clean_user_text(draft.emotional_tone, fallback="温柔、克制、像寄回一小段生活"),
            dwell_minutes=draft.dwell_minutes,
            can_generate_photo=True,
            source=draft.provider,
        )
        image_prompt = self._ensure_image_prompt_contract(
            draft.image_prompt,
            pet=pet,
            place=place,
            interaction=interaction,
            perspective=PhotoPerspective.first_person_selfie,
            landmark_hints=draft.landmark_hints,
            local_detail_hints=draft.local_detail_hints,
            crowd_hints=draft.crowd_hints,
            weather=weather,
            time_of_day=time_of_day,
        )
        return PhotoMission(
            id=self._stable_photo_id(pet=pet, place=place, now=now),
            pet_id=pet.pet_id,
            generated_at=now,
            provider=draft.provider,
            city=place.city,
            place=place,
            interaction=interaction,
            camera_perspective=PhotoPerspective.first_person_selfie,
            scene_anchor=self._clean_user_text(draft.scene_anchor or self._scene_anchor(place, draft.landmark_hints)),
            landmark_hints=self._clean_user_list(draft.landmark_hints or [place.detail_hint]),
            local_detail_hints=self._clean_user_list(draft.local_detail_hints or [place.activity_hint]),
            crowd_hints=self._clean_user_list(draft.crowd_hints),
            weather=weather,
            time_of_day=time_of_day,
            image_prompt=image_prompt,
            postcard_text=self._clean_user_text(
                draft.postcard_text,
                fallback=f"我在 {place.name} 附近停了一会儿，把这一刻拍给你看。",
            ),
            safety_notes=self._safety_notes(draft.safety_notes, pet=pet, place=place, prompt=image_prompt),
        )
    def _ensure_image_prompt_contract(
        self,
        prompt: str,
        *,
        pet: PetRecord,
        place: PlaceSignal,
        interaction: PlaceInteraction,
        perspective: PhotoPerspective,
        landmark_hints: list[str],
        local_detail_hints: list[str],
        crowd_hints: list[str],
        weather: str,
        time_of_day: str,
    ) -> str:
        return self.photo_prompt_builder.build_prompt(
            pet=pet,
            place=place,
            interaction=interaction,
            perspective=perspective,
            weather=weather,
            time_of_day=time_of_day,
            landmark_hints=landmark_hints,
            local_detail_hints=local_detail_hints,
            crowd_hints=crowd_hints,
            base_prompt=prompt,
            has_pet_reference=bool(pet.photo_path),
            has_place_reference=bool(place.photo_url),
        )
    def _safety_notes(self, notes: list[str], *, pet: PetRecord, place: PlaceSignal, prompt: str) -> list[str]:
        required = [
            "Preserve the user's pet identity from the reference photo when available.",
            "Do not use official sports logos, readable brand marks, recognizable real athletes, or public figures.",
            "This is an emotional companion simulation, not proof of a real spiritual event.",
            "Model-generated photo mission; rule layer only validates safety and fallback constraints.",
            self._prompt_quality_note(prompt, pet=pet, place=place),
        ]
        seen: set[str] = set()
        merged: list[str] = []
        for note in [*notes, *required]:
            clean = note.strip()
            if not clean or clean.lower() in seen:
                continue
            seen.add(clean.lower())
            merged.append(clean)
        return merged
    def _prompt_quality_note(self, prompt: str, *, pet: PetRecord, place: PlaceSignal) -> str:
        roles = self.photo_prompt_builder.expected_reference_roles(
            has_pet_reference=bool(pet.photo_path),
            has_place_reference=bool(place.photo_url),
        )
        return self.photo_prompt_builder.safety_note_for_prompt(prompt, expected_roles=roles, place=place)
    def _select_place(self, activity: WorldActivity | None, places: list[PlaceSignal]) -> PlaceSignal | None:
        if not places:
            return None
        if activity and activity.place_name:
            by_name = next((place for place in places if place.name == activity.place_name), None)
            if by_name:
                return by_name
        if activity:
            return min(
                places,
                key=lambda place: self._rough_distance_meters(activity.lat, activity.lng, place.lat, place.lng),
            )
        return max(
            places,
            key=lambda place: (
                place.guide_score or 0,
                1 if place.photo_url else 0,
                place.rating or 0,
            ),
        )
    def _fallback_place(self, activity: WorldActivity | None) -> PlaceSignal:
        city = activity.city if activity else "平行世界"
        name = activity.place_name or city if activity else city
        lat = activity.lat if activity else 0.0
        lng = activity.lng if activity else 0.0
        return PlaceSignal(
            id=f"fallback-{uuid.uuid4().hex[:8]}",
            name=name,
            category=activity.kind if activity else "place",
            city=city,
            lat=lat,
            lng=lng,
            activity_hint=activity.detail if activity else "安静地停留了一会儿",
            detail_hint="由世界模拟当前位置生成的临时地点。",
            source=self.provider_name,
        )
