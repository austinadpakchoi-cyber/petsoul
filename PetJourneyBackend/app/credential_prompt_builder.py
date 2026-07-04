from __future__ import annotations

from datetime import date

from .schemas import PetCredentialKind, PetCredentialPrompt
from .species import species_display_name, species_image_subject
from .storage import PetRecord


class PetCredentialPromptBuilder:
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

    def _pet_identity_guidance(self, kind: PetCredentialKind, reference_line: str) -> str:
        match kind:
            case PetCredentialKind.boarding_pass:
                return "- Do not include a pet portrait or ID photo. Use the pet only as the passenger name on the ticket."
            case PetCredentialKind.hotel_key:
                return "- Do not include a pet portrait, guest name, room number, date, or ID photo. The output is just a hotel key card."
            case _:
                return (
                    f"- {reference_line}\n"
                    "- Put the pet portrait inside the credential as an official-looking document portrait, not a pasted sticker or cutout."
                )

    def _visible_content_instruction(self, kind: PetCredentialKind, fields: dict[str, str]) -> str:
        field_lines = "\n".join(f"- {label}: {value}" for label, value in fields.items())
        match kind:
            case PetCredentialKind.boarding_pass:
                return f"""Required visible ticket content:
{field_lines}
- Use these as boarding-pass fields, not as a passport or certificate table.
- Include a decorative non-scannable barcode or QR-like ticket area labeled fictional / not for real travel."""
            case PetCredentialKind.hotel_key:
                return """Visible content:
- Minimal branding only, such as PETSOUL STAY, SOFT BLANKET INN, LITTLE SOUL REST KEY, FICTIONAL KEEPSAKE.
- Do not print the metadata fields as visible text. Do not show guest name, room number, stay dates, serial number, or care notes on the card face."""
            case _:
                return f"""Required visible field content, arranged cleanly as a collectible document:
{field_lines}"""

    def _visual_system(self, kind: PetCredentialKind) -> str:
        match kind:
            case PetCredentialKind.boarding_pass:
                return """Visual system:
- Clean realistic airline boarding pass, English-dominant, short Chinese labels allowed.
- White paper base with PetSoul amber/teal accent strip, crisp typography, rounded corners, light paper shadow.
- Full ticket visible in frame, front-facing flat lay, no crop, no phone UI.
- Avoid passport guilloche borders, ceremonial seals, MRZ lines, signatures, or large decorative document stamps."""
            case PetCredentialKind.hotel_key:
                return """Visual system:
- Premium physical hotel key card, credit-card proportions, rounded corners, subtle plastic/paper texture, soft shadow.
- Warm cream base with sage/clay accents, abstract window-light or soft lodging illustration, tiny paw emblem.
- Full card visible in frame, no crop, no phone UI.
- Avoid passport guilloche borders, ceremonial seals, field rows, signatures, barcodes, QR codes, or ticket layout."""
            case _:
                return """Unified PetSoul visual system:
- Premium fictional travel-document design, warm cream paper, soft rose, sage, amber, and dusty blue accents.
- Fine guilloche linework, subtle paw seals, soft security-pattern texture, rounded card/page corners, gentle paper grain.
- Bilingual Chinese/English labels where space allows; clean editorial hierarchy; polished but warm, not childish.
- Full document visible in frame, front-facing flat lay or clean scanned-document perspective, no crop, no phone UI.
- Make the layout feel related to the existing PetSoul passport: "PETSOUL REPUBLIC", paw emblem, commemorative edition stamp, and tender companion-world details."""

    def _safety_guards(self, kind: PetCredentialKind) -> str:
        match kind:
            case PetCredentialKind.boarding_pass:
                return """- Fictional PetSoul travel keepsake only.
- Use a common boarding-pass structure, but do not copy any real airline brand, logo, ticket, airport system, or boarding credential exactly.
- No real scannable QR code or machine-readable barcode; decorative non-scannable ticket marks are allowed.
- No real address, no private human face, no official travel authority, and no claim of real boarding permission."""
            case PetCredentialKind.hotel_key:
                return """- Fictional PetSoul hotel key keepsake only.
- Do not copy any real hotel brand, access card, booking confirmation, or room key exactly.
- No guest name, room number, stay date, barcode, QR code, magnetic stripe data, or real access claim.
- No official authority, no private human face, and no real address."""
            case _:
                return """- Fictional commemorative PetSoul document only.
- Do not copy or imitate any real government ID, passport, DMV, driver license, medical card, flag, seal, coat of arms, airline ticket, or legal document.
- No scannable QR code, no barcode, no real address or current city, no real license plate, no watermark, no brand logo, no private human face.
- No claim of real identity, legal driving permission, border permission, medical validity, or official authority."""

    def _document_direction(self, kind: PetCredentialKind) -> str:
        match kind:
            case PetCredentialKind.passport:
                return (
                    "Design a wide passport information page, similar to a ceremonial companion passport: large portrait panel on the left, "
                    "PETS type, PSR issuing country, passport number, soul-country fields, expiry date, paw seal watermark, and MRZ-like decorative line that is clearly fictional."
                )
            case PetCredentialKind.identity:
                return (
                    "Design a wide Pet ID identity card: portrait panel on the left, identity fields on the right, compact PET ID badge, "
                    "soft sage/cream base, paw seal, identity desk stamp, and a clean wallet-card feeling."
                )
            case PetCredentialKind.driver_license:
                return (
                    "Design a wide Paw Driver License: playful but premium amber/cream card, small slow-car silhouette, wheel and road-line motifs, "
                    "permitted class for slow scenic rides, window-seat rider stamp, and clear non-legal fantasy wording."
                )
            case PetCredentialKind.health_record:
                return (
                    "Design a warm fictional PetSoul health record card: care-clinic layout, soft blue-green accents, gentle vaccination/care fields, "
                    "comfort notes derived from DNA, and explicit non-medical keepsake wording."
                )
            case PetCredentialKind.boarding_pass:
                return (
                    "Design a realistic paper or e-boarding pass layout: wide ticket, detachable stub, airline color strip, large route codes, "
                    "flight, seat, gate, boarding time, zone, and a decorative non-scannable ticket code area. Do not make it look like a passport."
                )
            case PetCredentialKind.hotel_key:
                return (
                    "Design a realistic physical hotel key card: one clean card with minimal branding, subtle contactless icon, soft material texture, "
                    "and no guest information, room number, date, field table, portrait, signature, or document layout."
                )

    def _safety_notes(self, kind: PetCredentialKind) -> list[str]:
        match kind:
            case PetCredentialKind.boarding_pass:
                return [
                    "Fictional PetSoul document only; use a common boarding-pass layout without copying any real airline brand or ticket exactly.",
                    "Decorative non-scannable ticket marks are allowed, but no real scannable QR code or machine-readable barcode.",
                    "No claim of real flight, real boarding permission, official travel authority, or private human passenger identity.",
                ]
            case PetCredentialKind.hotel_key:
                return [
                    "Fictional PetSoul document only; render this as a simple hotel key card without copying any real hotel brand, room key, or access card exactly.",
                    "Do not print guest name, room number, stay date, booking data, barcode, QR code, or real access claim.",
                    "Keep it as a simple physical card surface, not an identity document or certificate.",
                ]
            case _:
                return [
                    "Fictional PetSoul document only; do not mimic any real government, DMV, passport, medical, airline, or legal credential.",
                    "Use the pet reference only for identity preservation; redraw a coherent document portrait instead of pasting the source image.",
                    "No real national seals, real flags, scannable QR/barcodes, license plates, signatures of real people, watermarks, or brand logos.",
                ]

    def _fields(
        self,
        *,
        kind: PetCredentialKind,
        pet: PetRecord,
        serial: str,
        issue_date: str,
        current_location: str,
    ) -> dict[str, str]:
        species = species_display_name(pet.pet_type)
        soul_world = self._soul_world(pet)
        favorite_place = pet.dna.favorite_places[0] if pet.dna.favorite_places else "安静的光里"
        hobby = pet.dna.hobby[0] if pet.dna.hobby else "慢慢停留"
        catchphrase = pet.dna.catchphrase or "我重新出现，也在想你"
        base = {
            "姓名 / Name": pet.name,
            "物种 / Species": species,
            "灵魂国度 / Soulland": soul_world,
            "初现地点 / Reappearance": current_location,
            "性格 DNA / Personality DNA": pet.dna.personality or "温柔、好奇",
            "签发日期 / Issue Date": issue_date,
        }
        match kind:
            case PetCredentialKind.passport:
                return {
                    "类型 / Type": "PETS",
                    "签发国 / Issuing Country": "PSR",
                    "护照号码 / Passport No.": serial,
                    **base,
                    "国籍 / Nationality": "PetSoul Citizen",
                    "有效期至 / Expiry Date": "10 years after issue",
                    "通行注记 / Passage Note": "fictional soul-companion journey only",
                }
            case PetCredentialKind.identity:
                return {
                    "证件号码 / ID No.": serial,
                    **base,
                    "毛色特征 / Markings": "preserve from pet_identity reference",
                    "守护人 / Guardian": pet.dna.owner_title or "Owner",
                    "喜欢的地方 / Favorite Place DNA": favorite_place,
                    "口头禅 / Catchphrase": catchphrase,
                }
            case PetCredentialKind.health_record:
                return {
                    "档案号码 / Care No.": serial,
                    **base,
                    "照护偏好 / Care Preference": f"{favorite_place}; {hobby}",
                    "安抚方式 / Comfort Cue": catchphrase,
                    "疫苗记录 / Vaccine": "fictional PetSoul care stamp, not medical proof",
                    "状态 / Status": "stable in companion-world archive",
                }
            case PetCredentialKind.driver_license:
                return {
                    "驾驶证号 / License No.": serial,
                    **base,
                    "准驾类型 / Class": "Cloud Cart · Slow Scenic Only",
                    "驾驶风格 / Driving Style": f"{hobby}; window views first",
                    "状态 / Status": "Fictional keepsake only",
                    "规则 / Rule": "never controls a real route or vehicle",
                }
            case PetCredentialKind.boarding_pass:
                return {
                    "票据号码 / Pass No.": serial,
                    **base,
                    "From": current_location,
                    "To": self._soft_destination(pet),
                    "Seat": f"PAW-{pet.pet_id[-2:].upper()}",
                    "Gate": "Cloud Gate",
                    "Status": "generated when the story needs a long-distance keepsake",
                }
            case PetCredentialKind.hotel_key:
                return {
                    "房卡号码 / Key No.": serial,
                    **base,
                    "Stay": self._soft_lodging_name(pet),
                    "Room": f"SOUL-{pet.pet_id[-4:].upper()}",
                    "Preference": f"quiet corner; {favorite_place}",
                    "Status": "fictional rest-stop keepsake only",
                }

    def _serial(self, *, kind: PetCredentialKind, pet_id: str) -> str:
        suffix = pet_id[-6:].upper()
        match kind:
            case PetCredentialKind.passport:
                return f"PS{suffix}"
            case PetCredentialKind.identity:
                return f"PJ-ID-{suffix}"
            case PetCredentialKind.driver_license:
                return f"PJ-DL-{suffix}"
            case PetCredentialKind.health_record:
                return f"PJ-CARE-{suffix}"
            case PetCredentialKind.boarding_pass:
                return f"PJ-AIR-{suffix}"
            case PetCredentialKind.hotel_key:
                return f"PJ-STAY-{suffix}"

    def _title_and_subtitle(self, kind: PetCredentialKind) -> tuple[str, str]:
        match kind:
            case PetCredentialKind.passport:
                return ("PETSOUL PASSPORT", "宠物灵魂护照")
            case PetCredentialKind.identity:
                return ("PETSOUL IDENTITY CARD", "宠物身份卡")
            case PetCredentialKind.driver_license:
                return ("PAW DRIVER LICENSE", "爪爪驾驶证")
            case PetCredentialKind.health_record:
                return ("PETSOUL HEALTH RECORD", "健康证 / 疫苗本")
            case PetCredentialKind.boarding_pass:
                return ("PETSOUL BOARDING PASS", "登机牌")
            case PetCredentialKind.hotel_key:
                return ("PETSOUL HOTEL KEY CARD", "酒店房卡")

    def _soul_world(self, pet: PetRecord) -> str:
        return {
            "dog": "汪汪星 / Pawland",
            "cat": "喵喵星 / Meowland",
            "parrot": "鹦羽星 / Featherland",
            "rabbit": "月兔星 / Moonburrow",
            "hamster": "软爪星 / Softpaw",
            "bird": "啾啾星 / Chirpland",
            "other": "小动物星 / Companionland",
        }.get(pet.pet_type.value, "小动物星 / Companionland")

    def _reappearance_place(self, pet: PetRecord) -> str:
        places = [
            "彩虹桥东侧 / Rainbow Bridge East",
            "晨雾草地 / Morning Mist Meadow",
            "云边窗台 / Cloudside Window",
            "软风小站 / Softwind Station",
            "月光口袋 / Moonlit Pocket",
            "回声花园 / Echo Garden",
        ]
        return places[self._seed_index(pet, len(places))]

    def _soft_destination(self, pet: PetRecord) -> str:
        destinations = [
            "Next Warm Light",
            "Quiet Window Seat",
            "Soft Grass Stop",
            "Tiny Sunbeam Gate",
            "Companion Cloud",
        ]
        return destinations[self._seed_index(pet, len(destinations), salt=17)]

    def _soft_lodging_name(self, pet: PetRecord) -> str:
        lodgings = [
            "Soft Blanket Inn",
            "Window Light House",
            "Little Paw Rest Desk",
            "Rainbow Nap Hotel",
            "Cloud Pillow Room",
        ]
        return lodgings[self._seed_index(pet, len(lodgings), salt=31)]

    def _seed_index(self, pet: PetRecord, size: int, salt: int = 0) -> int:
        total = sum(ord(ch) for ch in f"{pet.pet_id}:{pet.name}:{pet.pet_type.value}") + salt
        return total % max(1, size)
