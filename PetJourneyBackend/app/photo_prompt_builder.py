from __future__ import annotations

from dataclasses import dataclass

from .schemas import PhotoPerspective, PlaceInteraction, PlaceSignal
from .species import species_image_subject
from .storage import PetRecord


@dataclass(frozen=True, slots=True)
class PhotoPromptQualityReport:
    passed: bool
    missing: list[str]

    @property
    def summary(self) -> str:
        if self.passed:
            return "Prompt QA passed: first-person selfie, pet identity, place context, anti-cutout, and safety constraints are present."
        return "Prompt QA missing: " + ", ".join(self.missing)


class PetPhotoPromptBuilder:
    """Builds stable GPT Image prompts for PetSoul's pet travel selfies."""

    def build_prompt(
        self,
        *,
        pet: PetRecord,
        place: PlaceSignal | None,
        interaction: PlaceInteraction | None = None,
        perspective: PhotoPerspective = PhotoPerspective.first_person_selfie,
        weather: str = "",
        time_of_day: str = "",
        landmark_hints: list[str] | None = None,
        local_detail_hints: list[str] | None = None,
        crowd_hints: list[str] | None = None,
        base_prompt: str | None = None,
        has_pet_reference: bool = False,
        has_place_reference: bool = False,
    ) -> str:
        species = species_image_subject(pet.pet_type)
        place_name = place.name if place else "the current place"
        city = place.city if place else "the current city"
        category = place.category if place else "place"
        activity = interaction.pet_action if interaction else "living at this real-world stop at a gentle pace"
        tone = interaction.emotional_tone if interaction else "warm, restrained, lived-in, emotionally gentle"
        landmark_text = self._joined(landmark_hints) or (place.detail_hint if place else "real local background")
        local_text = self._joined(local_detail_hints) or (place.activity_hint if place else "local everyday details")
        crowd_text = self._joined(crowd_hints) or "ordinary local life, no staged crowd"
        draft_text = self._clean_base_prompt(base_prompt)

        sections = [
            "Create a photorealistic first-person pet selfie from TA's own communicator or phone.",
            "",
            "Input images if supplied:",
            "- pet_identity reference: use only to preserve the exact pet identity, species, coat color, face shape, markings, ears, eyes, expression, collar, and body details.",
            "- place_environment reference: use only for the real location layout, lighting, storefront or scenery, materials, weather mood, and local atmosphere.",
            "",
            "Pet identity:",
            f"- Subject must be a {species} named {pet.name}; do not change the species.",
            f"- Pet personality cues: {pet.dna.personality or 'gentle and curious'}.",
            f"- Pet reference expected: {'yes' if has_pet_reference else 'no, but preserve the described identity if a reference is later attached'}.",
            "",
            "Scene:",
            f"- TA is at {place_name}, {city}, category {category}, during {time_of_day or 'the current time'}, with {weather or 'current local weather'}.",
            f"- TA is {activity}.",
            f"- Emotional tone: {tone}.",
            f"- Real place anchors: {landmark_text}.",
            f"- Local details to include: {local_text}.",
            f"- Crowd or event atmosphere: {crowd_text}.",
            f"- Place environment reference expected: {'yes' if has_place_reference else 'no, but use real contextual place clues'}.",
            "",
            "Camera:",
            self._camera_contract(perspective),
            "",
            "Style:",
            "- Authentic phone photo, lived-in and warm but not childish.",
            "- Natural lens perspective, coherent scale, shadows, depth, fur or feather detail, and matching local lighting.",
            "- The real place must be visible behind TA; do not make a generic studio portrait.",
            "",
            "Do not:",
            "- No cutout, no pasted sticker look, no collage, no clone-stamp, no hard edges, no full-body pet simply placed in front of a landmark.",
            "- No watermark, no text overlays, no captions, no readable logos, no brand marks, no license plates, no private faces.",
            "- No recognizable public figures, athletes, official sports logos, medical claims, religious claims, or supernatural proof.",
        ]
        if draft_text:
            sections.extend(["", "Model draft scene to preserve if compatible:", draft_text])

        prompt = "\n".join(sections).strip()
        report = self.quality_check(
            prompt,
            expected_roles=self.expected_reference_roles(
                has_pet_reference=has_pet_reference,
                has_place_reference=has_place_reference,
            ),
            place=place,
        )
        if not report.passed:
            prompt = f"{prompt}\n\nPrompt QA repair notes: {', '.join(report.missing)}."
        return prompt

    def append_reference_contract(self, prompt: str, *, roles: set[str]) -> str:
        notes = self.reference_contract_for_roles(roles)
        if not notes:
            return prompt
        return f"{prompt.strip()}\n\n{notes}"

    def reference_contract_for_roles(self, roles: set[str]) -> str:
        notes: list[str] = []
        if "pet_identity" in roles:
            notes.append(
                "Reference image role pet_identity: preserve the exact pet identity, coat, markings, face, ears, eyes, expression, collar, and body details."
            )
            notes.append(
                "Do not cut out, paste, sticker, overlay, or collage the reference pet into the scene; redraw a full coherent photo with matching light, scale, contact shadows, fur or feather detail, depth, and camera perspective."
            )
        if "place_environment" in roles:
            notes.append(
                "Reference image role place_environment: use it only for location layout, storefront or scenery, lighting, material textures, weather mood, and local atmosphere."
            )
            notes.append(
                "Do not copy readable signs, private faces, plates, watermarks, brand marks, or commercial text from the place reference."
            )
        if notes:
            notes.append(
                "Final image must remain a first-person pet selfie from TA's communicator or phone, with the pet close to the lens and the real place visible behind."
            )
        return " ".join(notes)

    def expected_reference_roles(self, *, has_pet_reference: bool, has_place_reference: bool) -> set[str]:
        roles: set[str] = set()
        if has_pet_reference:
            roles.add("pet_identity")
        if has_place_reference:
            roles.add("place_environment")
        return roles

    def quality_check(
        self,
        prompt: str,
        *,
        expected_roles: set[str] | None = None,
        place: PlaceSignal | None = None,
    ) -> PhotoPromptQualityReport:
        expected_roles = expected_roles or set()
        lower = prompt.lower()
        missing: list[str] = []

        self._require_any(lower, ("first-person", "first person"), "first-person perspective", missing)
        self._require_any(lower, ("selfie", "communicator", "phone"), "selfie communicator camera", missing)
        self._require_any(lower, ("pet_identity", "preserve the pet", "preserve the exact pet"), "pet identity preservation", missing)
        if "place_environment" in expected_roles:
            self._require_any(lower, ("place_environment", "location layout", "storefront", "scenery"), "place environment reference", missing)
        if place:
            place_tokens = [place.name.lower(), place.city.lower()]
            if not any(token and token in lower for token in place_tokens):
                missing.append("real place name or city")
        self._require_any(lower, ("cutout", "pasted", "sticker", "collage"), "anti-cutout guard", missing)
        self._require_any(lower, ("shadow", "lighting", "light", "depth", "scale"), "coherent lighting and depth", missing)
        self._require_any(lower, ("watermark", "logo", "readable"), "watermark/logo/text guard", missing)

        return PhotoPromptQualityReport(passed=not missing, missing=missing)

    def safety_note_for_prompt(self, prompt: str, *, expected_roles: set[str], place: PlaceSignal | None) -> str:
        return self.quality_check(prompt, expected_roles=expected_roles, place=place).summary

    def _camera_contract(self, perspective: PhotoPerspective) -> str:
        if perspective == PhotoPerspective.passerby_third_person:
            return (
                "- A passerby may have helped press the communicator, but keep the pet close to the camera with a candid travel-selfie feeling."
            )
        if perspective == PhotoPerspective.communicator_view:
            return (
                "- Low communicator camera view, imperfect framing, close pet face or paw in foreground, documentary travel-photo feeling."
            )
        return (
            "- Close pet face, nose, paw, wing, whiskers, collar, shoulder, or chest partially in foreground.\n"
            "- Low handheld phone angle, slightly imperfect framing, natural lens perspective, candid travel selfie.\n"
            "- The photo should feel like TA casually nudged or held the communicator to send a photo."
        )

    def _joined(self, values: list[str] | None) -> str:
        return ", ".join(item.strip() for item in values or [] if item and item.strip())

    def _clean_base_prompt(self, prompt: str | None) -> str:
        text = " ".join((prompt or "").strip().split())
        if not text:
            return ""
        return text[:1_600]

    def _require_any(self, lower: str, tokens: tuple[str, ...], label: str, missing: list[str]) -> None:
        if not any(token in lower for token in tokens):
            missing.append(label)
