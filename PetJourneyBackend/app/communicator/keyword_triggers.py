from __future__ import annotations

from .schemas import CommunicatorIntent


NEGATION_WORDS = ("不是", "不用", "别", "不要", "以前", "之前", "刚才不是")

KEYWORD_TRIGGERS: list[tuple[CommunicatorIntent, tuple[str, ...]]] = [
    (
        CommunicatorIntent.emotional_distress,
        ("撑不住", "好难受", "不想活", "崩溃", "受不了了", "好痛苦", "活不下去", "想死"),
    ),
    (
        CommunicatorIntent.farewell_or_grief_spike,
        ("再也见不到", "最后一次", "告别", "离开我", "回不来了", "我好想ta", "我好想TA"),
    ),
    (
        CommunicatorIntent.current_status_visual_request,
        ("你现在干嘛", "现在干嘛", "在干嘛", "你在做什么", "看看你", "给我看看", "让我看看你", "拍给我看看", "发张现在的照片", "你那边怎么样", "你那里现在什么样"),
    ),
    (
        CommunicatorIntent.photo_request,
        ("拍张照片", "发张照片", "给我拍一张", "再拍一张", "拍给我", "自拍一下", "看看风景", "给我看风景", "发个自拍"),
    ),
    (
        CommunicatorIntent.postcard_request,
        ("寄张明信片", "给我寄明信片", "写张明信片", "发张明信片"),
    ),
    (
        CommunicatorIntent.location_check,
        ("你在哪", "现在在哪", "到哪里了", "你去哪里了", "现在到哪了", "你在什么地方"),
    ),
    (
        CommunicatorIntent.affection_i_miss_you,
        ("想你了", "我好想你", "想抱抱你", "想摸摸你", "宝宝", "乖乖", "回来看看我", "爱你"),
    ),
    (
        CommunicatorIntent.care_check,
        ("累不累", "饿不饿", "冷不冷", "有没有休息", "有没有吃东西", "今天开心吗", "困不困"),
    ),
]


def has_negation_context(text: str) -> bool:
    return any(word in text for word in NEGATION_WORDS)


def match_keyword_intent(text: str) -> CommunicatorIntent | None:
    clean = text.strip()
    if not clean:
        return None
    for intent, keywords in KEYWORD_TRIGGERS:
        if any(keyword in clean for keyword in keywords):
            if intent in {CommunicatorIntent.current_status_visual_request, CommunicatorIntent.photo_request} and has_negation_context(clean):
                return CommunicatorIntent.general_chat
            return intent
    return None
