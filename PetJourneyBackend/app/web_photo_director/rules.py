"""确定性规则导演。永远可用，什么都不调用。

这不是降级占位：只要文本预算、家庭许可或供应商任一缺失，默认就走这里，
所以它必须拍得出一张主人仍然认得出来的照片。它和模型从**同一份封闭配方表**里挑，
两者的差别是取舍口味，不是世界事实。
"""
from __future__ import annotations

from .catalog import WEATHER_TOKENS
from .contracts import PhotoContext, PhotoDirectorError, SceneDraft
from .draft import (MAX_VISIBLE_FACTS, eligible_recipes, normalise_draft, recipe_of,
                    verified_tokens)
from .privacy import dna_codes
from .recipes import NON_VISIBLE_FACTS, RECIPES, SCENES

# 有序：先命中的先用，所以同一份 DNA 每次得到同一个表情。
EXPRESSION_RULES = (
    ("habits:head_tilt", "head_tilt"),
    ("personality:curious", "curious"),
    ("personality:playful", "curious"),
    ("personality:calm", "relaxed"),
    ("personality:reserved", "relaxed"),
)
# 这些配方的表情是剧情本身的一部分，DNA 不覆盖它
EXPRESSION_LOCKED_RECIPES = frozenset({
    "cockpit_helmet_actioncam", "pirate_deck_selfie", "landmark_front_selfie",
    "landmark_duo_selfie", "courtyard_harvest_selfie",
})


def choose_recipe(context: PhotoContext) -> str:
    """在拍得出来的配方里挑一个最像这只宠物的。

    排序依据：DNA 契合度 → 用上了多少条已核验的事实 → 名字。
    名字兜底是为了让同一只宠物在同一个状态下重试时得到**同一张**照片，
    而不是每次换一张。
    """
    candidates = eligible_recipes(context)
    if not candidates:
        raise PhotoDirectorError("no_recipe_for_verified_facts")
    codes = set(dna_codes(context.dna))

    def score(name: str) -> tuple[int, int, str]:
        recipe = RECIPES[name]
        affinity = len(recipe.affinity & codes)
        # 用上更多已核验事实的配方更贴近这次事件：咖啡真的点了，
        # 那"在喝那杯咖啡"就比"坐在旁边"更接近事实。
        specificity = len(recipe.requires)
        return (affinity, specificity, name)

    return max(candidates, key=score)


def choose_expression(context: PhotoContext, recipe_name: str) -> str:
    recipe = recipe_of(recipe_name)
    if recipe_name in EXPRESSION_LOCKED_RECIPES:
        return recipe.expression
    codes = set(dna_codes(context.dna))
    for code, expression in EXPRESSION_RULES:
        if code in codes:
            return expression
    return recipe.expression


def choose_visible_facts(context: PhotoContext, recipe_name: str) -> tuple[str, ...]:
    """这个场景里所有合法可见、且确实已核验的东西，多一样都不加。"""
    recipe = recipe_of(recipe_name)
    spec = SCENES[context.scene.scene]
    available = verified_tokens(context)

    # 顺序就是重要性：必需的先占位，可选的和天气排在后面，超出上限时只砍尾巴，
    # 不会把配方必需的事实砍掉。
    ordered: list[str] = [spec.mandatory]
    for token in sorted(recipe.requires - {spec.mandatory} - NON_VISIBLE_FACTS):
        ordered.append(token)
    weather = sorted(token for token in available if token in WEATHER_TOKENS)
    if weather:
        ordered.append(weather[0])
    for token in sorted(spec.objects):
        if token in available and token not in NON_VISIBLE_FACTS and token not in ordered:
            ordered.append(token)
    return tuple(ordered[:MAX_VISIBLE_FACTS])


def rule_draft(context: PhotoContext) -> SceneDraft:
    recipe = choose_recipe(context)
    return normalise_draft(
        recipe=recipe,
        expression=choose_expression(context, recipe),
        visible_facts=choose_visible_facts(context, recipe),
        context=context,
    )
