"""Immutable internal contracts. No storage, media bytes, credentials or public API models."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class PhotoDirectorError(ValueError):
    """Stable reason codes only: never echo rejected private input."""


@dataclass(frozen=True, slots=True)
class PhotoVersions:
    identity: int
    dna: int
    privacy: int
    activity: int


@dataclass(frozen=True, slots=True)
class IdentityReference:
    pet_id: str
    household_id: str
    species: str
    origin: str  # owner_original / original_companion / real_archive
    reference_id: str
    sha256: str
    version: int
    appearance_tags: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "appearance_tags", tuple(self.appearance_tags))


@dataclass(frozen=True, slots=True)
class MediaReference:
    """Metadata for an asset already resolved/checked by the authorized media layer.

    Not proof of a provider send. A must bind these IDs and digests to actual bytes.
    """
    reference_id: str
    sha256: str
    role: str
    source: str
    pet_id: str
    household_id: str
    mime_type: str
    ready: bool
    authorized: bool
    event_id: str | None = None
    place_id: str | None = None


@dataclass(frozen=True, slots=True)
class PhotoDNA:
    version: int
    projection_id: str
    purpose: str = "photo_generation"
    personality: tuple[str, ...] = ()
    habits: tuple[str, ...] = ()
    interests: tuple[str, ...] = ()
    preferences: tuple[str, ...] = ()

    def __post_init__(self):
        for field in ("personality", "habits", "interests", "preferences"):
            object.__setattr__(self, field, tuple(getattr(self, field)))


@dataclass(frozen=True, slots=True)
class SceneFact:
    fact_id: str
    token: str
    pet_id: str
    household_id: str
    event_id: str
    verified: bool


@dataclass(frozen=True, slots=True)
class SceneFacts:
    event_id: str
    revision: int
    scene: str
    captured_at: datetime
    city: str
    place_id: str
    place_label: str
    committed: bool
    origin: str  # world_event / owner_directed / evaluation_fixture
    narrative: str  # daily_life / fictional_adventure / film_scene
    facts: tuple[SceneFact, ...]

    def __post_init__(self):
        object.__setattr__(self, "facts", tuple(self.facts))


@dataclass(frozen=True, slots=True)
class CompanionReference:
    """A second subject in the same photo.

    Kept separate from `IdentityReference` because a companion carries its own consent:
    being in the same household is not on its own permission to put another pet in a
    generated picture.
    """
    pet_id: str
    household_id: str
    species: str
    reference_id: str
    sha256: str
    version: int
    consent_scope: str  # photo_together / none
    appearance_tags: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "appearance_tags", tuple(self.appearance_tags))


@dataclass(frozen=True, slots=True)
class PhotoContext:
    pet_id: str
    household_id: str
    versions: PhotoVersions
    identity: IdentityReference
    dna: PhotoDNA
    scene: SceneFacts
    references: tuple[MediaReference, ...]
    companions: tuple[CompanionReference, ...] = ()
    requested_camera: str = "auto"
    config_version: str = "photo-config-v1"

    def __post_init__(self):
        object.__setattr__(self, "references", tuple(self.references))
        object.__setattr__(self, "companions", tuple(self.companions))


@dataclass(frozen=True, slots=True)
class PhotoAccess:
    """Fresh caller projection, including for cache reuse. Not an authorization service."""
    pet_id: str
    household_id: str
    versions: PhotoVersions
    event_revision: int
    can_access: bool
    generated_photos: bool
    photo_dna: bool
    reference_use: bool
    text_director: bool = False
    # 把另一只宠物放进同一张照片，需要它那边也同意；同住一个家庭不等于默认允许。
    companion_photos: bool = False



@dataclass(frozen=True, slots=True)
class SceneDraft:
    """The one creative decision per event: how to frame an already-committed fact.

    `recipe` picks the whole shot -- scene, camera, composition and action together --
    because those constrain each other: a cockpit shot cannot be hand-held, a mirror
    selfie needs a mirror, a friend shot needs a friend who was actually there.
    `camera` and `composition` are recorded as they were resolved from the recipe, so
    the stored draft stays readable without re-deriving it.
    """
    recipe: str
    camera: str
    composition: str
    expression: str
    visible_facts: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "visible_facts", tuple(self.visible_facts))


@dataclass(frozen=True, slots=True)
class ReferenceSlot:
    """One reference image in the exact order it will be sent to the image provider."""
    position: int
    role: str
    reference_id: str
    sha256: str


@dataclass(frozen=True, slots=True)
class TextCallRecord:
    """What actually happened on the director's own text budget.

    `outcome` is one of: skipped / rule_only / sent_ok / sent_unknown / refused / invalid_output.
    `sent_ok` and `sent_unknown` both mean a request left the process and may have been billed;
    `unknown` is never rewritten into a failure, and is never auto-resent.
    """
    outcome: str
    operation_id: str
    reserved: bool
    provider_label: str | None = None
    requested_model: str | None = None
    effective_model: str | None = None
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class DirectedPhoto:
    """Compiled, ready-to-send instruction. Holds no media bytes and no raw DNA."""
    pet_id: str
    household_id: str
    event_id: str
    scene: str
    prompt: str
    negative_prompt: str
    size: str
    references: tuple[ReferenceSlot, ...]
    draft: SceneDraft
    directed_by: str  # rule / model
    fallback_reason: str | None
    versions: PhotoVersions
    identity_reference_id: str
    identity_sha256: str
    prompt_version: str
    config_version: str
    context_key: str
    text_call: TextCallRecord
    story_mode: str = "daily_life"
    # world_event / owner_directed / evaluation_fixture，原样来自 SceneFacts.origin
    scene_origin: str = "world_event"
    companion_pet_ids: tuple[str, ...] = ()
    prompt_checks: tuple[str, ...] = ()
    # 看真图时逐条对照的人审要点。这是给人用的清单，**不是**程序给出的通过结论。
    review_points: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "references", tuple(self.references))
        object.__setattr__(self, "companion_pet_ids", tuple(self.companion_pet_ids))
        object.__setattr__(self, "prompt_checks", tuple(self.prompt_checks))
        object.__setattr__(self, "review_points", tuple(self.review_points))

    def evidence(self) -> dict:
        """Loggable summary. Deliberately excludes the prompt body and every DNA value."""
        return {
            "pet_id": self.pet_id,
            "household_id": self.household_id,
            "event_id": self.event_id,
            "scene": self.scene,
            # 这张照片的由来。不记下来，"虚构题材有没有被记成真事"就没人验得了。
            "scene_origin": self.scene_origin,
            "recipe": self.draft.recipe,
            "camera": self.draft.camera,
            "composition": self.draft.composition,
            "visible_facts": list(self.draft.visible_facts),
            "directed_by": self.directed_by,
            "fallback_reason": self.fallback_reason,
            "identity_reference_id": self.identity_reference_id,
            "identity_sha256": self.identity_sha256,
            "companion_pet_ids": list(self.companion_pet_ids),
            "story_mode": self.story_mode,
            "references": [(slot.position, slot.role, slot.reference_id) for slot in self.references],
            "prompt_version": self.prompt_version,
            "config_version": self.config_version,
            "context_key": self.context_key,
            "prompt_checks": list(self.prompt_checks),
            "review_points": list(self.review_points),
            "text_call": {
                "outcome": self.text_call.outcome,
                "operation_id": self.text_call.operation_id,
                "reserved": self.text_call.reserved,
                "provider_label": self.text_call.provider_label,
                "requested_model": self.text_call.requested_model,
                "effective_model": self.text_call.effective_model,
                "latency_ms": self.text_call.latency_ms,
                "prompt_tokens": self.text_call.prompt_tokens,
                "completion_tokens": self.text_call.completion_tokens,
                "reason": self.text_call.reason,
            },
        }
