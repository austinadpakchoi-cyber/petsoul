from __future__ import annotations

import re

# 展示层地名规则：中英混排品牌名只留中文（"LONE STAR孤星汉堡"→"孤星汉堡"），
# 纯外文名保留但收敛长度，去掉营销尾巴。与 iOS 端 PlaceDisplayName 保持同一套规则。

MAX_DISPLAY_LENGTH = 18

_LATIN_PREFIX = re.compile(r"^[A-Za-z0-9&'’\.\-\s]+")
_PARENTHETICAL = re.compile(r"[（(][^）)]*[）)]")
_MARKETING_SEPARATORS = ("|", "·-", " - ", "——")


def display_name(raw: str | None) -> str:
    if not raw:
        return ""
    name = raw.strip()
    name = _PARENTHETICAL.sub("", name).strip()

    for separator in _MARKETING_SEPARATORS:
        if separator in name:
            name = name.split(separator)[0].strip()

    # 中英混排：中文部分已经是完整名字时，去掉前置拉丁品牌串。
    if _has_cjk(name):
        stripped = _LATIN_PREFIX.sub("", name).strip()
        if _has_cjk(stripped) and len(stripped) >= 2:
            name = stripped

    if len(name) > MAX_DISPLAY_LENGTH:
        name = name[:MAX_DISPLAY_LENGTH].rstrip() + "…"
    return name or raw.strip()


def _has_cjk(text: str) -> bool:
    return any("一" <= char <= "鿿" for char in text)
