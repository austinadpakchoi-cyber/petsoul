"""读懂 DNA 原话：把主人写的每一栏按小句拆开，找出和生活习惯有关的说法，判断是肯定、否定还是说不准。

只做确定性的规则（不调用模型，不产生付费调用）；每条结论都带着原话出处，主人能看到“为什么这样理解”：
- 小句：标点处断开；“但/不过/可是/然而/而是/其实/反而/只是/却”处也断开，转折、纠正之后的说法更算数；
- 否定：紧挨在说法前面（中间最多隔 2 个字）的“不、没、从不、不太、没那么、很少、不再……”把它变成否定；
  否定词离得远、中间隔着别的说法，或“不是不……”这类双重否定，都记为“说不准”，不强行归类；
  说法后面紧跟“不下来/不起来/不了/不住/不着”也是否定；“也、还、又、就、而且……”之后，前面的否定不再管到；
- 讨厌、害怕、受不了：明确的不喜欢（用于路线与工作倾向时会降低意愿）；
- 含糊：偶尔、有时、可能、也许、好像、大概、看心情……出现在说法之前，记为“说不准”；
- 时间：“以前/小时候/原来/曾经”的说法只作参考，“现在/如今/后来/最近/越来越/其实/不再”的说法更算数；
- 常见的非否定用法（非常、不管、不停、不但、没事、别人、哪怕……）不当作否定。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

NEAR = 2  # 否定词与说法之间最多隔几个字
TURN_WEIGHT, PRESENT_WEIGHT, PAST_WEIGHT, SOFT_FACTOR = 1.5, 1.5, 0.3, 0.8
SUFFIX_NEG = ("不下来", "不起来", "不了", "不住", "不着")
TURN = ("但是", "不过", "可是", "然而", "而是", "其实", "反而", "只是", "但", "却")

WORDS: dict[str, tuple[str, ...]] = {
    "hedge": ("不一定", "说不准", "说不好", "看心情", "有时候", "有时", "偶尔", "可能", "也许", "好像", "大概", "似乎", "时而", "间或"),
    "negate": ("一点也不", "一点都不", "从来不", "从来没", "根本不", "几乎不", "并没有", "并不", "并没", "没那么", "不怎么", "不太", "不大", "不算",
               "不是", "不再", "不会", "很少", "极少", "鲜少", "少有", "没有", "不", "没", "别", "非", "无"),
    "averse": ("受不了", "讨厌", "害怕", "怕"),
    "past": ("刚来的时候", "小时候", "年轻时", "以前", "之前", "原来", "过去", "曾经", "从前"),
    "present": ("这几年", "越来越", "现在", "如今", "后来", "最近", "变得", "其实", "反而"),
    "soft": ("有一点", "有点", "有些", "稍微", "略微"),
    "breaker": ("而且", "并且", "所以", "因为", "然后", "同时", "也", "还", "又", "就"),
    # 看起来像否定、其实不是：先占住位置，避免“非常”里的“非”、“不管”里的“不”被当成否定
    "plain": ("不得不", "非常", "特别", "不管", "不论", "无论", "不停", "不断", "不但", "不仅", "不光", "没事", "别人", "别的", "哪怕", "恐怕", "无聊"),
}
KIND = {word: kind for kind, words in WORDS.items() for word in words}
_TOKEN = re.compile("|".join(re.escape(w) for w in sorted(KIND, key=len, reverse=True)))
_TURN = re.compile("|".join(re.escape(w) for w in sorted(TURN, key=len, reverse=True)))
_PUNCT = re.compile(r"[，,。．.；;、！!？?\n\r～~…·/|()（）\[\]【】「」“”\"]+")


@dataclass(frozen=True)
class Evidence:
    key: str  # 特征或倾向：night_owl / social / job:bookstore / route:local:stroll ……
    field: str  # 来自哪一栏：personality / habits / note ……
    phrase: str  # 原话里的那一小句（原样，不改写）
    keyword: str
    polarity: str  # positive / negative / averse / uncertain
    weight: float
    note: str | None = None  # 为什么这样理解，例如“‘不’否定了这个说法”
    implied: bool = False  # 由别的说法反推出来的（例如“不爱热闹”→ 偏安静），单独不足以归类


@dataclass(frozen=True)
class Match:
    key: str
    word: str
    start: int
    end: int


def clauses(text: str) -> list[tuple[str, bool]]:
    """[(小句, 是否在转折/纠正之后)]。"""
    found: list[tuple[str, bool]] = []
    for piece in _PUNCT.split(text or ""):
        piece = piece.strip()
        if not piece:
            continue
        starts = [0] + [m.start() for m in _TURN.finditer(piece) if m.start() > 0]
        for index, start in enumerate(starts):
            end = starts[index + 1] if index + 1 < len(starts) else len(piece)
            part = piece[start:end].strip()
            if part:
                found.append((part, index > 0 or bool(_TURN.match(piece))))
    return found


def find(clause: str, groups: dict[str, tuple[str, ...]]) -> list[Match]:
    """每一组各自找：同一组里长词优先、不重叠；不同组之间可以重叠（“海边”既是散步也是渔港的线索）。"""
    found: list[Match] = []
    for key, words in groups.items():
        taken: list[tuple[int, int]] = []
        for word in sorted(words, key=len, reverse=True):
            start = clause.find(word)
            while start != -1:
                end = start + len(word)
                if not any(s < end and start < e for s, e in taken):
                    taken.append((start, end))
                    found.append(Match(key, word, start, end))
                start = clause.find(word, start + 1)
    return sorted(found, key=lambda m: (m.start, m.key))


def judge(clause: str, match: Match, others: list[Match], after_turn: bool) -> tuple[str, float, str | None]:
    """(polarity, 权重, 说明)。只看这个说法前面、同一小句里的修饰词；否定词只管到最近的断开词（也、还、就……）为止。"""
    tokens = [(m.start(), m.end(), m.group(), KIND[m.group()]) for m in _TOKEN.finditer(clause[:match.start])]
    cut = max((end for _, end, _, kind in tokens if kind == "breaker"), default=0)
    weight, note = (TURN_WEIGHT, "转折/纠正之后的说法更算数") if after_turn else (1.0, None)
    temporal = [t for t in tokens if t[3] in ("past", "present")]
    if temporal:
        word, kind = temporal[-1][2], temporal[-1][3]
        weight, note = (PAST_WEIGHT, f"“{word}”：以前的样子，只作参考") if kind == "past" else (PRESENT_WEIGHT, f"“{word}”：按现在的样子")
    if any(t[3] == "soft" for t in tokens):
        weight *= SOFT_FACTOR
    hedge = next((t for t in tokens if t[3] == "hedge"), None)
    if hedge is not None:
        return "uncertain", weight, f"“{hedge[2]}”：说法不确定，暂不归类"
    negators = [t for t in tokens if t[3] in ("negate", "averse") and t[0] >= cut]
    if negators:
        start, end, word, kind = negators[-1]
        between = [o for o in others if o is not match and o.start >= end and o.end <= match.start]
        if match.start - end > NEAR or between:
            return "uncertain", weight, f"“{word}”离这个说法较远，暂不归类"
        earlier = [t for t in negators[:-1] if start - t[1] <= 1 and t[3] == "negate"]
        if earlier and kind == "negate":
            return "uncertain", weight, f"“{clause[earlier[-1][0]:end]}”双重否定，暂不归类"
        if word == "不再":
            weight = max(weight, PRESENT_WEIGHT)
        if kind == "averse":
            return "averse", weight, f"“{word}”：不喜欢/害怕"
        return "negative", weight, f"“{word}”否定了这个说法"
    suffix = next((s for s in SUFFIX_NEG if clause[match.end:].startswith(s)), None)
    if suffix is not None:
        return "negative", weight, f"“{suffix}”否定了这个说法"
    return "positive", weight, note


def read(field: str, text: str, groups: dict[str, tuple[str, ...]]) -> list[Evidence]:
    """一栏原话 → 与各组说法有关的证据（没提到的不产生证据）。"""
    evidence: list[Evidence] = []
    for clause, after_turn in clauses(text):
        matches = find(clause, groups)
        for match in matches:
            polarity, weight, note = judge(clause, match, matches, after_turn)
            evidence.append(Evidence(match.key, field, clause, match.word, polarity, round(weight, 2), note))
    return evidence
