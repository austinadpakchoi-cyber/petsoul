"""草稿校验与模型输出解析。Fail-closed，无 I/O。

草稿是创作介入的唯一位置。它可以决定**怎么取景**一件已经成立的事，
但不能引入新的宠物、地点、事件、物件或天气。任何超出封闭词表的东西一律拒绝、
不做修补——一条无效的模型回复会退回规则导演，而不是悄悄变成一个稍有出入的世界。
"""
from __future__ import annotations

import json

from .catalog import (
    CAMERAS,
    CAMERAS_NEEDING_DEVICE,
    CAMERAS_NEEDING_PHOTOGRAPHER,
    EXPRESSIONS,
    WEATHER_TOKENS,
)
from .contracts import PhotoContext, PhotoDirectorError, SceneDraft
from .recipes import NON_VISIBLE_FACTS, RECIPES, SCENES

MAX_VISIBLE_FACTS = 5
DRAFT_FIELDS = frozenset({"recipe", "expression", "visible_facts"})
# 这两种镜头需要现场真的具备条件，不能靠"看起来像"就用
CAMERA_PRECONDITION = {
    "friend_camera": ("photographer_present", "photographer_not_present"),
    "mirror_selfie": ("gym_mirror", "mirror_not_present"),
}


def assert_fact_source(context: PhotoContext) -> None:
    """纵深防御：主围栏在 `validation.validate_scene`，这里挡住绕过它直接喂 draft 的调用方。"""
    spec = SCENES.get(context.scene.scene)
    if spec is None:
        raise PhotoDirectorError("scene_not_supported")
    if spec.fact_source != "target" and context.scene.origin != "evaluation_fixture":
        raise PhotoDirectorError("scene_has_no_fact_source")


def verified_tokens(context: PhotoContext) -> frozenset[str]:
    return frozenset(fact.token for fact in context.scene.facts if fact.verified)


def recipe_of(name: str):
    if name not in RECIPES:
        raise PhotoDirectorError("recipe_not_allowed")
    return RECIPES[name]


def eligible_recipes(context: PhotoContext) -> tuple[str, ...]:
    """这次事件真正拍得出来的那些配方。

    过滤条件是"事实"而不是"好看"：场景对得上、叙事模式对得上、必需事实都已核验、
    镜头的现场前提成立（有同伴、有镜子、有自己的设备），双宠配方要有第二位主角。
    """
    scene = context.scene.scene
    if SCENES[scene].fact_source != "target" and context.scene.origin != "evaluation_fixture":
        return ()  # 世界侧还产不出这个场景的事实，这里就不该有可选配方
    available = verified_tokens(context)
    has_companion = bool(context.companions)
    out = []
    for name, recipe in RECIPES.items():
        if recipe.scene != scene or context.scene.narrative not in recipe.story_modes:
            continue
        if not recipe.requires <= available:
            continue
        if recipe.subjects == 2 and not has_companion:
            continue
        if recipe.subjects == 1 and has_companion:
            continue
        if not _camera_possible(recipe.camera, available):
            continue
        if context.requested_camera != "auto" and recipe.camera != context.requested_camera:
            continue
        out.append(name)
    return tuple(sorted(out))


def _camera_possible(camera: str, available: frozenset[str]) -> bool:
    token = CAMERA_PRECONDITION.get(camera)
    if token is not None and token[0] not in available:
        return False
    if camera in CAMERAS_NEEDING_DEVICE and camera == "mirror_selfie" and "own_device" not in available:
        return False
    return True


def validate_draft(draft: SceneDraft, context: PhotoContext) -> None:
    assert_fact_source(context)
    recipe = recipe_of(draft.recipe)
    scene = context.scene.scene
    if recipe.scene != scene:
        raise PhotoDirectorError("recipe_scene_mismatch")
    if context.scene.narrative not in recipe.story_modes:
        raise PhotoDirectorError("recipe_story_mode_mismatch")

    # 镜头与构图由配方决定，不接受单独改写——否则咖啡馆会被套上车窗构图。
    if draft.camera != recipe.camera:
        raise PhotoDirectorError("camera_not_for_recipe")
    if draft.composition != recipe.composition:
        raise PhotoDirectorError("composition_not_for_recipe")
    if draft.camera not in CAMERAS:
        raise PhotoDirectorError("camera_not_allowed")
    # 主人明确点了自拍就得是自拍，导演不能因为别的更好拍就换掉。
    if context.requested_camera != "auto" and draft.camera != context.requested_camera:
        raise PhotoDirectorError("requested_camera_overridden")
    if draft.expression not in EXPRESSIONS:
        raise PhotoDirectorError("expression_not_allowed")

    available = verified_tokens(context)
    if not recipe.requires <= available:
        raise PhotoDirectorError("recipe_requires_unverified_fact")
    precondition = CAMERA_PRECONDITION.get(draft.camera)
    if precondition is not None and precondition[0] not in available:
        # 没有同伴在场就不能说"同伴拍的"，没有镜子就不能说"镜中自拍"。
        raise PhotoDirectorError(precondition[1])
    if draft.camera in CAMERAS_NEEDING_DEVICE and draft.camera == "mirror_selfie" \
            and "own_device" not in available:
        raise PhotoDirectorError("own_device_not_present")

    if recipe.subjects == 2 and len(context.companions) != 1:
        raise PhotoDirectorError("companion_required_for_recipe")
    if recipe.subjects == 1 and context.companions:
        raise PhotoDirectorError("companion_not_allowed_for_recipe")

    _validate_visible_facts(draft, context, recipe)


def _validate_visible_facts(draft: SceneDraft, context: PhotoContext, recipe) -> None:
    scene_spec = SCENES[context.scene.scene]
    available = verified_tokens(context)
    allowed = {scene_spec.mandatory, *scene_spec.objects, *WEATHER_TOKENS}

    if len(draft.visible_facts) > MAX_VISIBLE_FACTS:
        raise PhotoDirectorError("too_many_visible_facts")
    if len(set(draft.visible_facts)) != len(draft.visible_facts):
        raise PhotoDirectorError("duplicate_visible_fact")
    for token in draft.visible_facts:
        if token not in allowed:
            raise PhotoDirectorError("visible_fact_not_for_scene")
        if token not in available:
            # 这一条挡住的是"它到了咖啡馆但没点单，画面里却有一杯咖啡"。
            raise PhotoDirectorError("visible_fact_not_verified")
    if scene_spec.mandatory not in draft.visible_facts:
        raise PhotoDirectorError("mandatory_fact_not_visible")
    must_show = recipe.requires - {scene_spec.mandatory} - NON_VISIBLE_FACTS
    if not must_show <= set(draft.visible_facts):
        raise PhotoDirectorError("recipe_fact_not_visible")
    if NON_VISIBLE_FACTS & set(draft.visible_facts):
        # 同伴在场是前提，不是画面内容——画面里不该出现拍摄者。
        raise PhotoDirectorError("precondition_is_not_visible_content")
    if sum(token in WEATHER_TOKENS for token in draft.visible_facts) > 1:
        raise PhotoDirectorError("conflicting_weather")


def normalise_draft(
    *,
    recipe: str,
    expression: str,
    visible_facts: tuple[str, ...],
    context: PhotoContext,
) -> SceneDraft:
    """按配方补齐镜头与构图，然后校验。"""
    spec = recipe_of(recipe)
    draft = SceneDraft(
        recipe=recipe,
        camera=spec.camera,
        composition=spec.composition,
        expression=expression,
        visible_facts=visible_facts,
    )
    validate_draft(draft, context)
    return draft


def parse_model_draft(text: str, context: PhotoContext) -> SceneDraft:
    """解析一次结构化模型回复。任何异常都抛 PhotoDirectorError。

    调用方把任何抛出都当作 `invalid_output` 并退回规则；**不会重新提问**，
    因为每个事件只有一次导演文本请求。
    """
    if not isinstance(text, str) or not text.strip():
        raise PhotoDirectorError("model_output_empty")
    body = text.strip()
    if body.startswith("```"):
        body = body.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, ValueError) as exc:
        raise PhotoDirectorError("model_output_not_json") from exc
    if not isinstance(parsed, dict):
        raise PhotoDirectorError("model_output_not_object")
    # 未知键一律拒绝而不是忽略：回复里带 `city` 或 `pet_name`，
    # 说明它在尝试重新定义这个世界，这件事我们要当作失败看见。
    if not set(parsed) <= DRAFT_FIELDS:
        raise PhotoDirectorError("model_output_unknown_field")
    if not {"recipe", "expression"} <= set(parsed):
        raise PhotoDirectorError("model_output_missing_field")

    facts = parsed.get("visible_facts", ())
    if isinstance(facts, str) or not isinstance(facts, (list, tuple)):
        raise PhotoDirectorError("model_output_facts_not_list")
    for value in (parsed["recipe"], parsed["expression"], *facts):
        if type(value) is not str:
            raise PhotoDirectorError("model_output_value_not_string")

    return normalise_draft(
        recipe=parsed["recipe"],
        expression=parsed["expression"],
        visible_facts=tuple(facts),
        context=context,
    )
