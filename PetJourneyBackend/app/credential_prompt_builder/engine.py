"""证件提示词构建器编排（架构审计 P1-2 包化，自 credential_prompt_builder.py 原样迁入）。"""

from __future__ import annotations

from datetime import date

from ..schemas import PetCredentialKind, PetCredentialPrompt
from ..species import species_display_name, species_image_subject
from ..storage import PetRecord

from .content import PetCredentialContentMixin

class PetCredentialPromptBuilder(PetCredentialContentMixin):
    """Builds reusable GPT Image prompts for fictional PetSoul pet credentials."""

    provider_name = "petsoul-credential-prompt-builder"

    def build_wallet_prompts(
        self,
        *,
        pet: PetRecord,
        issue_date: date | None = None,
        current_location: str = "PetSoul Reappearance Field",
        has_pet_reference: bool = False,
    ) -> list[PetCredentialPrompt]:
        return [
            self.build_prompt(
                kind=kind,
                pet=pet,
                issue_date=issue_date,
                current_location=current_location,
                has_pet_reference=has_pet_reference,
            )
            for kind in (
                PetCredentialKind.identity,
                PetCredentialKind.passport,
                PetCredentialKind.health_record,
                PetCredentialKind.driver_license,
                PetCredentialKind.boarding_pass,
                PetCredentialKind.hotel_key,
            )
        ]

    def build_prompt(
        self,
        *,
        kind: PetCredentialKind | str,
        pet: PetRecord,
        issue_date: date | None = None,
        current_location: str = "PetSoul Reappearance Field",
        has_pet_reference: bool = False,
    ) -> PetCredentialPrompt:
        credential_kind = PetCredentialKind(kind)
        issued = (issue_date or date.today()).isoformat()
        serial = self._serial(kind=credential_kind, pet_id=pet.pet_id)
        reappearance_place = self._reappearance_place(pet)
        fields = self._fields(
            kind=credential_kind,
            pet=pet,
            serial=serial,
            issue_date=issued,
            current_location=reappearance_place,
        )
        title, subtitle = self._title_and_subtitle(credential_kind)
        prompt = self._prompt(
            kind=credential_kind,
            pet=pet,
            title=title,
            subtitle=subtitle,
            serial=serial,
            fields=fields,
            issue_date=issued,
            current_location=reappearance_place,
            has_pet_reference=has_pet_reference,
        )
        return PetCredentialPrompt(
            kind=credential_kind,
            title=title,
            subtitle=subtitle,
            serial=serial,
            image_prompt=prompt,
            size="1536x1024",
            reference_roles=["pet_identity"] if has_pet_reference else [],
            safety_notes=self._safety_notes(credential_kind),
            fields=fields,
        )

    def _prompt(
        self,
        *,
        kind: PetCredentialKind,
        pet: PetRecord,
        title: str,
        subtitle: str,
        serial: str,
        fields: dict[str, str],
        issue_date: str,
        current_location: str,
        has_pet_reference: bool,
    ) -> str:
        species = species_image_subject(pet.pet_type)
        document_direction = self._document_direction(kind)
        reference_line = (
            "pet_identity reference will be supplied; preserve the exact pet identity, species, coat or feather colors, face shape, markings, ears, eyes, expression, collar, and body details."
            if has_pet_reference
            else "If a pet_identity reference is supplied later, use it only to preserve the pet's identity and markings."
        )
        pet_identity_guidance = self._pet_identity_guidance(kind, reference_line)
        visible_content = self._visible_content_instruction(kind, fields)
        visual_system = self._visual_system(kind)
        safety_guards = self._safety_guards(kind)

        return f"""Create one polished full-document image for a fictional PetSoul credential.

Document type:
- {title} / {subtitle}
- Serial: {serial}
- Issued: {issue_date}
- PetSoul reappearance context: {current_location}
- {document_direction}

Pet identity:
- Subject is {pet.name}, a {species}; do not change species.
- Chinese species label: {species_display_name(pet.pet_type)}.
- User-provided DNA cues only: owner title "{pet.dna.owner_title}", personality "{pet.dna.personality or "gentle, curious, loved companion"}", favorite places "{", ".join(pet.dna.favorite_places)}", hobbies "{", ".join(pet.dna.hobby)}", catchphrase "{pet.dna.catchphrase}".
- All other document memories, dates, desk names, care notes, travel desk names, room/seat/gate codes, and planet lore must be fictional GPT/PetSoul generated content for a soul that reappeared on this planet.
- Do not synchronize or infer any real current address, route, GPS location, city stay, medical record, airline, hotel, DMV, or legal status.
{pet_identity_guidance}

{visible_content}

{visual_system}

Safety and realism guards:
{safety_guards}"""
