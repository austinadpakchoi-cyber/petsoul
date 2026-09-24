"""内容类型的词表、字段白名单与结构校验（从 content.py 拆出，那边只剩仓储与发布流程）。

拆分原因：`content.py` 同时管"有哪些类型、每种能发哪些字段、怎么校验"和"草稿/版本/发布怎么落库"，
定义数超过了架构门禁的上限（30）。这里只放**与存储无关的纯判断**，不 import 仓储。

字段白名单是这套设计的核心：能不能发布某个字段，取决于它会不会被进行中的事实实时读到。
详见 `app/web_admin/content.py` 的模块说明。
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass
from typing import Any

from .labels import ADOPTION_AVAILABILITY, ANNOUNCEMENT_AUDIENCE, ANNOUNCEMENT_SEVERITY, CONTENT_FIELD

CONTENT_TYPES =("announcement", "adventure", "crop", "job", "resident", "destination")
# 覆盖层类型：这几种是给**内置目录**发新版本，slug 必须是已有条目（`app/content_overlay.py`）。
OVERLAY_TYPES = ("adventure", "crop", "job", "destination")
ANNOUNCEMENT_SEVERITIES = ("info", "notice", "maintenance")
ANNOUNCEMENT_AUDIENCES = ("all", "signed_in")
ADVENTURE_PLACEHOLDERS = {"pet", "keepsake"}
# 数值型字段的合理区间：挡住手滑打多一个零。上限不是"生产授权额度"，是防呆。
NUMERIC_BOUNDS = {
    ("crop", "unit_value"): (1, 50),
    ("crop", "grow_seconds"): (30, 86400),
    ("job", "pay"): (1, 200),
    ("job", "hours"): (1, 12),
    ("destination", "fee"): (0, 300),
}
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{1,48}$")
# 素材编号只判**形状**；"这个素材在不在、是不是公开的、下架了没有"要查库，
# 放在发布那一刻做（见 content.py 的 _publish_in）——草稿存着的这段时间里素材可能被下架。
_ASSET_ID_RE = re.compile(r"^AS-[0-9A-F]{16}$")
# 公告链接只收站内路径：一个 / 开头；`//外站` 是协议相对地址、`/\外站` 有的浏览器把反斜杠当斜杠，都会跳到别的网站；
# 空白与控制字符也不收（6c2b 接公告时报的，玩家端同样挡了）。
_SITE_LINK_RE = re.compile(r"/(?![/\\])[^\s\\\x00-\x1f\x7f]*")
# 富文本一律不接：公告正文是纯文本，界面按纯文本渲染。挡在入口比事后消毒可靠。
_MARKUP_RE = re.compile(r"[<>]|&[a-zA-Z#][a-zA-Z0-9]{1,8};")
# 覆盖层缓存的存活时间：`CROPS[key]`、`JOBS.values()` 会被世界推进反复调用，不能每次打库。
# 多进程下最多陈旧这么久；发布/撤下/回退时本进程立刻失效。
OVERLAY_CACHE_SECONDS = 2.0


def builtin_keys(content_type: str) -> frozenset[str]:
    """某个覆盖层类型的内置条目键。运营只能给已有条目发新版本，不能凭空造新条目。"""
    if content_type == "adventure":
        from ..web_journey.adventures import BUILT_IN_ADVENTURES

        return BUILT_IN_ADVENTURES
    if content_type == "crop":
        from ..web_farm.service import BUILT_IN_CROPS

        return BUILT_IN_CROPS
    if content_type == "job":
        from ..web_journey.local import BUILT_IN_JOBS

        return BUILT_IN_JOBS
    if content_type == "destination":
        from ..web_journey.catalog import BUILT_IN_DESTINATIONS

        return BUILT_IN_DESTINATIONS
    return frozenset()


def builtin_body(content_type: str, slug: str) -> dict[str, Any]:
    """内置条目的可发布字段当前值。新建草稿时拿它当起点，改动差异也对着它算。"""
    if content_type == "adventure":
        from ..web_journey.adventures import ADVENTURES, PUBLISHABLE_FIELDS

        base = ADVENTURES.base_of(slug) if hasattr(ADVENTURES, "base_of") else ADVENTURES[slug]
        return {field: getattr(base, field) for field in PUBLISHABLE_FIELDS}
    if content_type == "crop":
        from ..web_farm.service import CROPS, CROP_PUBLISHABLE_FIELDS

        base = CROPS.base_of(slug) if hasattr(CROPS, "base_of") else CROPS[slug]
        return {field: getattr(base, field) for field in CROP_PUBLISHABLE_FIELDS}
    if content_type == "job":
        from ..web_journey.local import JOBS, JOB_PUBLISHABLE_FIELDS

        base = JOBS.base_of(slug) if hasattr(JOBS, "base_of") else JOBS[slug]
        return {field: getattr(base, field) for field in JOB_PUBLISHABLE_FIELDS}
    if content_type == "destination":
        from ..web_journey.catalog import DESTINATIONS, DESTINATION_PUBLISHABLE_FIELDS

        base = DESTINATIONS.base_of(slug) if hasattr(DESTINATIONS, "base_of") else DESTINATIONS[slug]
        return {field: getattr(base, field) for field in DESTINATION_PUBLISHABLE_FIELDS}
    return {}


def builtin_name(content_type: str, slug: str) -> str:
    """内置条目的中文名（选条目的下拉框、报错里用；内部键只在「显示技术代码」时出现）。认不出来就照原样给键。"""
    try:
        body = builtin_body(content_type, slug)
    except (KeyError, AttributeError):
        return slug
    return str(body.get("title") or body.get("label") or slug)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    field: str
    message: str



def _placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def validate(content_type: str, body: Any) -> list[ValidationIssue]:
    """结构校验。返回空列表＝通过。这里只判**可机器判定**的事实，判断不了的（版权、真实商家）由人负责并在原因里写明。"""
    issues: list[ValidationIssue] = []
    if content_type not in CONTENT_TYPES:
        return [ValidationIssue("content_type", f"不支持的内容类型：{content_type}")]
    if not isinstance(body, dict):
        return [ValidationIssue("body", "正文必须是一个对象。")]

    def text(field: str, *, required: bool = True, max_length: int = 200, allow_markup: bool = False) -> str:
        value = body.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            if required:
                issues.append(ValidationIssue(field, "这一项是必填的。"))
            return ""
        if not isinstance(value, str):
            issues.append(ValidationIssue(field, "必须是文本。"))
            return ""
        value = value.strip()
        if len(value) > max_length:
            issues.append(ValidationIssue(field, f"最多 {max_length} 个字，现在是 {len(value)} 个。"))
        if not allow_markup and _MARKUP_RE.search(value):
            issues.append(ValidationIssue(field, "不接受 HTML 标签或转义实体；公告与故事是纯文本。"))
        return value

    def number(field: str, bound_key: tuple[str, str]) -> None:
        low, high = NUMERIC_BOUNDS[bound_key]
        value = body.get(field)
        if value is None:
            issues.append(ValidationIssue(field, "这一项是必填的。"))
            return
        if isinstance(value, bool) or not isinstance(value, int):
            issues.append(ValidationIssue(field, "必须是整数。"))
            return
        if not low <= value <= high:
            issues.append(ValidationIssue(field, f"要在 {low}–{high} 之间，现在是 {value}。"))

    def blocked(allowed: tuple[str, ...], reasons: dict[str, str]) -> None:
        """正文里出现了**不可发布**的字段就明确拒绝，并说清为什么——不是静默忽略。"""
        for field in sorted(set(body) - set(allowed)):
            issues.append(ValidationIssue(field, reasons.get(field, "这一项不在可发布字段里，运营改不了它。")))

    if content_type == "announcement":
        text("title", max_length=60)
        text("body", max_length=2000)
        severity = body.get("severity")
        if severity not in ANNOUNCEMENT_SEVERITIES:
            issues.append(ValidationIssue("severity", f"只能是 {' / '.join(ANNOUNCEMENT_SEVERITY[s] for s in ANNOUNCEMENT_SEVERITIES)}。"))
        audience = body.get("audience")
        if audience not in ANNOUNCEMENT_AUDIENCES:
            issues.append(ValidationIssue("audience", f"只能是 {' / '.join(ANNOUNCEMENT_AUDIENCE[a] for a in ANNOUNCEMENT_AUDIENCES)}。"))
        link = body.get("link")
        if link is not None:
            if not isinstance(link, str) or not _SITE_LINK_RE.fullmatch(link):
                # 只允许站内相对路径：不让运营在公告里挂任意外链，服务器也不会去抓取它。
                issues.append(ValidationIssue("link", "只接受站内路径：以一个 / 开头，不能以 // 开头，不能有反斜杠、空格或控制字符。"))
        asset_id = body.get("image_asset_id")
        if asset_id is not None and not (isinstance(asset_id, str) and _ASSET_ID_RE.match(asset_id)):
            # 只接受素材库里的编号，不接受任意 URL：公告里挂不了外链图，服务器也不会去抓。
            issues.append(ValidationIssue("image_asset_id", "配图只能从素材库里选（素材编号形如 AS-XXXXXXXXXXXXXXXX）。"))
    elif content_type == "adventure":
        title = text("title", max_length=40)
        badge = text("badge", max_length=40)
        story = text("story", max_length=600)
        if story:
            unknown = _placeholders(story) - ADVENTURE_PLACEHOLDERS
            if unknown:
                issues.append(ValidationIssue(
                    "story", f"故事里只能用 {{pet}} 与 {{keepsake}} 两个占位符；发现了 {'、'.join('{' + name + '}' for name in sorted(unknown))}。"
                             "世界引擎会对这段文字做 format，未知占位符会在真实运行时报错。"))
            if "{pet}" not in story:
                issues.append(ValidationIssue("story", "故事里必须出现 {pet}，否则读起来不是在说这只宠物。"))
        if badge and title and badge == title:
            issues.append(ValidationIssue("badge", "勋章名与活动标题不要完全相同，回忆柜里会分不清。"))

    elif content_type == "crop":
        from ..web_farm.service import CROP_PUBLISHABLE_FIELDS

        text("label", max_length=20)
        number("unit_value", ("crop", "unit_value"))
        number("grow_seconds", ("crop", "grow_seconds"))
        blocked(CROP_PUBLISHABLE_FIELDS,
                {"yield_units": "产量在收获时是实时读的，改了会改写进行中的那一批；要开放必须先在种植时冻结版本。",
                 "steal_total": "可偷上限在地块摘要里是实时读的，同上。",
                 "requires_seed": "改它会让已经消耗/待退还的种子账目对不上。"})

    elif content_type == "job":
        from ..web_journey.local import JOB_PUBLISHABLE_FIELDS

        text("label", max_length=24)
        number("pay", ("job", "pay"))
        number("hours", ("job", "hours"))
        blocked(JOB_PUBLISHABLE_FIELDS,
                {"keyword": "找活的关键词是「哪里有这个岗位」的世界规则，不是文案。",
                 "habitats": "岗位出现在哪种家附近同样是世界规则。"})

    elif content_type == "destination":
        from ..web_journey.catalog import DESTINATION_PUBLISHABLE_FIELDS

        text("title", max_length=20)
        text("city", max_length=16)
        text("summary", max_length=120)
        number("fee", ("destination", "fee"))
        blocked(DESTINATION_PUBLISHABLE_FIELDS,
                {"outbound": "去程各段是路线与承运人，属于世界事实；运营改它等于伪造一段行程。",
                 "inbound": "回程同上。",
                 "venue": "到访场所的身份与坐标是事实，不是文案。",
                 "wish_keywords": "愿望匹配是规则，不是文案。",
                 "food_area": "寻味区域是事实关联，不是文案。"})

    elif content_type == "resident":
        text("personality", max_length=60)
        text("dream", max_length=60)
        text("source_note", required=False, max_length=80)
        blocked(("personality", "dream", "source_note"),
                {"name": "名字属于居民身份；产品规则要求领养前后身份连续，运营不能改。",
                 "species": "物种同样属于身份。",
                 "pet_id": "宠物编号是身份，永远不可发布。"})
    return issues


# ---- 发布流水与发布结果里的说明文字（纯文字，不碰库）----
def _diff_summary(previous: dict | None, current: dict) -> str:
    """发布流水里的差异摘要：字段写说法（标题、正文……），词表里没有的照原样写代码。"""

    def names(keys) -> str:
        return "、".join(CONTENT_FIELD.get(key, key) for key in sorted(keys))

    if previous is None:
        return "首次发布：" + names(current)
    changed = [key for key in set(previous) | set(current) if previous.get(key) != current.get(key)]
    return ("改动字段：" + names(changed)) if changed else "正文与上一版相同"


def resident_apply_note(applied: str) -> str:
    """居民文案发布之后，待领养名单上真实发生了什么——给操作的人一句人话（原始结果照样记在审计里）。

    「发布成功」不等于「玩家看到了新文案」：居民在草稿之后被领养了，发布会如实跳过，这件事必须当场说出来。
    """
    if applied == "applied":
        return "已经写进待领养名单，玩家在领养页看到的是这一版。"
    if applied == "noop":
        return "这一版没有要改的文案，待领养名单没有变化。"
    if applied == "missing":
        return "待领养名单里找不到这位居民，什么也没写。"
    if applied.startswith("skipped:"):
        state = applied.split(":", 1)[1]
        return f"版本已发布，但这位居民现在是「{ADOPTION_AVAILABILITY.get(state, state)}」，名单上的文案没有改（身份与经历必须连续）。"
    return applied
