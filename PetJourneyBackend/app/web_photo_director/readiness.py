"""这次事件够不够拍一张照片——不够就**暂不生成**，不靠默认值补齐。

规则导演的"默认"只针对**可选偏好**（用哪种表情、取哪个角度、要不要把已核验的
天气画进去）。它从来不给**必需的东西**兜底：

  - 必需事实（场景的 mandatory、配方 requires 的物件、镜头的现场前提）
  - 身份参考（没有参考照就没有"像不像它"可言）
  - 授权（家庭没开生成照片、没给 DNA 用途、撤回了参考使用）

缺这三类里的任何一样，正确做法是**这次先不出图**，而不是编一个看起来合理的画面。
调用方用 `readiness()` 得到结构化结论，可以干净地跳过这一轮；
真的走 `direct()` 也会在围栏上抛出同样口径的原因码，两条路不会打架。
"""
from __future__ import annotations

from dataclasses import dataclass

from .contracts import PhotoAccess, PhotoContext, PhotoDirectorError
from .draft import eligible_recipes, verified_tokens
from .recipes import NON_VISIBLE_FACTS, RECIPES, SCENES
from .validation import validate_context

# 这些是"有了更像它，没有也能拍"的：规则导演可以给默认值。
OPTIONAL_KINDS = ("expression", "camera_angle", "weather", "dna_flavour", "place_reference")


@dataclass(frozen=True, slots=True)
class Readiness:
    ready: bool
    reason: str | None = None
    missing_required: tuple[str, ...] = ()
    optional_absent: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.ready


def _missing_authorisation(access: PhotoAccess) -> tuple[str, ...]:
    missing = []
    for flag in ("can_access", "generated_photos", "photo_dna", "reference_use"):
        if not getattr(access, flag, False):
            missing.append(f"authorisation:{flag}")
    return tuple(missing)


def readiness(context: PhotoContext, access: PhotoAccess) -> Readiness:
    """够不够拍。`ready=False` 时调用方应当跳过这一轮，不要退而求其次。"""
    missing: list[str] = []

    missing.extend(_missing_authorisation(access))

    identities = [ref for ref in context.references if ref.role == "pet_identity"]
    if len(identities) != 1:
        missing.append("identity_reference")
    elif not (identities[0].ready and identities[0].authorized):
        missing.append("identity_reference:unavailable")

    spec = SCENES.get(context.scene.scene)
    if spec is None:
        return Readiness(False, "scene_not_supported", tuple(missing))
    if spec.fact_source != "target" and context.scene.origin != "evaluation_fixture":
        missing.append("fact_source")

    available = verified_tokens(context)
    if spec.mandatory not in available:
        # 没有"它到了咖啡馆"这条，就不存在一张咖啡馆的照片可拍。
        missing.append(f"required_fact:{spec.mandatory}")

    if missing:
        return Readiness(False, "hold_missing_required", tuple(sorted(missing)))

    # 预检必须和最终围栏用**同一套校验**，否则会出现"预检说能拍、最终又拒"的误报：
    # 授权版本过期、事件被更正、参考图属于另一只宠物、DNA 版本对不上、同伴没同意，
    # 这些都只有 validate_context 知道。这里不重写一遍规则，直接复用它。
    try:
        validate_context(context, access)
    except PhotoDirectorError as exc:
        return Readiness(False, "hold_validation_failed", (str(exc),))

    if not eligible_recipes(context):
        # 场景成立，但没有任何一种拍法的必需条件齐了（例如要同伴拍却没有同伴在场）。
        needed = sorted({
            token
            for name, recipe in RECIPES.items()
            if recipe.scene == context.scene.scene
            for token in recipe.requires - available
        })
        return Readiness(False, "hold_no_shot_is_possible", tuple(needed))

    return Readiness(True, None, (), _optional_absent(context, available, spec))


def _optional_absent(context, available, spec) -> tuple[str, ...]:
    """有了会更像它、没有也能拍的那些。仅供记录，不影响 ready。"""
    absent = []
    for token in sorted(spec.objects - available - NON_VISIBLE_FACTS):
        absent.append(f"optional_object:{token}")
    if not any(ref.role == "place_environment" for ref in context.references):
        absent.append("optional:place_reference")
    if not context.identity.appearance_tags:
        absent.append("optional:appearance_tags")
    return tuple(absent)


def require_ready(context: PhotoContext, access: PhotoAccess) -> None:
    """想用异常流的调用方用这个；原因码与 `readiness()` 一致。"""
    state = readiness(context, access)
    if not state.ready:
        raise PhotoDirectorError(
            f"{state.reason}:" + ",".join(state.missing_required)
            if state.missing_required else state.reason or "not_ready"
        )
