"""照片编排：拍照任务与自拍/明信片的生成（含去重与频控）。"""

from __future__ import annotations

from ..schemas import PhotoMission, Postcard
from ..storage import utcnow


class PhotoMixin:
    def photo_mission(self, pet_id: str) -> PhotoMission:
        trace_started = utcnow()
        steps: list = []
        pet = self._pet(pet_id)
        try:
            now = utcnow()
            elapsed = (now - pet.created_at).total_seconds()
            city = self._city_for_elapsed(elapsed, now=now)
            plan = self._journey_plan_for(pet, city, now)
            snapshot = self.world_simulation_engine.snapshot(pet=pet, city=city, plan=plan, now=now)
            steps.append(
                self._trace_step(
                    "world_snapshot",
                    outputs={"city": snapshot.city, "activity": snapshot.current_activity.title, "places": len(plan.places)},
                )
            )
            mission = self.place_interaction_engine.build_photo_mission(
                pet=pet,
                activity=snapshot.current_activity,
                places=plan.places,
                weather=snapshot.weather,
                now=now,
                worldcup_event=plan.worldcup_event,
            )
            steps.append(
                self._trace_step(
                    "photo_mission",
                    outputs={
                        "mission_id": mission.id,
                        "place_id": mission.place.id,
                        "place_name": mission.place.name,
                        "quality_report": mission.quality_report.model_dump(mode="json") if mission.quality_report else None,
                    },
                    fallback="photo_mission_quality_retry_needed" if mission.failure_category else None,
                )
            )
            self._save_trace(
                pet_id=pet.pet_id,
                operation="photo_mission",
                started_at=trace_started,
                steps=steps,
                state_after={"mission_id": mission.id, "place": mission.place.name, "failure_category": mission.failure_category},
            )
            return mission
        except Exception as exc:
            self._save_trace(pet_id=pet.pet_id, operation="photo_mission", started_at=trace_started, steps=steps, error=exc)
            raise

    def generate_selfie(self, pet_id: str) -> Postcard:
        trace_started = utcnow()
        steps: list = []
        pet = self._pet(pet_id)
        try:
            now = utcnow()
            elapsed = (now - pet.created_at).total_seconds()
            city = self._city_for_elapsed(elapsed, now=now)
            latest = self.storage.latest_postcard(pet.pet_id)
            if latest and (now - latest["timestamp"]).total_seconds() < 20 * 60:
                result = Postcard.model_validate(latest)
                steps.append(self._trace_step("action_validation", outputs={"cooldown_reused_latest": True}))
                self._save_trace(
                    pet_id=pet.pet_id,
                    operation="generate_selfie",
                    started_at=trace_started,
                    steps=steps,
                    state_after={"postcard_id": result.id, "reused": True},
                )
                return result
            mission = self.photo_mission(pet_id)
            steps.append(
                self._trace_step(
                    "photo_mission",
                    outputs={"mission_id": mission.id, "place": mission.place.name, "quality": mission.quality_report.model_dump(mode="json") if mission.quality_report else None},
                    fallback="photo_mission_quality_retry_needed" if mission.failure_category else None,
                )
            )
            existing = self.storage.find_postcard_by_mission(pet.pet_id, mission.id)
            if existing:
                result = Postcard.model_validate(existing)
                steps.append(self._trace_step("action_validation", outputs={"deduped_by_mission": True}))
                self._save_trace(
                    pet_id=pet.pet_id,
                    operation="generate_selfie",
                    started_at=trace_started,
                    steps=steps,
                    state_after={"postcard_id": result.id, "reused": True},
                )
                return result
            postcard = Postcard.model_validate(self.event_generator.generate_selfie_postcard(pet, city, now, mission=mission))
            steps.append(
                self._trace_step(
                    "photo_generation",
                    outputs={"postcard_id": postcard.id, "has_image": bool(postcard.image_url), "mission_id": mission.id},
                    fallback=None if postcard.image_url else "image_provider_returned_empty_or_fallback",
                )
            )
            self._append_agent_thought(
                pet=pet,
                city=city,
                trigger="selfie",
                scene=f"我在 {postcard.location} 拍了一张照片给你。{mission.interaction.pet_action}。",
                status=self._status_for(now),
                timestamp=now,
            )
            steps.append(self._trace_step("agent_speech", outputs={"trigger": "selfie"}))
            self._remember_postcard(pet, postcard, mission=mission)
            steps.append(self._trace_step("memory_write", outputs={"kind": "postcard", "mission_id": mission.id}))
            self._save_trace(
                pet_id=pet.pet_id,
                operation="generate_selfie",
                started_at=trace_started,
                steps=steps,
                state_after={"postcard_id": postcard.id, "location": postcard.location, "has_image": bool(postcard.image_url)},
            )
            return postcard
        except Exception as exc:
            self._save_trace(pet_id=pet.pet_id, operation="generate_selfie", started_at=trace_started, steps=steps, error=exc)
            raise
