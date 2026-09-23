"""DNA 行为画像：同一份 DNA（注册、照片与接待时收集的资料）既决定 TA 怎么说话，也决定 TA 怎么过日子。

对齐说明（2026-09-22）：爱热闹、恋家、慢热、好奇、爱睡觉或爱熬夜，应影响作息、出门频率、路线兴趣、工作倾向与分享方式；
不能只把性格拼进聊天提示词，却让所有宠物运行相同的日程。DNA 决定倾向，当前时间、地点、钱包、目标与状态决定此刻能做什么。

规则版本 dna-behavior-2026.2（修复独立核查 P2：“不爱熬夜，不爱热闹，喜欢安静”曾被判成夜猫子、爱热闹、每天想出门三次）：
- 不再对整段文字做关键词子串命中，而是按小句读（dna_reading）：否定、转折与纠正（“以前…现在…”“不是…而是…”）、
  含糊说法（偶尔、有时、可能……）分别对待；
- 每条结论都保留原话出处（哪一栏、哪一句、被哪个词影响）；不确定或前后说法矛盾的不强行归类，列入 unclassified；
- 仍然只做确定性规则，结果可复现、可测试，不调用模型、不产生付费调用。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import time
from typing import Iterable

from .dna_reading import Evidence, read

RULES_VERSION = "dna-behavior-2026.2"
DEFAULT_SLEEP, DEFAULT_WAKE = time(23, 30), time(7, 30)
APPLY = 0.75  # 净分到这个数才算数（一句明确的话记 1 分）
CLEAR_WIN = 1.0  # 两种相反的说法都成立时，至少高出这么多才按强的一方，否则都不算
IMPLIED = 0.5  # 由否定反推的分量（“不爱热闹”→ 偏安静）：单独不足以归类

NIGHT_OWL = ("熬夜", "夜猫子", "晚上不睡", "半夜", "夜里精神", "晚睡", "睡得晚", "深夜", "通宵")
EARLY_BIRD = ("早起", "天一亮", "清晨", "早睡", "起得早", "睡得早", "一大早")
SLEEPY = ("爱睡", "贪睡", "嗜睡", "懒", "睡不醒", "一天到晚睡", "睡懒觉", "午睡", "打盹", "能睡")
SOCIAL = ("爱热闹", "喜欢热闹", "凑热闹", "外向", "黏人", "粘人", "活泼", "话多", "话痨", "热情", "闹腾", "爱交朋友", "自来熟", "人来疯")
HOMEBODY = ("恋家", "宅", "安静", "慢热", "胆小", "内向", "怕生", "认生", "害羞", "文静", "独立", "高冷", "不爱出门", "不喜欢出门", "很少出门",
            "讨厌热闹", "怕热闹", "怕吵", "躲起来")
CURIOUS = ("好奇", "爱冒险", "冒险", "闲不住", "探险", "爱跑", "精力旺盛", "爱玩", "爱出门", "喜欢出门", "爱出去", "到处跑", "到处逛")
DILIGENT = ("聪明", "好学", "认真", "专注", "机灵", "学得快")
PLAYFUL = ("贪玩", "坐不住", "三分钟热度", "懒")
FEAR_HOMEBODY = ("陌生人", "生人", "人多", "热闹", "吵")  # 只看“害怕的东西”一栏：怕这些 → 偏恋家（单独不足以归类）

# 喜好/习惯里的关键词 → 更愿意做的活（倍数）
JOB_HINTS: dict[str, tuple[str, ...]] = {
    "bookstore": ("书", "看书", "安静"),
    "florist": ("花", "植物", "叶子", "种", "草"),
    "cafe_helper": ("咖啡", "做饭", "烤", "甜点", "吃", "厨房"),
    "post_office": ("信", "邮", "送东西", "叼报纸"),
    "fishing_port": ("鱼", "海", "船", "游泳"),
    "ranch": ("羊", "草原", "跑", "牧"),
    "ranger": ("爬山", "森林", "山", "树"),
    "camel_team": ("骆驼", "沙", "沙漠"),
}
# 喜好里的关键词 → 更愿意去的地方（倍数）
ROUTE_HINTS: dict[str, tuple[str, ...]] = {
    "local:stroll": ("散步", "晒太阳", "草地", "公园", "看海", "海边", "山"),
    "local:cafe": ("咖啡", "奶茶", "甜点", "吃", "零食"),
    "local:city_trip": ("逛街", "热闹", "看人", "城里"),
    "long": ("看海", "坐船", "飞", "远方", "旅行", "旅游", "去远方"),
}
TRAIT_GROUPS = {"night_owl": NIGHT_OWL, "early_bird": EARLY_BIRD, "sleepy": SLEEPY, "social": SOCIAL, "homebody": HOMEBODY,
                "curious": CURIOUS, "diligent": DILIGENT, "playful": PLAYFUL}
HINT_GROUPS = {**{f"job:{k}": v for k, v in JOB_HINTS.items()}, **{f"route:{k}": v for k, v in ROUTE_HINTS.items()}}
OPPOSITE = {"social": "homebody", "homebody": "social"}  # 否定一端 → 轻微偏向另一端

LABELS = {
    "night_owl": "爱熬夜", "early_bird": "早睡早起", "sleepy": "爱睡觉", "social": "爱热闹", "homebody": "恋家安静", "curious": "好奇爱跑",
    "diligent": "认真好学", "playful": "贪玩",
    "job:bookstore": "在书店理书", "job:florist": "在花店帮忙", "job:cafe_helper": "在咖啡馆帮工", "job:post_office": "在邮局分拣信件",
    "job:fishing_port": "去渔港帮忙收网", "job:ranch": "去牧场帮忙看羊", "job:ranger": "跟着护林员巡山", "job:camel_team": "帮骆驼队牵绳",
    "route:local:stroll": "在家附近走走", "route:local:cafe": "去附近喝一杯", "route:local:city_trip": "进城逛逛", "route:long": "出远门",
}
FIELD_LABELS = {
    "personality": "性格", "voice_style": "说话的样子", "catchphrase": "口头禅", "habits": "小习惯", "hobbies": "爱好",
    "favorite_places": "喜欢的地方", "favorite_foods": "爱吃的", "fears": "害怕的东西", "dream": "梦想", "note": "接待时的叮嘱", "text": "描述",
}
DNA_FIELDS = ("personality", "voice_style", "catchphrase", "habits", "hobbies", "favorite_places", "favorite_foods", "fears")


@dataclass(frozen=True)
class TraitReading:
    key: str
    label: str
    status: str  # applied 用上了 / negated 明确说不是 / outweighed 被更明确的相反说法盖过 / uncertain 说不准，暂不归类
    score: float
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class PreferenceReading:
    key: str  # job:bookstore / route:local:stroll / route:long
    label: str
    weight: float  # 倍数：>1 更愿意，<1 不太愿意
    evidence: tuple[Evidence, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class BehaviorProfile:
    sleep_start: time = DEFAULT_SLEEP
    wake: time = DEFAULT_WAKE
    sociability: str = "steady"  # social / steady / homebody
    curious: bool = False
    night_owl: bool = False
    outings_per_day: int = 2
    chattiness: int = 2  # 每天主动找主人说话的次数
    learn_rate: float = 1.0  # 学东西的快慢（驾考自学/陪练）
    job_affinity: dict[str, float] = field(default_factory=dict)
    route_interest: dict[str, float] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()  # 推导结论（给展示“为什么”）
    rhythm: str = "regular"  # regular / night_owl / early_bird / sleepy
    traits: tuple[TraitReading, ...] = ()
    preferences: tuple[PreferenceReading, ...] = ()
    unclassified: tuple[str, ...] = ()  # 提到了但说不准、或前后矛盾而没有归类的原话
    sources: tuple[str, ...] = ()  # 用到了哪些栏目
    rules_version: str = RULES_VERSION


def profile_sources(*, personality: str | None = None, dna=None, notes: list[str] | None = None) -> list[tuple[str, str]]:
    """[(栏目, 原话)]：列表栏目逐条保留，便于追溯；完全相同的原话只算一次。"""
    raw: list[tuple[str, str]] = [("personality", personality)] if personality else []
    if dna is not None:
        for name in DNA_FIELDS:
            value = getattr(dna, name, None)
            raw += [(name, item) for item in (value if isinstance(value, list) else [value]) if item]
    raw += [("note", note) for note in notes or [] if note]
    unique: dict[str, str] = {}
    for name, text in raw:
        unique.setdefault(text, name)
    return [(name, text) for text, name in unique.items()]


def profile_text(*, personality: str | None = None, dna=None, notes: list[str] | None = None) -> str:
    """兼容旧调用：拼成一段文字（新代码请用 profile_sources，保留栏目出处）。"""
    return "；".join(text for _, text in profile_sources(personality=personality, dna=dna, notes=notes))


def _evidence(sources: list[tuple[str, str]]) -> list[Evidence]:
    found: list[Evidence] = []
    for name, text in sources:
        found += read(name, text, TRAIT_GROUPS)
        hints = read(name, text, HINT_GROUPS)
        if name == "fears":  # 写在“害怕的东西”里的，都是不喜欢
            hints = [replace(e, polarity="averse", note="写在“害怕的东西”里") if e.polarity != "uncertain" else e for e in hints]
            found += [replace(e, key="homebody", weight=IMPLIED, note="害怕这些：偏恋家（单独不足以归类）", implied=True)
                      for e in read(name, text, {"homebody": FEAR_HOMEBODY}) if e.polarity == "positive"]
        found += hints
    found += [Evidence(OPPOSITE[e.key], e.field, e.phrase, e.keyword, "positive", IMPLIED, f"由“{e.phrase}”反推（单独不足以归类）", implied=True)
              for e in found if e.key in OPPOSITE and e.polarity in ("negative", "averse")]
    return found


def _reading(key: str, items: list[Evidence]) -> TraitReading:
    positive = sum(e.weight for e in items if e.polarity == "positive")
    negative = sum(e.weight for e in items if e.polarity in ("negative", "averse"))
    score = round(positive - negative, 2)
    status = "applied" if score >= APPLY else ("negated" if score <= -APPLY else "uncertain")
    return TraitReading(key, LABELS[key], status, score, tuple(items))


def _resolve(readings: dict[str, TraitReading], a: str, b: str) -> None:
    """同一条轴的两端：都成立时明显更强的一方算数、另一方记为被盖过，差不多就都不算（说不准）；
    一端明确成立、另一端只是含糊或“以前”的说法（“以前爱熬夜，现在早睡早起”）→ 另一端记为被盖过。"""
    first, second = readings.get(a), readings.get(b)
    if not (first and second):
        return
    if {first.status, second.status} == {"applied", "uncertain"}:
        loser = first if first.status == "uncertain" else second
        readings[loser.key] = replace(loser, status="outweighed")
        return
    if not first.status == second.status == "applied":
        return
    if abs(first.score - second.score) >= CLEAR_WIN:
        loser = second if first.score > second.score else first
        readings[loser.key] = replace(loser, status="outweighed")
    else:
        readings[a], readings[b] = replace(first, status="uncertain"), replace(second, status="uncertain")


def derive_profile(source: str | Iterable[tuple[str, str]]) -> BehaviorProfile:
    sources = [("text", source)] if isinstance(source, str) else [(name, text) for name, text in source if text]
    evidence = _evidence(sources)
    readings = {key: _reading(key, [e for e in evidence if e.key == key]) for key in TRAIT_GROUPS if any(e.key == key for e in evidence)}
    for a, b in (("night_owl", "early_bird"), ("social", "homebody"), ("diligent", "playful")):
        _resolve(readings, a, b)
    on = {key for key, reading in readings.items() if reading.status == "applied"}
    reasons: list[str] = []
    rhythm = "night_owl" if "night_owl" in on else "early_bird" if "early_bird" in on else "sleepy" if "sleepy" in on else "regular"
    sleep, wake = {"night_owl": (time(1, 30), time(9, 30)), "early_bird": (time(22, 0), time(6, 0)), "sleepy": (time(23, 0), time(8, 30))}.get(
        rhythm, (DEFAULT_SLEEP, DEFAULT_WAKE))
    window = f"{sleep:%H:%M} 睡，{wake:%H:%M} 起"
    if rhythm != "regular":
        reasons.append({"night_owl": "爱熬夜：晚睡晚起", "early_bird": "早起：早睡早起", "sleepy": "爱睡觉：睡得久"}[rhythm] + f"（{window}）")
    elif readings.get("night_owl") and readings["night_owl"].status == "negated":
        reasons.append(f"不爱熬夜：按平常作息（{window}）")
    elif any(k in readings for k in ("night_owl", "early_bird", "sleepy")):
        reasons.append(f"作息的说法不确定：按平常作息（{window}）")
    sociability = "social" if "social" in on else ("homebody" if "homebody" in on else "steady")
    curious = "curious" in on
    outings = {"social": 3, "steady": 2, "homebody": 1}[sociability]
    if curious:
        outings = min(3, outings + 1)
        reasons.append("好奇：更常出门、更想去远处")
    if "sleepy" in on:
        outings = max(1, outings - 1)
    if sociability != "steady":
        reasons.append("爱热闹：常出门、话多" if sociability == "social" else "恋家：少出门、话少")
    elif any(readings.get(k) and readings[k].status in ("uncertain", "outweighed") for k in ("social", "homebody")):
        reasons.append("热闹还是安静：说法不一，按平常的节奏")
    learn = 1.3 if "diligent" in on else (0.8 if "playful" in on else 1.0)
    if learn != 1.0:
        reasons.append("认真好学：学东西快" if learn > 1 else "贪玩：学东西慢一些")
    jobs, routes, preferences = _preferences(evidence, sociability, curious)
    unclassified = [e.phrase for reading in readings.values() if reading.status == "uncertain" for e in reading.evidence if not e.implied]
    return BehaviorProfile(sleep_start=sleep, wake=wake, sociability=sociability, curious=curious, night_owl=rhythm == "night_owl", outings_per_day=outings,
                           chattiness={"social": 3, "steady": 2, "homebody": 1}[sociability], learn_rate=learn, job_affinity=jobs, route_interest=routes,
                           reasons=tuple(reasons), rhythm=rhythm, traits=tuple(readings.values()), preferences=preferences,
                           unclassified=tuple(dict.fromkeys(unclassified)), sources=tuple(dict.fromkeys(name for name, _ in sources)))


def _preferences(evidence: list[Evidence], sociability: str, curious: bool) -> tuple[dict[str, float], dict[str, float], tuple[PreferenceReading, ...]]:
    """工作与路线倾向：明确喜欢 → 加倍；明确讨厌、害怕 → 减半；只是否定或说不准 → 不加分（照常）。"""
    weights: dict[str, float] = {}
    notes: dict[str, list[str]] = {}
    for key in HINT_GROUPS:
        items = [e for e in evidence if e.key == key]
        if not items:
            continue
        reading = _reading(key, items)
        if reading.status == "applied":
            weights[key] = 2.0 if key.startswith("job:") else 1.5
        elif any(e.polarity == "averse" for e in items):
            weights[key] = 0.5
        else:
            weights[key] = 1.0

    def scale(key: str, factor: float, why: str) -> None:
        weights[key] = round(weights.get(key, 1.0) * factor, 2)
        notes.setdefault(key, []).append(why)

    if sociability == "homebody":
        scale("route:local:stroll", 1.5, "恋家：更爱在附近走走")
        scale("route:long", 0.3, "恋家：不太想出远门")
    if sociability == "social":
        scale("route:local:city_trip", 1.5, "爱热闹：更爱进城逛")
        scale("route:local:cafe", 1.3, "爱热闹：更爱去店里坐坐")
    if curious:
        scale("route:long", 1.5, "好奇：更想去远处")
        scale("route:local:city_trip", 1.3, "好奇：更爱进城看看")
    readings = tuple(PreferenceReading(key, LABELS[key], weight, tuple(e for e in evidence if e.key == key), tuple(notes.get(key, ())))
                     for key, weight in weights.items())
    jobs = {key.split(":", 1)[1]: w for key, w in weights.items() if key.startswith("job:") and w != 1.0}
    routes = {key.split(":", 1)[1]: w for key, w in weights.items() if key.startswith("route:") and w != 1.0}
    return jobs, routes, readings
