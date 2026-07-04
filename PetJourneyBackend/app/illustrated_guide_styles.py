from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .schemas import IllustratedGuideStop


@dataclass(frozen=True)
class IllustratedGuideStyle:
    id: str
    name_zh: str
    weight: float
    best_for: tuple[str, ...]
    prompt: str


STYLE_PACK_VERSION = "2026-07-04-all14"

ILLUSTRATED_GUIDE_STYLES: tuple[IllustratedGuideStyle, ...] = (
    IllustratedGuideStyle(
        id="warm_travel_journal",
        name_zh="温柔手账风",
        weight=1.3,
        best_for=("default", "coastal", "slow_travel", "pet_emotional"),
        prompt=(
            "Style: Warm hand-drawn travel journal style. Cream paper texture, soft pastel colors, "
            "low saturation, gentle watercolor washes, thin ink lines, notebook binding, washi tape, "
            "small flower doodles, paw print decorations, cozy handwritten feeling. Cute but premium, "
            "emotional but not childish."
        ),
    ),
    IllustratedGuideStyle(
        id="watercolor_city_map",
        name_zh="水彩城市地图风",
        weight=1.1,
        best_for=("coastal", "city_route", "landmark"),
        prompt=(
            "Style: Soft watercolor illustrated city map. Light cream background, pale blue and green "
            "watercolor blocks, hand-drawn streets, gentle route curves, small skyline sketches, soft "
            "landmark illustrations, subtle map-like composition without real map UI."
        ),
    ),
    IllustratedGuideStyle(
        id="xiaohongshu_guide_poster",
        name_zh="小红书攻略海报风",
        weight=0.9,
        best_for=("share", "food", "city_walk"),
        prompt=(
            "Style: Modern Chinese social media travel guide poster. Clean editorial layout, soft pastel "
            "background, cute stickers, bold readable Chinese title, neatly arranged route cards, small "
            "illustrated icons, warm lifestyle aesthetic, visually organized like a premium Xiaohongshu travel note."
        ),
    ),
    IllustratedGuideStyle(
        id="minimal_infographic",
        name_zh="极简信息图风",
        weight=0.8,
        best_for=("clarity", "complex_route", "in_app_preview"),
        prompt=(
            "Style: Minimal illustrated infographic. Clean warm off-white background, simple geometric layout, "
            "muted colors, clear grid, large readable Chinese text, simple line icons, minimal route line, "
            "lots of breathing space."
        ),
    ),
    IllustratedGuideStyle(
        id="vintage_ticket_collage",
        name_zh="复古票根拼贴风",
        weight=0.9,
        best_for=("travel_memory", "ticket", "chapter_summary"),
        prompt=(
            "Style: Vintage travel ticket collage. Paper tickets, torn edges, stamps, soft postal marks, "
            "old receipt textures, muted beige and faded colors, hand-written labels, small illustrated "
            "travel stickers, scrapbook composition."
        ),
    ),
    IllustratedGuideStyle(
        id="storybook_pet_journey",
        name_zh="绘本故事风",
        weight=1.0,
        best_for=("pet_story", "emotional", "family"),
        prompt=(
            "Style: Gentle storybook illustration. Soft rounded shapes, warm pastel colors, cute pet character, "
            "cozy city scenes, light narrative feeling, friendly hand-drawn texture, simple readable Chinese text. "
            "Premium and gentle, not overly childish."
        ),
    ),
    IllustratedGuideStyle(
        id="japanese_zakka_magazine",
        name_zh="日系Zakka杂志风",
        weight=0.9,
        best_for=("cafe", "old_street", "slow_walk", "shops"),
        prompt=(
            "Style: Japanese zakka lifestyle magazine layout. Soft neutral paper background, delicate small "
            "illustrations, quiet spacing, muted beige, sage green, pale blue, warm brown, calm lifestyle editorial feeling."
        ),
    ),
    IllustratedGuideStyle(
        id="route_blueprint_sketch",
        name_zh="蓝图路线草图风",
        weight=0.7,
        best_for=("route", "transport", "clear_path"),
        prompt=(
            "Style: Soft route blueprint sketch. Pale blue-gray background, fine route lines, clean numbered markers, "
            "subtle grid texture, simple hand-drawn icons, map-planning feeling, warm and pet-friendly."
        ),
    ),
    IllustratedGuideStyle(
        id="polaroid_memory_album",
        name_zh="拍立得相册拼贴风",
        weight=1.0,
        best_for=("photo", "memory", "moments", "postcard"),
        prompt=(
            "Style: Polaroid travel memory album. Cream paper background, taped photo frames, soft hand-drawn city "
            "sketches inside photo cards, handwritten Chinese captions, paw prints, stickers, flowers, gentle shadows."
        ),
    ),
    IllustratedGuideStyle(
        id="chinese_ink_wash_scroll",
        name_zh="国风淡彩手卷风",
        weight=0.8,
        best_for=("culture", "ancient_city", "park", "lake"),
        prompt=(
            "Style: Modern Chinese ink-wash travel scroll. Light rice-paper texture, soft ink lines, pale mineral colors, "
            "elegant Chinese brush title, subtle paw mark, delicate landscape vignettes, calm poetic spacing. No official seals."
        ),
    ),
    IllustratedGuideStyle(
        id="cinematic_storyboard",
        name_zh="电影分镜风",
        weight=0.8,
        best_for=("story", "full_day", "dramatic_light"),
        prompt=(
            "Style: Soft cinematic storyboard. Use 4 to 5 illustrated panels like gentle film frames, each panel showing "
            "one stop. Warm cinematic lighting, soft shadows, handwritten Chinese captions, pet character appearing in some frames."
        ),
    ),
    IllustratedGuideStyle(
        id="postcard_stamp_route",
        name_zh="邮戳明信片风",
        weight=0.9,
        best_for=("postcard", "city_chapter", "share"),
        prompt=(
            "Style: Postcard and stamp themed illustrated guide. Postcard frames, soft postal stamp marks, city postmark "
            "decorations, handwritten route labels, warm cream paper, subtle red and blue accents, tiny paw-print stamps. "
            "No real postal logos."
        ),
    ),
    IllustratedGuideStyle(
        id="soft_clay_scrapbook",
        name_zh="黏土立体手账风",
        weight=0.7,
        best_for=("cute", "collectible", "young_user"),
        prompt=(
            "Style: Soft clay-like 3D scrapbook illustration. Rounded clay objects, soft shadows, pastel colors, tactile "
            "paper background, cute pet mascot, small 3D travel icons, clean Chinese text. Playful but premium."
        ),
    ),
    IllustratedGuideStyle(
        id="night_city_glow",
        name_zh="夜间城市灯光风",
        weight=0.6,
        best_for=("night", "evening", "city_lights"),
        prompt=(
            "Style: Warm night city glow illustration. Deep muted navy and warm amber tones, soft glowing lights, gentle stars, "
            "cozy night-walk feeling, readable Chinese text, small pet mascot or silhouette. Warm, not too dark."
        ),
    ),
)

ACTIVE_STYLE_IDS = frozenset(style.id for style in ILLUSTRATED_GUIDE_STYLES)

# Kept for compatibility with older tests/imports. The style pack is no longer MVP-limited.
MVP_STYLE_IDS = ACTIVE_STYLE_IDS


def get_illustrated_guide_style(style_id: str | None) -> IllustratedGuideStyle | None:
    if not style_id:
        return None
    return next((style for style in ILLUSTRATED_GUIDE_STYLES if style.id == style_id), None)


def select_illustrated_guide_style(
    *,
    seed: str,
    city: str,
    theme: str,
    stops: list[IllustratedGuideStop],
    preferred_style_id: str | None = None,
    force_new_style: bool = False,
) -> IllustratedGuideStyle:
    preferred = get_illustrated_guide_style(preferred_style_id)
    if preferred:
        return preferred

    active_styles = [style for style in ILLUSTRATED_GUIDE_STYLES if style.id in ACTIVE_STYLE_IDS]
    tags = _route_tags(city=city, theme=theme, stops=stops)
    stable_seed = f"{seed}:style_pack:{STYLE_PACK_VERSION}:daily"
    stable_style = _weighted_pick(active_styles, seed=stable_seed, tags=tags)
    if not force_new_style:
        return stable_style

    alternatives = [style for style in active_styles if style.id != stable_style.id] or active_styles
    return _weighted_pick(alternatives, seed=f"{seed}:style_pack:{STYLE_PACK_VERSION}:next", tags=tags)


def _route_tags(*, city: str, theme: str, stops: list[IllustratedGuideStop]) -> set[str]:
    joined = " ".join([city, theme, *[stop.name for stop in stops], *[stop.category for stop in stops], *[stop.label for stop in stops]])
    tags = {"default", "slow_travel", "pet_emotional", "full_day"}
    if any(token in joined for token in ("厦门", "海", "沙滩", "环岛", "白鹭洲", "鼓浪屿", "青岛", "三亚")):
        tags.update({"coastal", "city_route", "landmark"})
    if any(token in joined for token in ("八市", "市场", "小吃", "沙茶", "餐", "咖啡", "茶")):
        tags.update({"food", "cafe", "old_street", "city_walk"})
    if any(token in joined for token in ("公园", "山", "湖", "步道", "树", "草地")):
        tags.update({"park", "lake"})
    if any(token in joined for token in ("明信片", "照片", "寄", "邮")):
        tags.update({"postcard", "photo", "memory"})
    if any((stop.time or "") >= "18:00" for stop in stops if stop.time):
        tags.update({"evening", "night"})
    if len(stops) >= 5:
        tags.update({"route", "clear_path"})
    return tags


def _weighted_pick(
    styles: list[IllustratedGuideStyle],
    *,
    seed: str,
    tags: set[str] | None = None,
) -> IllustratedGuideStyle:
    total = sum(_effective_weight(style, tags=tags) for style in styles)
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    target = (int(digest[:12], 16) / float(0xFFFFFFFFFFFF)) * total
    cursor = 0.0
    for style in styles:
        cursor += _effective_weight(style, tags=tags)
        if target <= cursor:
            return style
    return styles[-1]


def _effective_weight(style: IllustratedGuideStyle, *, tags: set[str] | None = None) -> float:
    weight = max(style.weight, 0.01)
    if not tags:
        return weight
    matched_tags = set(style.best_for).intersection(tags)
    if "default" in style.best_for:
        weight *= 1.04
    if matched_tags:
        weight *= 1.0 + min(len(matched_tags), 4) * 0.12
    return weight
