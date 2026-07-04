from __future__ import annotations

from dataclasses import dataclass

from .schemas import PhotoMission, PhotoQualityReport
from .storage import PetRecord


@dataclass(slots=True)
class PromptAssembly:
    prompt: str
    blocks: dict[str, str]


class PromptAssembler:
    provider_name = "prompt-assembler-v2"

    def assemble(self, *, mission: PhotoMission, pet: PetRecord | None = None) -> PromptAssembly:
        pet_identity = f"{pet.name} identity and markings from pet reference" if pet else "pet identity from reference"
        place_environment = f"{mission.city} · {mission.place.name}: {mission.scene_anchor}"
        blocks = {
            "pet_identity": pet_identity,
            "place_environment": place_environment,
            "camera": f"{mission.camera_perspective.value}; first-person companion selfie",
            "action": mission.interaction.pet_action,
            "emotional_tone": mission.interaction.emotional_tone,
            "safety_negatives": (
                "no readable brand marks, no official sports logos, no medical or supernatural proof, "
                "do not invent exact coordinates or impossible routes"
            ),
            "output_style": "warm realistic travel snapshot, emotionally restrained, lived-in details",
        }
        prefix = "\n".join(f"{key}: {value}" for key, value in blocks.items())
        return PromptAssembly(prompt=f"{prefix}\n\n{mission.image_prompt}", blocks=blocks)


class PhotoQualityEvaluator:
    provider_name = "heuristic-photo-quality-evaluator"

    def evaluate_prompt(self, *, prompt: str, mission: PhotoMission, has_pet_reference: bool = False) -> PhotoQualityReport:
        lower = prompt.lower()
        pet_score = 0.55
        if has_pet_reference or "pet reference" in lower or "identity" in lower:
            pet_score += 0.3
        if mission.place.name and mission.place.name in prompt:
            place_score = 0.82
        elif mission.city and mission.city in prompt:
            place_score = 0.68
        else:
            place_score = 0.38
        emotional_score = 0.76 if any(word in lower for word in ("warm", "restrained", "gentle", "温柔", "克制")) else 0.45
        logo_risk = 0.12 if any(word in lower for word in ("logo", "brand", "official")) else 0.35
        if "no readable brand" in lower or "no official sports logos" in lower:
            logo_risk = 0.05
        uncanny_risk = 0.22
        if "preserve" in lower and "identity" in lower:
            uncanny_risk = 0.12
        policy_safety = "supernatural proof" in lower or "not proof" in lower or "no medical" in lower
        retry_reason = None
        failure_category = None
        if pet_score < 0.72:
            retry_reason = "pet_identity_weak"
            failure_category = "pet_identity"
        elif place_score < 0.62:
            retry_reason = "place_anchor_weak"
            failure_category = "place_recognition"
        elif not policy_safety or logo_risk > 0.2:
            retry_reason = "safety_negatives_weak"
            failure_category = "policy_safety"
        return PhotoQualityReport(
            pet_identity_score=round(min(1.0, pet_score), 2),
            place_recognition_score=round(min(1.0, place_score), 2),
            emotional_tone_score=round(min(1.0, emotional_score), 2),
            policy_safety=policy_safety,
            logo_brand_risk=round(min(1.0, logo_risk), 2),
            uncanny_risk=round(min(1.0, uncanny_risk), 2),
            retry_reason=retry_reason,
            failure_category=failure_category,
            evaluator=self.provider_name,
        )

    def classify_generation_error(self, exc: Exception) -> str:
        text = str(exc).lower()
        if "policy" in text or "safety" in text or "content" in text:
            return "policy_safety"
        if "timeout" in text or "tempor" in text:
            return "provider_timeout"
        if "reference" in text or "image" in text:
            return "reference_image"
        return "provider_error"


class PromptRepairer:
    provider_name = "prompt-repairer-v2"

    def repair(self, *, prompt: str, report: PhotoQualityReport, mission: PhotoMission, pet: PetRecord) -> str:
        additions: list[str] = []
        if report.failure_category == "pet_identity":
            additions.append(f"Strongly preserve {pet.name}'s exact pet identity, coat colors, face shape, and familiar expression.")
        if report.failure_category == "place_recognition":
            additions.append(f"Anchor the scene clearly at {mission.city} · {mission.place.name}; include {mission.scene_anchor}.")
        if report.failure_category in {"policy_safety", "provider_error", "reference_image"}:
            additions.append(
                "Avoid official logos, readable brands, public figures, medical claims, religious proof, and supernatural proof."
            )
        if not additions:
            additions.append(f"Make the image safer and clearer while keeping {pet.name} at {mission.place.name}.")
        return f"{prompt}\n\nDirected repair pass: {' '.join(additions)}"


class PhotoPipeline:
    provider_name = "photo-pipeline-v2"

    def __init__(self):
        self.assembler = PromptAssembler()
        self.evaluator = PhotoQualityEvaluator()
        self.repairer = PromptRepairer()

    def enrich_mission(self, *, mission: PhotoMission, pet: PetRecord) -> PhotoMission:
        assembled = self.assembler.assemble(mission=mission, pet=pet)
        report = self.evaluator.evaluate_prompt(
            prompt=assembled.prompt,
            mission=mission,
            has_pet_reference=bool(pet.photo_path),
        )
        return mission.model_copy(
            update={
                "image_prompt": assembled.prompt,
                "prompt_blocks": assembled.blocks,
                "quality_report": report,
                "failure_category": report.failure_category,
            }
        )

    def repair_prompt(self, *, prompt: str, report: PhotoQualityReport, mission: PhotoMission, pet: PetRecord) -> str:
        return self.repairer.repair(prompt=prompt, report=report, mission=mission, pet=pet)
