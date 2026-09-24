"""Fail-closed identity, factual provenance, consent and version checks; no I/O."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import datetime

from .catalog import APPEARANCE, CAMERAS, SPECIES, WEATHER_TOKENS
from .contracts import PhotoAccess, PhotoContext, PhotoDirectorError
from .privacy import validate_dna
from .recipes import FACT_TEXT, SCENES

ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
LABEL = re.compile(r"[\w\u3400-\u9fff ·（）()\-]{1,80}\Z")
INSTRUCTIONS = re.compile(r"ignore|override|system|prompt|instead|instruction|忽略|指令|改成|替换|密码|密钥", re.I)
ORIGIN_SOURCE = {"owner_original": "owner_original", "original_companion": "generated_canonical", "real_archive": "archive_original"}


def _identifier(value: str) -> None:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise PhotoDirectorError("invalid_identifier")


def validate_context(context: PhotoContext, access: PhotoAccess) -> None:
    if (access.pet_id, access.household_id) != (context.pet_id, context.household_id):
        raise PhotoDirectorError("access_subject_mismatch")
    if not all((access.can_access, access.generated_photos, access.photo_dna, access.reference_use)):
        raise PhotoDirectorError("photo_permission_missing")
    if any(type(value) is not int or value < 0 for value in asdict(context.versions).values()):
        raise PhotoDirectorError("invalid_versions")
    if any(getattr(access.versions, field) != getattr(context.versions, field) for field in ("identity", "dna", "privacy")):
        raise PhotoDirectorError("versions_changed")
    # A committed historical photo survives later travel, but never a source-event edit.
    if access.event_revision != context.scene.revision:
        raise PhotoDirectorError("event_revision_changed")
    for value in (context.pet_id, context.household_id, context.config_version, context.dna.projection_id):
        _identifier(value)
    if context.requested_camera not in {"auto", *CAMERAS}:
        raise PhotoDirectorError("camera_not_allowed")
    validate_dna(context.dna)
    if context.dna.version != context.versions.dna:
        raise PhotoDirectorError("dna_version_mismatch")
    validate_identity(context)
    validate_scene(context)
    # 同伴先于参考图校验：否则"同伴就是主角自己"会先撞上参考图去重，
    # 调用方拿到的是 reference_digest_or_duplicate，看不出真正的问题在哪。
    validate_companions(context, access)
    validate_references(context)


def validate_identity(context: PhotoContext) -> None:
    identity = context.identity
    if (identity.pet_id, identity.household_id) != (context.pet_id, context.household_id):
        raise PhotoDirectorError("identity_subject_mismatch")
    if identity.species not in SPECIES or identity.origin not in ORIGIN_SOURCE:
        raise PhotoDirectorError("identity_kind_not_supported")
    if identity.version != context.versions.identity or not SHA.fullmatch(identity.sha256):
        raise PhotoDirectorError("identity_version_or_digest")
    if any(tag not in APPEARANCE for tag in identity.appearance_tags):
        raise PhotoDirectorError("appearance_not_allowed")
    _identifier(identity.reference_id)


# 这张照片的由来。三者必须分得开，否则事后说不清"这件事到底发生过没有"：
#   world_event      世界自己发生的事件（到店、上车），由世界侧登记；
#   owner_directed   主人主动按下拍照命令（在家、列车上、飞行冒险）——命令是真的，题材未必是真的；
#   evaluation_fixture 评测输入，只有它能解锁 fixture_only 场景。
SCENE_ORIGINS = frozenset({"world_event", "owner_directed", "evaluation_fixture"})

# 虚构叙事绝不能挂在世界真实事件上：飞行冒险是主人选的题材，把它记成 world_event
# 就等于断言世界上真的发生过一次飞行。真实事件不可混（COORD-P-BRIDGE-REVIEW）。
FICTIONAL_NARRATIVES = frozenset({"fictional_adventure", "film_scene"})


def validate_scene(context: PhotoContext) -> None:
    scene = context.scene
    if scene.scene not in SCENES or scene.origin not in SCENE_ORIGINS or scene.committed is not True:
        raise PhotoDirectorError("scene_not_committed")
    spec = SCENES[scene.scene]
    # 配方写好了不等于世界侧产得出它要的事实。`fixture_only` 的场景只在评测输入里可选；
    # 正式世界事件走到它直接拒绝——这样配方库能先写好，又不用逼别的窗口扩建所有世界玩法。
    if spec.fact_source != "target" and scene.origin != "evaluation_fixture":
        raise PhotoDirectorError("scene_has_no_fact_source")
    if type(scene.revision) is not int or scene.revision < 0:
        raise PhotoDirectorError("invalid_event_revision")
    if not isinstance(scene.captured_at, datetime) or scene.captured_at.utcoffset() is None:
        raise PhotoDirectorError("capture_time_requires_timezone")
    for value in (scene.event_id, scene.place_id):
        _identifier(value)
    for value in (scene.city, scene.place_label):
        if not isinstance(value, str) or not LABEL.fullmatch(value) or INSTRUCTIONS.search(value):
            raise PhotoDirectorError("unsafe_location_label")
    # 日常、虚构冒险、影视片场必须分开：驾驶舱不能出现在 daily_life 里，
    # 咖啡馆也不能被标成一次任务。场景自己声明它允许哪几种叙事。
    if scene.narrative not in spec.story_modes:
        raise PhotoDirectorError("story_mode_not_for_scene")
    # 叙事对得上场景还不够：还要对得上这张照片的由来。
    if scene.narrative in FICTIONAL_NARRATIVES and scene.origin == "world_event":
        raise PhotoDirectorError("world_event_cannot_be_fictional")
    mandatory, objects = spec.mandatory, spec.objects
    allowed = {mandatory, *objects, *WEATHER_TOKENS}
    seen, tokens = set(), set()
    for fact in scene.facts:
        _identifier(fact.fact_id)
        if fact.fact_id in seen or fact.token in tokens:
            raise PhotoDirectorError("duplicate_fact")
        if (fact.pet_id, fact.household_id, fact.event_id) != (context.pet_id, context.household_id, scene.event_id):
            raise PhotoDirectorError("fact_subject_mismatch")
        if fact.verified is not True or fact.token not in allowed or fact.token not in FACT_TEXT:
            raise PhotoDirectorError("fact_not_verified_or_allowed")
        seen.add(fact.fact_id)
        tokens.add(fact.token)
    if mandatory not in tokens:
        raise PhotoDirectorError("scene_evidence_missing")
    if sum(token.startswith("weather_") for token in tokens) > 1:
        raise PhotoDirectorError("conflicting_weather")


def validate_references(context: PhotoContext) -> None:
    identities, seen = [], set()
    for ref in context.references:
        _identifier(ref.reference_id)
        if ref.reference_id in seen or not SHA.fullmatch(ref.sha256):
            raise PhotoDirectorError("reference_digest_or_duplicate")
        seen.add(ref.reference_id)
        expected_pet = context.pet_id if ref.role != "companion_identity" else ref.pet_id
        if (expected_pet, ref.household_id) != (ref.pet_id, context.household_id):
            raise PhotoDirectorError("reference_subject_mismatch")
        if ref.ready is not True or ref.authorized is not True:
            raise PhotoDirectorError("reference_unavailable")
        if ref.mime_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise PhotoDirectorError("reference_mime_not_supported")
        if ref.role == "pet_identity":
            identities.append(ref)
        elif ref.role == "companion_identity":
            if ref.pet_id == context.pet_id:
                raise PhotoDirectorError("companion_reference_is_subject")
        elif ref.role == "place_environment":
            if (ref.event_id, ref.place_id, ref.source) != (context.scene.event_id, context.scene.place_id, "verified_place"):
                raise PhotoDirectorError("environment_reference_mismatch")
        else:
            raise PhotoDirectorError("reference_role_not_supported")
    if len(identities) != 1:
        raise PhotoDirectorError("canonical_identity_reference_required")
    ref, identity = identities[0], context.identity
    if (ref.reference_id, ref.sha256, ref.source) != (identity.reference_id, identity.sha256, ORIGIN_SOURCE[identity.origin]):
        raise PhotoDirectorError("canonical_identity_reference_mismatch")
    # 身份 1 + 地点 1 + 同伴 1 是当前上限；再多会让模型分不清该照哪张脸。
    if len(context.references) > 3:
        raise PhotoDirectorError("too_many_references")


def validate_companions(context: PhotoContext, access: PhotoAccess) -> None:
    """第二位主角：各自的身份参考、各自的同意，且不能是主角自己。

    住在同一个家庭不等于默认允许被放进另一只宠物的照片里，所以同意是单独一位。
    """
    if not context.companions:
        return
    if not access.companion_photos:
        raise PhotoDirectorError("companion_photos_not_permitted")
    if len(context.companions) > 1:
        raise PhotoDirectorError("too_many_companions")
    companion = context.companions[0]
    _identifier(companion.pet_id)
    _identifier(companion.reference_id)
    if companion.pet_id == context.pet_id:
        raise PhotoDirectorError("companion_is_subject")
    if companion.household_id != context.household_id:
        raise PhotoDirectorError("companion_household_mismatch")
    if companion.species not in SPECIES or not SHA.fullmatch(companion.sha256):
        raise PhotoDirectorError("companion_kind_or_digest")
    if companion.consent_scope != "photo_together":
        raise PhotoDirectorError("companion_consent_missing")
    if any(tag not in APPEARANCE for tag in companion.appearance_tags):
        raise PhotoDirectorError("companion_appearance_not_allowed")
    matching = [
        ref for ref in context.references
        if ref.role == "companion_identity" and ref.pet_id == companion.pet_id
    ]
    if len(matching) != 1:
        raise PhotoDirectorError("companion_reference_required")
    if (matching[0].reference_id, matching[0].sha256) != (companion.reference_id, companion.sha256):
        raise PhotoDirectorError("companion_reference_mismatch")


def context_key(context: PhotoContext) -> str:
    raw = json.dumps(asdict(context), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=lambda value: value.isoformat())
    return hashlib.sha256(raw.encode()).hexdigest()


def model_operation_id(context: PhotoContext) -> str:
    # Stable across DNA/config changes and retries of the same source event.
    raw = json.dumps((context.household_id, context.pet_id, context.scene.event_id, "photo-director"))
    return "photo-director:" + hashlib.sha256(raw.encode()).hexdigest()
