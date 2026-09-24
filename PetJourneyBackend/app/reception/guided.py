"""引导便笺模式（未接接待模型）：接待员按固定的温和问题引导；主人的话“原样”进入待确认候选，
并由确定性规则给出**建议**（种类、槽位、是否含“别告诉它”一类限制）。建议只是默认选项，主人逐项确认；
规则不会替主人补编细节，不会把担心写成宠物人格，也不会把愿望写成过去经历。
"""

from __future__ import annotations

import re

from ..schemas.web.reception import CandidateKind, CandidateSubject, CareNoteSlot, ReceptionBranch

HOST_NAME = "星球接待员"
HOST_ROLE = "PetSoul 的 AI 接待角色"
MODEL_DISCLOSURE = "我是 PetSoul 的 AI 接待角色。你选择了让我用对话模型（{provider}）回应：你在这次接待里写的话会发送给该服务商生成回应；叮嘱仍然只摘录你的原话，由你决定交给 TA、只留在这里还是不保存。随时可以跳过。"
HOST_DISCLOSURE = "我是 PetSoul 的 AI 接待角色，现在是引导记录模式：你写的话会原样记成待确认的生活叮嘱，由你决定交给 TA、只留在这里还是不保存。不想说随时可以跳过。"

OPENING = {
    ReceptionBranch.own_pet: "我正在给 {name} 准备入住的小档案。有些只有你知道的小事——它怎么撒娇、习惯睡哪里、听到哪个小名会抬头——我也想替你带过去。有什么想特别交代的吗？一件小事也可以，我们不用一次说完。",
    ReceptionBranch.adopted: "{name} 第一次来到你家。你想怎样欢迎它？比如希望它怎么称呼你，或者给它准备了什么小角落。",
}
FOLLOW_UPS = [
    "好，我先把这句放进待确认的生活叮嘱里。还有别的小习惯吗？比如喜欢或不喜欢的互动。",
    "谢谢你。它有没有特别熟悉的物件，或者一个只有你们懂的称呼？",
    "好的。想说的差不多了就可以去整理叮嘱；以后想起来，还能在家里或通讯器的“补充叮嘱”里再补。",
]

PRIVACY_PATTERNS = re.compile(r"(别|不要|不用|不必)(告诉|跟|和|对)?(它|他|她|TA)(说|讲|知道)?|只留(在)?这里|别转达|不要转达|保密")
WISH_PATTERNS = re.compile(r"(以后|将来|希望|想带|想让|想去|想要|有一天)")
WORRY_PATTERNS = re.compile(r"(怪我|恨我|原谅|对不起|内疚|自责|哭)")
TITLE_PATTERN = re.compile(r"(?<![会在])(?:叫|喊|称呼)我(?!起床|起来|吃饭|回家|出门|睡觉|过去|过来|一起)[“\"「]?([一-龥A-Za-z]{1,6}?)[”\"」]?(?:就好|就行|吧|$|，|。|！)")
OBJECT_PATTERN = re.compile(r"((?:[红橙黄绿青蓝紫白黑灰粉棕米][色]的?)?(?:小)?(?:毯子|毛毯|垫子|软垫|窝|枕头|玩具|小球|围巾|衣服|毛巾))")
BOUNDARY_PATTERN = re.compile(r"(不喜欢|讨厌|害怕|怕)(被)?(抱|摸|洗澡|剪指甲|打扰|吵)|别(急着)?(抱|摸)")
TRAVEL_MOOD_PATTERN = re.compile(r"(安静|听歌|听音乐|看窗外|晕车|怕吵)")
SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?；;])")


def opening_line(branch: ReceptionBranch, pet_name: str) -> str:
    return OPENING[branch].format(name=pet_name)


def follow_up(turn_count: int) -> str:
    return FOLLOW_UPS[min(turn_count, len(FOLLOW_UPS) - 1)]


def _suggest(segment: str, branch: ReceptionBranch) -> tuple[CandidateKind, CandidateSubject, CareNoteSlot | None, str | None]:
    if PRIVACY_PATTERNS.search(segment) or WORRY_PATTERNS.search(segment):
        return CandidateKind.owner_private, CandidateSubject.owner, None, None
    title = TITLE_PATTERN.search(segment)
    if title:
        return CandidateKind.habit, CandidateSubject.relationship, CareNoteSlot.owner_title, title.group(1)
    if WISH_PATTERNS.search(segment):
        place = re.search(r"去(看)?([一-龥]{1,6}?)(?:$|，|。|！|吧)", segment)
        return CandidateKind.wish, CandidateSubject.relationship, CareNoteSlot.wish_place, place.group(2) if place else None
    obj = OBJECT_PATTERN.search(segment)
    if obj:
        return CandidateKind.habit, CandidateSubject.pet, CareNoteSlot.favorite_object, obj.group(1)
    if BOUNDARY_PATTERN.search(segment):
        return CandidateKind.habit, CandidateSubject.relationship, CareNoteSlot.interaction_boundary, None
    if TRAVEL_MOOD_PATTERN.search(segment):
        return CandidateKind.habit, CandidateSubject.pet, CareNoteSlot.travel_mood, None
    if branch is ReceptionBranch.adopted:
        return CandidateKind.wish, CandidateSubject.relationship, None, None
    return CandidateKind.habit, CandidateSubject.pet, None, None


def segment_owner_text(text: str, branch: ReceptionBranch = ReceptionBranch.own_pet) -> list[str]:
    """只在句子边界处拆分（原话不改写）：
    - 含用途限制/私人担忧的句子单独成段（“这件事别告诉它”这类短句并入它指向的上一句）；
    - 相邻句子建议的槽位不同（称呼 / 物件 / 互动边界 / 愿望……）时分开，方便主人逐条决定；
    - 同一话题的连续句子保留在一起，不丢上下文。
    """
    sentences = [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]
    if len(sentences) <= 1:
        return [text.strip()]
    groups: list[str] = []
    topics: list[tuple[CandidateKind, CareNoteSlot | None]] = []
    for sentence in sentences:
        private = bool(PRIVACY_PATTERNS.search(sentence) or WORRY_PATTERNS.search(sentence))
        if private and PRIVACY_PATTERNS.search(sentence) and not WORRY_PATTERNS.search(sentence) and groups and len(sentence) < 14:
            groups[-1] = groups[-1] + sentence
            topics[-1] = (CandidateKind.owner_private, None)
            continue
        kind, _, slot, _ = _suggest(sentence, branch)
        topic = (kind, slot)
        if groups and not private and topics[-1] == topic and topic[0] is not CandidateKind.owner_private and slot is None:
            groups[-1] = groups[-1] + sentence  # 同一话题且没有具体槽位：保留上下文
        else:
            groups.append(sentence)
            topics.append(topic)
    return groups


def suggestions_for(text: str, branch: ReceptionBranch) -> list[tuple[str, CandidateKind, CandidateSubject, CareNoteSlot | None, str | None]]:
    return [(segment, *_suggest(segment, branch)) for segment in segment_owner_text(text, branch)]


def rederive_slot_value(slot: CareNoteSlot | None, text: str) -> str | None:
    """更正文字后重新建议同一槽位的值；建议不出同一槽位就返回 None（不沿用旧值）。"""
    if slot is None:
        return None
    _, _, suggested_slot, value = _suggest(text, ReceptionBranch.own_pet)
    return value if suggested_slot is slot else None


def model_messages(branch: ReceptionBranch, pet_name: str, turns: list[dict]) -> list[dict[str, str]]:
    """接待模型提示：只回应与提一个小问题；不复述成结论、不编造经历；便笺仍由规则摘录原话。"""
    who = (f"新领养的原创伙伴「{pet_name}」——主人和它还没有共同往事，只聊怎样迎接它" if branch is ReceptionBranch.adopted
           else f"主人自己的宠物「{pet_name}」")
    system = "\n".join((
        f"你是 PetSoul 的 AI 接待角色「{HOST_NAME}」，正在帮主人为{who}准备入住。",
        "请用一两句话温和地回应主人刚写的话，然后只问一个具体、轻松的小问题，帮主人想起只有他知道的小事（称呼、喜欢的物件、不喜欢的互动、想一起去的地方）。",
        "规则：不要把主人的话改写成结论或替他总结；不要编造宠物的经历；主人提到离别、难过或自责时先安慰，不追问细节；不给医疗或法律建议；",
        "不要说“记下了/记住了/已保存/放进清单”——叮嘱要由主人确认后才保存；也不要承诺系统或宠物会做什么具体安排；",
        "不提“模型”“AI”“提示词”；不超过 60 个字；用中文。",
    ))
    messages = [{"role": "system", "content": system}]
    for turn in turns[-7:]:
        messages.append({"role": "assistant" if turn["speaker"] == "host" else "user", "content": str(turn["text"])[:500]})
    return messages

