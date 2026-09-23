"""确定性提示词编译。无 I/O、无模型调用、无随机。

草稿决定**怎么取景**；这里决定**什么是真的**。城市、地点、宠物、已拥有的东西、
天气与时间全部来自已校验的上下文，由这段代码写死——不是由模型回复写的。
所以模型可以换一种拍法，但换不掉宠物所在的城市，也发不出一枚它还没拿到的勋章。

编译顺序按公开的 Seedream 4/4.5 提示词指南（靠前的内容权重更高）：
主体+动作 → 镜头/构图 → 环境 → 光线 → 身份锁 → 解剖 → 事实。
负面词单独一个字段，不写成正向里的"不要 X"。
"""
from __future__ import annotations

from .catalog import (
    ANATOMY_RULE,
    APPEARANCE,
    BACKGROUND_RULE,
    CAMERA_DEVICE,
    CAMERAS,
    CAMERA_CONFLICTING_HABITS,
    CAMERAS_WITHOUT_FACE,
    COMPOSITION_IMPLIES,
    COMPOSITIONS,
    CONTACT_RULE,
    DAYPART_LIGHT,
    EXPRESSION_COVERS,
    EXPRESSIONS,
    HABIT_TEXT,
    IDENTITY_RULE,
    IDENTITY_RULE_NO_FACE,
    IMPERFECTION,
    LENS,
    NEGATIVE,
    NIGHT_DAYPARTS,
    PERSONALITY_POSE,
    PREFERENCE_FRAMING,
    PROMPT_VERSION,
    SINGLE_EXPRESSION_RULE,
    SPECIES_CN,
    STORY_MODE_TEXT,
    UNSEEN_MARKS_RULE,
    WEATHER_INDOOR,
    WEATHER_INDOOR_NIGHT,
    WEATHER_LIGHT,
    WEATHER_NIGHT,
    WEATHER_TOKENS,
    daypart_for,
)
from .contracts import (
    DirectedPhoto,
    PhotoContext,
    PhotoDirectorError,
    ReferenceSlot,
    SceneDraft,
    TextCallRecord,
)
from .recipes import FACT_TEXT, NON_VISIBLE_FACTS, RECIPES, SCENES
from .validation import context_key

# 网页生图用 Seedream 4.5，每张图至少约 369 万像素；现网实际就是用 2048x2048
# （`web_journey/illustrations.py` 的 selfie 路径）。1024x1024 低于门槛，会被供应商拒。
DEFAULT_SIZE = "2048x2048"
# 超过三条，DNA 子句就不再塑造画面，而是开始挤占身份锁——那一条必须活下来。
MAX_DNA_CLAUSES = 3
# 身份照必须排第一：Seedream 对靠前的参考权重更高，而且绝不能让模型从环境图上读脸。
REFERENCE_ORDER = ("pet_identity", "companion_identity", "place_environment")


def local_hour(context: PhotoContext) -> int:
    """宠物此刻所在地的墙上小时。

    `captured_at` 必须带时区，且调用方必须按宠物当前城市的偏移构造它
    （AGENTS.md：墙上时间跟随 TA 所在城市，不是宿主机）。naive 时间在 validate_scene 已被拒。
    """
    captured_at = context.scene.captured_at
    if captured_at.utcoffset() is None:
        raise PhotoDirectorError("capture_time_requires_timezone")
    return captured_at.hour


def _daypart(context: PhotoContext) -> str:
    return daypart_for(local_hour(context))


def weather_of(draft: SceneDraft) -> str | None:
    for token in draft.visible_facts:
        if token in WEATHER_TOKENS:
            return token
    return None


def weather_clause_for(context: PhotoContext, draft: SceneDraft) -> str | None:
    """已核验的天气怎么进画面，取决于空间与昼夜。

    室内只能隔着窗看见天气，室内本身保持干燥；密闭座舱一次都不渲染
    （地面观测到的天气不等于舱外天气）；夜里没有太阳，所以"晴天"要换一种说法。
    把这些混为一谈，就会出现"咖啡馆里下雨"和"半夜阳光直射"。
    """
    weather = weather_of(draft)
    if weather is None:
        return None
    space = SCENES[context.scene.scene].space
    if space == "sealed":
        return None
    night = _daypart(context) in NIGHT_DAYPARTS
    if space == "indoor":
        return (WEATHER_INDOOR_NIGHT if night else WEATHER_INDOOR)[weather]
    return (WEATHER_NIGHT if night else WEATHER_LIGHT)[weather]


def _appearance_clause(tags) -> str:
    named = [APPEARANCE[tag] for tag in tags if tag in APPEARANCE]
    return "参考图里已确认的特征：" + "、".join(named) + "。" if named else ""


def _dna_clauses(context: PhotoContext, draft: SceneDraft) -> list[str]:
    """DNA 只改姿态、习惯与取景。

    这里够不到城市、地点、已拥有的东西和身份——多宠隔离与 DNA 的用例盯的就是这条。
    """
    dna = context.dna
    covered = EXPRESSION_COVERS.get(draft.expression, frozenset())
    # 镜头把视线定在哪，就不再发与它相反的习惯句（和上面那条抑制同一个机制）
    conflicting = CAMERA_CONFLICTING_HABITS.get(draft.camera, frozenset())
    clauses: list[str] = []
    for trait in dna.personality:
        if trait in PERSONALITY_POSE:
            clauses.append(PERSONALITY_POSE[trait])
    for habit in dna.habits:
        # 表情已经渲染过的习惯就别再说一遍；"微微歪头"说两次不会让画面更对。
        if habit in HABIT_TEXT and habit not in covered and habit not in conflicting:
            clauses.append(HABIT_TEXT[habit])
    for preference in dna.preferences:
        if preference in PREFERENCE_FRAMING:
            clauses.append(PREFERENCE_FRAMING[preference])
    # 兴趣有意不渲染："喜欢咖啡香"是它去咖啡馆的理由，不是镜头能拍到的东西。
    return clauses[:MAX_DNA_CLAUSES]


def _fact_clauses(context: PhotoContext, draft: SceneDraft) -> list[str]:
    """只说上文还没说过的事实。

    场景那句已经把它放在咖啡馆了，动作那句已经说了它在喝自己点的咖啡；
    再列一遍不会让画面更真，只会变长，而长度会稀释遵循度。
    """
    recipe = RECIPES[draft.recipe]
    mandatory = SCENES[context.scene.scene].mandatory
    implied = ({mandatory} | set(recipe.requires) | set(NON_VISIBLE_FACTS)
               | set(COMPOSITION_IMPLIES.get(draft.composition, frozenset())))
    out: list[str] = []
    for token in draft.visible_facts:
        if token in WEATHER_TOKENS or token in implied:
            continue  # 天气渲染成光线；已被上文表达过的事实不重复
        text = FACT_TEXT.get(token)
        if text:
            out.append(text)
    return out


def _companion_clause(context: PhotoContext) -> str:
    if not context.companions:
        return ""
    companion = context.companions[0]
    animal = SPECIES_CN.get(companion.species, "小动物")
    tags = _appearance_clause(companion.appearance_tags)
    return (
        f"画面里还有第二只动物：一只{animal}，它有自己单独的参考图，"
        f"必须按那张图画，不能和主角混成同一只或同一种花纹。{tags}"
    )


def build_prompt(context: PhotoContext, draft: SceneDraft) -> str:
    """编译一条指令，重要的放前面。

    刻意压短：公开的 Seedream 指南给出的甜点在 30–100 词，
    每多一句重述都会稀释真正要紧的那几条（它是谁、它在哪、什么光）。
    """
    scene = context.scene
    spec = SCENES[scene.scene]
    recipe = RECIPES[draft.recipe]
    animal = SPECIES_CN.get(context.identity.species, "小动物")

    # 1) 主体 + 动作 + 表情
    parts = [
        f"写实摄影：一只真实的{animal}，{recipe.action}，"
        f"{EXPRESSIONS[draft.expression]}（{SINGLE_EXPRESSION_RULE}）。"
    ]

    # 2) 镜头与构图（互斥：这里决定谁在拍、设备在不在画面里）
    parts.append(
        f"{CAMERAS[draft.camera]}；{CAMERA_DEVICE[draft.camera]}；"
        f"{COMPOSITIONS[draft.composition]}。"
    )

    # 3) 地点与叙事：事实，由上下文写死，模型改不了
    place = f"地点：{scene.city} · {scene.place_label}，{spec.setting}；{BACKGROUND_RULE}。"
    story = STORY_MODE_TEXT[scene.narrative]
    parts.append(place + (story + "。" if story else ""))

    # 4) 光线：当地时段 + 已核验天气（按室内/室外/密闭与昼夜分层）
    light = [DAYPART_LIGHT[_daypart(context)]]
    weather_clause = weather_clause_for(context, draft)
    if weather_clause:
        light.append(weather_clause)
    parts.append("；".join(light) + f"。{LENS[draft.camera]}；{IMPERFECTION}。{CONTACT_RULE}。")

    # 5) 身份锁 + 解剖约束（特写镜头下脸可能不入镜，不能硬说"脸型一致"）
    rule = IDENTITY_RULE_NO_FACE if draft.camera in CAMERAS_WITHOUT_FACE else IDENTITY_RULE
    parts.append(
        rule.format(animal=animal) + "。"
        + _appearance_clause(context.identity.appearance_tags)
        + UNSEEN_MARKS_RULE + "。" + ANATOMY_RULE + "。"
    )

    companion = _companion_clause(context)
    if companion:
        parts.append(companion)

    # 6) DNA：只影响姿态、习惯与取景
    dna_clauses = _dna_clauses(context, draft)
    if dna_clauses:
        parts.append("；".join(dna_clauses) + "。")

    # 7) 还没被上文说过的已核验事实
    fact_clauses = _fact_clauses(context, draft)
    if fact_clauses:
        parts.append("；".join(fact_clauses) + "。")

    return "".join(parts)


def build_references(context: PhotoContext) -> tuple[ReferenceSlot, ...]:
    """把已授权的参考排好序；身份图永远第一。"""
    by_role: dict[str, list] = {role: [] for role in REFERENCE_ORDER}
    for reference in context.references:
        if reference.role not in by_role:
            raise PhotoDirectorError("reference_role_not_supported")
        by_role[reference.role].append(reference)
    slots: list[ReferenceSlot] = []
    for role in REFERENCE_ORDER:
        for reference in by_role[role]:
            slots.append(
                ReferenceSlot(
                    position=len(slots),
                    role=role,
                    reference_id=reference.reference_id,
                    sha256=reference.sha256,
                )
            )
    if not slots or slots[0].role != "pet_identity":
        raise PhotoDirectorError("identity_reference_must_be_first")
    return tuple(slots)


def prompt_checks(prompt: str, context: PhotoContext, draft: SceneDraft) -> tuple[str, ...]:
    """对编译出的文本做结构检查。这**不是**对图片的判断。

    它们只断言"我们想说的话确实写进去了"，完全不说明生成的照片像不像这只宠物——
    那件事需要人看着像素来判断。
    """
    space = SCENES[context.scene.scene].space
    checks: list[str] = []
    if context.scene.city in prompt and context.scene.place_label in prompt:
        checks.append("place_anchored")
    if "同一只" in prompt or "画面里出现的部分必须" in prompt:
        checks.append("identity_locked")
    if "仍认得出是哪里" in prompt:
        checks.append("background_legible")
    if "不要画成人手" in prompt:
        checks.append("animal_anatomy")
    if DAYPART_LIGHT[_daypart(context)] in prompt:
        checks.append("time_of_day_applied")
    if weather_clause_for(context, draft) is not None:
        checks.append("verified_weather_applied")
    if space in {"indoor", "sealed"}:
        checks.append("indoor_weather_layered")
    if CAMERA_DEVICE[draft.camera] in prompt:
        checks.append("camera_mode_exclusive")
    if context.companions:
        checks.append("companion_identity_separate")
    return tuple(checks)


def compile_photo(
    context: PhotoContext,
    draft: SceneDraft,
    *,
    directed_by: str,
    fallback_reason: str | None,
    text_call: TextCallRecord,
    size: str = DEFAULT_SIZE,
) -> DirectedPhoto:
    if directed_by not in {"rule", "model"}:
        raise PhotoDirectorError("directed_by_not_allowed")
    prompt = build_prompt(context, draft)
    return DirectedPhoto(
        pet_id=context.pet_id,
        household_id=context.household_id,
        event_id=context.scene.event_id,
        scene=context.scene.scene,
        prompt=prompt,
        negative_prompt=NEGATIVE,
        size=size,
        references=build_references(context),
        draft=draft,
        directed_by=directed_by,
        fallback_reason=fallback_reason,
        versions=context.versions,
        identity_reference_id=context.identity.reference_id,
        identity_sha256=context.identity.sha256,
        prompt_version=PROMPT_VERSION,
        config_version=context.config_version,
        context_key=context_key(context),
        text_call=text_call,
        story_mode=context.scene.narrative,
        scene_origin=context.scene.origin,
        companion_pet_ids=tuple(c.pet_id for c in context.companions),
        prompt_checks=prompt_checks(prompt, context, draft),
        review_points=tuple(RECIPES[draft.recipe].acceptance),
    )
