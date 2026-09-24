"""手账画面简报（TRV-05）：把一份已核验的旅行计划编译成「只画画面、不写文字」的生图简报。纯函数，无 I/O。

规则见 `docs/coordination/travel-wish/TRV-05-art-brief-ada5.md`：
- **准确文字全由应用排版**：地名、时间、票价、来源、引用都不进提示词。提示词里不出现任何站名和数字，
  也不出现会招来字迹的词——"手账"本身就会让模型写满伪文字，所以画面叫"剪贴本"。
- **地标只画已核验事实的画面特征**：未核验、冲突、过期、不允许展示、来源缺失或来源对不上的一律排除并记原因。
  特征文字来自网页检索，是外部资料不是指令：过字符白名单、限长，含指令字眼、数字、站名、动物的都排除。
- **印章不让模型画**：模型画的章位置随机，对不上是哪一站。回忆页的章由界面按真实事件编号叠加（`stamp_slots`），
  所以计划页从结构上画不出到访章。
- **主角**：只有真实参考照（主人原照／已核实档案照）才贴一张写实小照片；没有就整页不出现动物。
  生成的基准照不能冒充真实照片。
- **能力不够就拒**：需要参考图而调用方的适配器发不了，默认拒绝；调用方显式允许时才降为无肖像版并记原因，不静默丢。
- **`visual_digest` 只由画面内容决定**：改站名、时间、提醒不重画；回忆页与计划页画面输入相同，直接复用那张背景。
  事实编号、参考照版本号是**编号不是内容**，不进摘要：换一轮研究、特征一字不差，或者重传同一张照片，都不会再付费重画
  （A 接入时指出，2026-09-24 修订）。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime

from .catalog import APPEARANCE, IDENTITY_RULE, SPECIES_CN, UNSEEN_MARKS_RULE
from .compiler import _appearance_clause
from .contracts import PhotoDirectorError
from .validation import ID, INSTRUCTIONS, SHA

BRIEF_STYLE_VERSION = "journal-p1"
SIZE = "1024x1536"
MAX_LANDMARKS = 3
# 默认版式 t1 的文字区（相对画面的 x0, y0, x1, y1）。r7k 的 TRV-07 定稿后以它为准，这里是建议值。
TEXT_ZONES_T1 = (("title", 0.06, 0.05, 0.94, 0.17), ("stations", 0.56, 0.20, 0.94, 0.78), ("notes", 0.06, 0.82, 0.94, 0.95))
PAPER = {"cream": "米白色的旧纸", "kraft": "牛皮纸", "grid": "浅色方格纸"}
BRUSH = {"pencil": "彩色铅笔", "watercolor": "淡水彩", "ink": "细墨线加淡彩"}
MOOD = {"calm": "画面安静，留白多，小画稀疏", "curious": "小画和贴纸多一些，排布活泼",
        "excited": "色彩明快，贴纸更多", "nostalgic": "色调偏暖，纸面略显旧"}
STICKERS = "四周点缀小星星、叶子、云朵和小花形状的贴纸，几条彩色胶带"
ROUTE = "小画之间用一条随意弯曲的虚线轻轻连起来"
LAYOUT = "版面：上方留一条干净的横向空白带，右侧留一块干净的竖长空白，下方留一条窄窄的空白带；小画、贴纸{photo}集中在左侧和中间"
LIGHT = "柔和均匀的光，纸面平整，没有阴影遮挡"
FEATURE = re.compile(r"[一-鿿，、]{2,24}\Z")
DIGITS = re.compile(r"[0-9０-９¥￥$]")
# 会招来字迹、地图或到访记号的词：提示词里一个都不许有（地名、数字另查）
TEXT_WORDS = ("文字", "字迹", "写着", "写上", "标题", "地名", "名字", "签名", "日期", "时间", "票价", "价格", "门票",
              "地址", "手写", "书写", "笔记", "手账", "便签", "标签", "印章", "盖章", "打卡", "到访", "对勾",
              "地图", "导航", "指南针", "比例尺", "透明", "棋盘", "拿笔", "握笔", "拟人", "卡通")
ANIMAL_WORDS = ("猫", "狗", "兔", "仓鼠", "鸟", "鹦鹉", "动物", "宠物", "爪")
REAL_ORIGINS = frozenset({"owner_original", "real_archive"})
# 主角出不出现：对外契约 `TravelIdentityMode` 与这份清单双向比对（I 的合同用例）。加第三种模式要同时改契约与前端
IDENTITY_PHOTO, IDENTITY_NONE = "photo", "none"
IDENTITY_MODES = frozenset({IDENTITY_PHOTO, IDENTITY_NONE})
VERIFICATION_REASON = {"unverified": "fact_unverified", "conflicting": "fact_conflicting", "stale": "fact_stale"}


@dataclass(frozen=True, slots=True)
class JournalFact:
    fact_id: str
    visual_feature: str  # 允许画出来的画面特征，如「白色的灯塔和翻卷的浪花」；不含地名、数字
    verification: str  # verified / unverified / conflicting / stale
    display_allowed: bool
    source_ids: tuple[str, ...]
    valid_until: datetime | None = None
    names: tuple[str, ...] = ()  # 这条事实自己的专名及各种写法（如「日光岩」）：只给排版用，特征里出现就排除


@dataclass(frozen=True, slots=True)
class JournalStation:
    station_id: str
    role: str  # main（真实主目的地）/ suggested（顺路建议）
    name: str  # 只给排版用，绝不进提示词
    fact_ids: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()  # 简称、旧称、外文名：同样只排版。**上游有义务把各种写法都交齐**，这里不猜


@dataclass(frozen=True, slots=True)
class JournalEvent:
    event_id: str  # 真实发生的旅程事件
    station_id: str


@dataclass(frozen=True, slots=True)
class JournalIdentity:
    species: str
    reference_revision: int
    reference_sha256: str
    origin: str
    appearance_tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class JournalBriefInput:
    phase: str  # plan / memory
    plan_id: str
    plan_revision: int
    template_revision: str
    paper: str
    brush: str
    mood: str
    stations: tuple[JournalStation, ...]
    facts: tuple[JournalFact, ...]
    known_source_ids: frozenset[str]
    now: datetime
    identity: JournalIdentity | None = None
    events: tuple[JournalEvent, ...] = ()
    capabilities: frozenset[str] = frozenset()  # 调用方适配器实际支持的能力，如 {"reference_images"}
    allow_portrait_free: bool = False


@dataclass(frozen=True, slots=True)
class JournalArtBrief:
    phase: str
    plan_id: str
    plan_revision: int
    template_revision: str
    size: str
    prompt: str
    identity_mode: str  # IDENTITY_MODES 之一
    identity_note: str | None
    references: tuple[tuple[str, int, str], ...]  # (role, revision, sha256)
    landmark_fact_ids: tuple[str, ...]
    excluded: tuple[tuple[str, str], ...]  # (fact_id, 原因码)
    stamp_slots: tuple[tuple[str, tuple[str, ...]], ...]  # (station_id, 真实事件编号)；界面叠加，模型不画
    text_zones: tuple[tuple[str, float, float, float, float], ...]
    route: str  # 恒为 decorative：导航一律用真实地图
    capabilities_required: tuple[str, ...]
    visual_digest: str


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise PhotoDirectorError(code)


def _check_input(inp: JournalBriefInput) -> None:
    _require(inp.phase in ("plan", "memory"), "phase_unknown")
    _require(isinstance(inp.plan_id, str) and bool(ID.fullmatch(inp.plan_id)), "invalid_identifier")
    _require(type(inp.plan_revision) is int and inp.plan_revision >= 0, "invalid_versions")
    _require(isinstance(inp.template_revision, str) and bool(ID.fullmatch(inp.template_revision)), "template_revision_missing")
    _require(inp.paper in PAPER and inp.brush in BRUSH, "style_unknown")
    _require(inp.mood in MOOD, "mood_unknown")
    ids = [s.station_id for s in inp.stations]
    _require(bool(ids) and all(isinstance(i, str) and ID.fullmatch(i) for i in ids) and len(set(ids)) == len(ids), "stations_invalid")
    _require(all(s.role in ("main", "suggested") and isinstance(s.name, str) and s.name.strip() for s in inp.stations), "stations_invalid")
    _require(sum(s.role == "main" for s in inp.stations) == 1, "main_station_count")
    facts = [f.fact_id for f in inp.facts]
    _require(all(isinstance(i, str) and ID.fullmatch(i) for i in facts) and len(set(facts)) == len(facts), "facts_invalid")
    if inp.phase == "plan":
        _require(not inp.events, "plan_phase_has_events")  # 计划还没发生，不能有到访
    events = [e.event_id for e in inp.events]
    _require(all(isinstance(i, str) and ID.fullmatch(i) for i in events), "invalid_identifier")
    _require(len(set(events)) == len(events), "event_duplicate")
    _require(all(e.station_id in ids for e in inp.events), "event_station_unknown")


def _identity(inp: JournalBriefInput) -> tuple[str, str | None, tuple[tuple[str, int, str], ...]]:
    ident = inp.identity
    if ident is None:
        return IDENTITY_NONE, "no_reference", ()
    _require(ident.origin in REAL_ORIGINS, "reference_not_real")  # 生成的基准照不能冒充真实照片
    _require(type(ident.reference_revision) is int and ident.reference_revision >= 0, "invalid_versions")
    _require(isinstance(ident.reference_sha256, str) and bool(SHA.fullmatch(ident.reference_sha256)), "invalid_reference")
    _require(all(tag in APPEARANCE for tag in ident.appearance_tags), "appearance_unknown")
    problem = ("species_unsupported" if ident.species not in SPECIES_CN
               else None if "reference_images" in inp.capabilities else "capability_missing:reference_images")
    if problem is None:
        return IDENTITY_PHOTO, None, (("pet_identity", ident.reference_revision, ident.reference_sha256),)
    _require(inp.allow_portrait_free, problem)  # 默认拒；调用方显式允许才降级
    return IDENTITY_NONE, problem, ()


def _name_forms(inp: JournalBriefInput) -> tuple[str, ...]:
    """本计划里所有地名写法（站名、别名、事实专名），两个字以上才比——单字会误伤「远处的山坡」这类描述。"""
    forms = [s.name for s in inp.stations] + [a for s in inp.stations for a in s.aliases] + [n for f in inp.facts for n in f.names]
    return tuple(sorted({f.strip() for f in forms if isinstance(f, str) and len(f.strip()) >= 2}))


def _feature_problem(feature: str, names: tuple[str, ...]) -> str | None:
    if not isinstance(feature, str) or not FEATURE.fullmatch(feature):
        return "feature_rejected"  # 字符白名单与长度
    if INSTRUCTIONS.search(feature) or DIGITS.search(feature) or any(w in feature for w in TEXT_WORDS):
        return "feature_rejected"
    if any(name in feature for name in names) or any(w in feature for w in ANIMAL_WORDS):
        return "feature_rejected"  # 站名只能排版；动物会变成新同伴
    return None


def _select(inp: JournalBriefInput) -> tuple[tuple[JournalFact, ...], tuple[tuple[str, str], ...]]:
    by_id = {f.fact_id: f for f in inp.facts}
    names = _name_forms(inp)
    ordered = sorted(inp.stations, key=lambda s: s.role != "main")  # 主目的地的事实先画
    wanted: list[str] = []
    for station in ordered:
        wanted += [fid for fid in station.fact_ids if fid not in wanted]
    used: list[JournalFact] = []
    excluded: list[tuple[str, str]] = [(fid, "fact_not_in_plan") for fid in by_id if fid not in wanted]
    for fid in wanted:
        fact = by_id.get(fid)
        if fact is None:
            excluded.append((fid, "fact_missing"))
            continue
        reason = (VERIFICATION_REASON.get(fact.verification, "fact_unverified") if fact.verification != "verified"
                  else "fact_display_not_allowed" if not fact.display_allowed
                  else "fact_stale" if fact.valid_until is not None and fact.valid_until <= inp.now
                  else "fact_source_missing" if not fact.source_ids
                  else "fact_source_unknown" if any(s not in inp.known_source_ids for s in fact.source_ids)
                  else _feature_problem(fact.visual_feature, names)
                  or ("feature_duplicate" if any(u.visual_feature == fact.visual_feature for u in used) else None)
                  or ("landmark_limit" if len(used) >= MAX_LANDMARKS else None))
        if reason:
            excluded.append((fid, reason))
        else:
            used.append(fact)
    return tuple(used), tuple(excluded)


def forbidden_in_prompt(prompt: str, names: tuple[str, ...] = ()) -> list[str]:
    """提示词里不该出现的东西：会招来字迹或记号的词、数字与货币符号、任何站名。空列表才算干净。"""
    hits = [w for w in TEXT_WORDS if w in prompt]
    hits += ["digits"] if DIGITS.search(prompt) else []
    return hits + [n for n in names if n and n in prompt]


def _prompt(inp: JournalBriefInput, mode: str, features: tuple[JournalFact, ...]) -> str:
    only = "小画、贴纸、一张小照片和留白" if mode == IDENTITY_PHOTO else "小画、贴纸和留白"
    parts = [f"俯拍一页平铺的旅行剪贴本纸面：{PAPER[inp.paper]}，用{BRUSH[inp.brush]}画成，纸面上只有{only}。"]
    if mode == IDENTITY_PHOTO:
        ident = inp.identity
        animal = SPECIES_CN[ident.species]
        parts.append(f"纸上贴着一张这只{animal}的写实小照片，照片里是一只真实的{animal}，保持真实动物的姿态。"
                     + IDENTITY_RULE.format(animal=animal) + "。"
                     + _appearance_clause(tuple(ident.appearance_tags)) + UNSEEN_MARKS_RULE + "。")
    parts.append(("纸上画着几处小画：" + "；".join(f.visual_feature for f in features) + f"。{ROUTE}。")
                 if features else "纸面以贴纸和留白为主。")
    parts.append(f"{STICKERS}。" + LAYOUT.format(photo="和小照片" if mode == IDENTITY_PHOTO else "") + "。")
    parts.append(f"{MOOD[inp.mood]}。{LIGHT}。")
    return "".join(parts)


def _digest(inp: JournalBriefInput, mode: str, features: tuple[JournalFact, ...]) -> str:
    """只放画面内容：阶段、站名、时间、事件不在里面，所以改文字不重画、回忆页复用计划页背景。

    事实编号和参考照版本号也不在里面——它们是编号，换一轮研究或重传同一张照片就会变，内容却没变。
    参考照只认内容指纹（sha256）；地标只认特征文字，排序后再算，顺序不同不算不同的画。
    """
    ident = inp.identity if mode == IDENTITY_PHOTO else None
    visual = {
        "style": BRIEF_STYLE_VERSION, "size": SIZE, "template": inp.template_revision, "paper": inp.paper,
        "brush": inp.brush, "mood": inp.mood, "zones": TEXT_ZONES_T1,
        "identity": None if ident is None else [ident.species, ident.reference_sha256, list(ident.appearance_tags)],
        "landmarks": sorted(f.visual_feature for f in features),
        "fixed": [STICKERS, ROUTE, LAYOUT, LIGHT, IDENTITY_RULE, UNSEEN_MARKS_RULE],
    }
    return hashlib.sha256(json.dumps(visual, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def compile_journal_brief(inp: JournalBriefInput) -> JournalArtBrief:
    """编译一份手账画面简报。任何一条不过都抛 `PhotoDirectorError(原因码)`，不做"大概能用"的放行。"""
    _check_input(inp)
    mode, note, references = _identity(inp)
    features, excluded = _select(inp)
    prompt = _prompt(inp, mode, features)
    names = _name_forms(inp)  # 与 _select 同口径
    _require(not forbidden_in_prompt(prompt, names), "prompt_leaks_text")  # 纵深防御：编完再查一遍
    _require(mode == IDENTITY_PHOTO or not any(w in prompt for w in ANIMAL_WORDS), "prompt_leaks_animal")
    slots: dict[str, list[str]] = {}
    for event in inp.events:
        slots.setdefault(event.station_id, []).append(event.event_id)
    return JournalArtBrief(
        phase=inp.phase, plan_id=inp.plan_id, plan_revision=inp.plan_revision, template_revision=inp.template_revision,
        size=SIZE, prompt=prompt, identity_mode=mode, identity_note=note, references=references,
        landmark_fact_ids=tuple(f.fact_id for f in features), excluded=excluded,
        stamp_slots=tuple((sid, tuple(eids)) for sid, eids in slots.items()), text_zones=TEXT_ZONES_T1,
        route="decorative", capabilities_required=("reference_images",) if mode == IDENTITY_PHOTO else (),
        visual_digest=_digest(inp, mode, features),
    )
