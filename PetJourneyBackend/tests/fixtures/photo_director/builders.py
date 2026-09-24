"""Build PhotoContext / PhotoAccess objects from the fictional fixture file.

Nothing here reads a real user photo, a real household or a real place; the fixture is
hand-written. Tests import these builders instead of constructing contexts inline so an
added contract field surfaces in one place.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.web_photo_director import (
    CompanionReference,
    IdentityReference,
    MediaReference,
    PhotoAccess,
    PhotoContext,
    PhotoVersions,
    SceneFact,
    SceneFacts,
    project_photo_dna,
)
from app.web_photo_director.catalog import DNA_FIELDS
from app.web_photo_director.recipes import SCENES

FIXTURE = Path(__file__).with_name("scenes.json")
DATA = json.loads(FIXTURE.read_text(encoding="utf-8"))

DEFAULT_VERSIONS = PhotoVersions(identity=4, dna=2, privacy=6, activity=9)
PLACE_REFERENCE_SHA = "3333333333333333333333333333333333333333333333333333333333333333"


def build_versions(**overrides) -> PhotoVersions:
    values = {"identity": 4, "dna": 2, "privacy": 6, "activity": 9}
    values.update(overrides)
    return PhotoVersions(**values)


def build_identity(pet_key: str, versions: PhotoVersions) -> IdentityReference:
    pet = DATA["pets"][pet_key]
    return IdentityReference(
        pet_id=pet["pet_id"],
        household_id=pet["household_id"],
        species=pet["species"],
        origin=pet["origin"],
        reference_id=pet["reference_id"],
        sha256=pet["sha256"],
        version=versions.identity,
        appearance_tags=tuple(pet["appearance_tags"]),
    )


def build_dna(pet_key: str, versions: PhotoVersions, *, allowed_fields=None, raw=None):
    pet = DATA["pets"][pet_key]
    return project_photo_dna(
        raw if raw is not None else pet["dna"],
        allowed_fields=frozenset(allowed_fields if allowed_fields is not None else DNA_FIELDS),
        version=versions.dna,
        projection_id=f"fx-dnaproj-{pet_key}-{versions.dna}",
    )


def build_scene(scene_key: str, pet_key: str, *, facts=None, pet_id=None, **overrides) -> SceneFacts:
    spec = DATA["scenes"][scene_key]
    pet = dict(DATA["pets"][pet_key])
    if pet_id is not None:
        pet["pet_id"] = pet_id  # 执行单用真实宠物重编时，事实的归属也要跟着换
    tokens = list(spec["facts"] if facts is None else facts)
    event_id = overrides.pop("event_id", spec["event_id"])
    values = {
        "event_id": event_id,
        "revision": spec["revision"],
        "scene": spec["scene"],
        "captured_at": datetime.fromisoformat(spec["captured_at"]),
        "city": spec["city"],
        "place_id": spec["place_id"],
        "place_label": spec["place_label"],
        "committed": True,
        # 四个目标场景走正式世界事件；其余场景世界侧还产不出事实，
        # 只能标成评测输入——这正是生产路径闸门要区分的东西。
        # 虚构题材的场景由主人下令发起，不是世界自己发生的事件——不能标成 world_event
        "origin": _origin_for(spec["scene"], spec.get("narrative")),
        "narrative": spec["narrative"],
    }
    values.update(overrides)
    values["facts"] = tuple(
        SceneFact(
            fact_id=f"{event_id}:{token}",
            token=token,
            pet_id=pet["pet_id"],
            household_id=pet["household_id"],
            event_id=event_id,
            verified=True,
        )
        for token in tokens
    )
    return SceneFacts(**values)


def build_identity_media(pet_key: str) -> MediaReference:
    pet = DATA["pets"][pet_key]
    source = {
        "owner_original": "owner_original",
        "original_companion": "generated_canonical",
        "real_archive": "archive_original",
    }[pet["origin"]]
    return MediaReference(
        reference_id=pet["reference_id"],
        sha256=pet["sha256"],
        role="pet_identity",
        source=source,
        pet_id=pet["pet_id"],
        household_id=pet["household_id"],
        mime_type="image/jpeg",
        ready=True,
        authorized=True,
    )


def build_place_media(scene_key: str, pet_key: str, *, event_id=None) -> MediaReference:
    spec = DATA["scenes"][scene_key]
    pet = DATA["pets"][pet_key]
    return MediaReference(
        reference_id=f"fx-ref-place-{scene_key}",
        sha256=PLACE_REFERENCE_SHA,
        role="place_environment",
        source="verified_place",
        pet_id=pet["pet_id"],
        household_id=pet["household_id"],
        mime_type="image/jpeg",
        ready=True,
        authorized=True,
        event_id=event_id or spec["event_id"],
        place_id=spec["place_id"],
    )


def build_companion(pet_key: str, subject_key: str, *, consent: str = "photo_together") -> CompanionReference:
    """第二位主角。注意 household 跟随主角，但同意是它自己那一份。"""
    pet = DATA["pets"][pet_key]
    subject = DATA["pets"][subject_key]
    return CompanionReference(
        pet_id=pet["pet_id"],
        household_id=subject["household_id"],
        species=pet["species"],
        reference_id=pet["reference_id"],
        sha256=pet["sha256"],
        version=DEFAULT_VERSIONS.identity,
        consent_scope=consent,
        appearance_tags=tuple(pet["appearance_tags"]),
    )


def build_companion_media(pet_key: str, subject_key: str) -> MediaReference:
    pet = DATA["pets"][pet_key]
    subject = DATA["pets"][subject_key]
    return MediaReference(
        reference_id=pet["reference_id"],
        sha256=pet["sha256"],
        role="companion_identity",
        source="owner_original",
        pet_id=pet["pet_id"],
        household_id=subject["household_id"],
        mime_type="image/jpeg",
        ready=True,
        authorized=True,
    )


def _origin_for(scene: str, narrative: str | None) -> str:
    """这条 fixture 的由来。`fixture_only` 场景只能是评测输入；虚构题材算主人下令。"""
    if SCENES[scene].fact_source != "target":
        return "evaluation_fixture"
    return "owner_directed" if (narrative or "daily_life") != "daily_life" else "world_event"


def build_context(
    scene_key: str,
    pet_key: str = "fx-pet-amber",
    *,
    versions: PhotoVersions | None = None,
    references=None,
    with_place_reference: bool = False,
    requested_camera: str = "auto",
    dna_raw=None,
    dna_allowed=None,
    scene=None,
    companion_key: str | None = None,
    companion_consent: str = "photo_together",
    companions=None,
) -> PhotoContext:
    versions = versions or DEFAULT_VERSIONS
    pet = DATA["pets"][pet_key]
    scene_facts = scene if scene is not None else build_scene(scene_key, pet_key)
    if companions is None:
        companions = (
            (build_companion(companion_key, pet_key, consent=companion_consent),)
            if companion_key else ()
        )
    if references is None:
        references = [build_identity_media(pet_key)]
        if companion_key:
            references.append(build_companion_media(companion_key, pet_key))
        if with_place_reference:
            references.append(build_place_media(scene_key, pet_key, event_id=scene_facts.event_id))
    return PhotoContext(
        pet_id=pet["pet_id"],
        household_id=pet["household_id"],
        versions=versions,
        identity=build_identity(pet_key, versions),
        dna=build_dna(pet_key, versions, allowed_fields=dna_allowed, raw=dna_raw),
        scene=scene_facts,
        references=tuple(references),
        companions=tuple(companions),
        requested_camera=requested_camera,
    )


def build_access(context: PhotoContext, **overrides) -> PhotoAccess:
    values = {
        "pet_id": context.pet_id,
        "household_id": context.household_id,
        "versions": context.versions,
        "event_revision": context.scene.revision,
        "can_access": True,
        "generated_photos": True,
        "photo_dna": True,
        "reference_use": True,
        "text_director": False,
        "companion_photos": bool(context.companions),
    }
    values.update(overrides)
    return PhotoAccess(**values)
