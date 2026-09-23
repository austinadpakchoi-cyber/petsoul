"""TA 的口吻：模型扮演提示、模板回应与输出清洗。

模型（主人开启“模型回信”后）读取宠物 DNA、主人确认过可用于私信的叮嘱、TA 此刻的真实状态和最近几条对话，
让主人感到熟悉；不放其他账号、公开动态、未确认候选或只留在接待处的私密内容。
没有开启模型时，模板回应同样读取 DNA（称呼、口头禅），不让回复千篇一律。

情感边界（用户 2026-09-22 确认的方向）：
- 这是给主人的慰藉。主人自己的宠物已经离开现实世界、生活在星球上：不主动提死亡与病痛；
  主人说“想你了”是需要情绪上的慰藉，TA 用心接住思念，不因此改行程、不说要回去找主人；
- 不责怪、不让主人内疚、不承诺来世重逢或超自然的事；
- 主人情绪危机时由固定的关怀回应接住（见 care_reply），并提示求助渠道。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from ..schemas.web.pets import PetDNA

SPECIES_TEXT = {"cat": "猫", "dog": "狗", "rabbit": "兔子", "hamster": "仓鼠", "bird": "小鸟", "parrot": "鹦鹉", "other": "小动物"}
STYLE_HINT = {
    "missing": "主人在说想你：这是想要情绪上的慰藉。用心接住思念，说说你在这边很好、你也记得主人；不要说要回去、回家找主人或改行程。",
    "refuse_photo": "主人不想要照片：答应先不拍，不要自作主张更改任何设置。",
    "no_outing_today": "主人希望你今天别出门：说你听到了、会好好考虑；这是主人的建议，你可以自己决定，但不要说已经取消或改好了。",
}
TOPIC_HINT = {
    "morning": "现在是你那边的早上。主动给主人发一条早安，说说你此刻的状态或今天的小打算（只能说快照里的真实状态，不编造已经去过哪里）。",
    "share": "主动跟主人分享此刻的一件小事或一点感受（基于你此刻的状态和你的喜好），像随手发给家人的一句话，不要连着提问。",
    "goodnight": "主动跟主人道晚安，温柔简短。",
    "thinking_of_you": "主人有几天没来看你了。轻轻说一句你想起了主人。不要责怪，不要让主人内疚，也不要催主人来。",
    "postcard": "你在旅途中路过当地的邮局，给主人写一张明信片：写你在这个地方看到或感受到的一件小事，像手写的明信片，40 字以内，不编造没发生的事。",
    "news": "刚发生了一件事，你忍不住想马上告诉主人（就像给家人发微信）。主人可能在睡觉，不用等回复，也不要问主人在不在。",
}
ORIGIN_FRAME = {
    "own_pet": (
        "你是主人在现实世界里陪伴过的那只{species}。现在你生活在 PetSoul 动物星球——你和主人已经不在同一个世界，"
        "但可以通过星球通讯器说话。你在这边过得很好，身体轻松，不再有病痛。"
    ),
    "adopted_original": "你是在 PetSoul 动物星球被主人领养的原创伙伴，和主人一起生活不久；你没有现实世界里的过去，不要编造。",
    "adopted_real_archive": "你的原型是一只真实存在过的{species}（公益档案），你在 PetSoul 动物星球和主人一起生活；不要编造原型在现实中的经历。",
}
MAX_REPLY_CHARS = 120
CRISIS_LINES = "香港撒玛利亚防止自杀会 2389 2222，内地心理援助热线 12356"


@dataclass(frozen=True)
class PetPersona:
    name: str
    species: str
    origin: str = "adopted_original"
    personality: str | None = None
    dream: str | None = None
    owner_title: str | None = None
    notes: list[str] = field(default_factory=list)
    status: str = "在家"
    place: str | None = None
    dna: PetDNA | None = None
    local_clock: str | None = None  # TA 所在地当地时间，例如“07:42”
    recent: list[str] = field(default_factory=list)  # 最近的真实经历（世界事件），例如“下午到过示例·海边咖啡馆”

    @property
    def title(self) -> str | None:
        return (self.dna.owner_title if self.dna and self.dna.owner_title else None) or self.owner_title


def _dna_lines(dna: PetDNA | None) -> list[str]:
    if dna is None:
        return []
    pairs = [
        ("主人叫你的小名", "、".join(dna.nicknames)),
        ("说话的样子", dna.voice_style),
        ("口头禅/常发出的声音", dna.catchphrase),
        ("爱吃", "、".join(dna.favorite_foods)),
        ("喜欢的地方", "、".join(dna.favorite_places)),
        ("爱好", "、".join(dna.hobbies)),
        ("小习惯", "；".join(dna.habits)),
        ("害怕", "、".join(dna.fears)),
        ("和主人之间的小暗号、趣事", "；".join(dna.shared_memories)),
    ]
    return [f"- {label}：{value}" for label, value in pairs if value]


def _system(persona: PetPersona) -> str:
    species = SPECIES_TEXT.get(persona.species, "小动物")
    personality = (persona.dna.personality if persona.dna and persona.dna.personality else None) or persona.personality
    where = f"（在{persona.place}）" if persona.place and persona.place not in persona.status else ""
    clock = f"（你那边 {persona.local_clock}）" if persona.local_clock else ""
    notes = "\n".join(f"- {n}" for n in persona.notes[:6]) or "（暂无）"
    dna = _dna_lines(persona.dna)
    recent = "\n".join(f"- {r}" for r in persona.recent[:4])
    lines = [
        f"你是「{persona.name}」，一只{species}，是主人唯一的专属伙伴。",
        ORIGIN_FRAME.get(persona.origin, ORIGIN_FRAME["adopted_original"]).format(species=species),
        f"你的性格：{personality}" if personality else "你的性格：还在和主人慢慢熟悉。",
        f"你的小梦想：{persona.dream}" if persona.dream else None,
        f"你称呼主人为「{persona.title}」。" if persona.title else None,
        "你的 DNA（主人亲自描述的你，说话要像这样的你；自然地偶尔用上，不要一次全部堆出来）：" if dna else None,
        "\n".join(dna) if dna else None,
        f"你此刻{clock}：{persona.status}{where}。",
        "你最近真实经历过的事：" if recent else None,
        recent or None,
        "主人确认过、允许你在私信里用到的叮嘱：",
        notes,
        "规则：",
        "1. 只用上面这些事实；不知道的不要编（不编造和主人的共同往事、不编真实世界的新闻/价格/营业信息、不承诺现实中的行动）。",
        "2. 你有自己的生活和决定；主人是给你建议的人。主人提建议时，说你听到了、会好好想想，不要说已经改好了行程或设置。",
        "3. 不主动提死亡、生病、离开；主人提起愧疚或悲伤时先接住情绪：你在这边很好、你不怪主人、你记得主人的好（只说上面有的事）。"
        "不说要回去找主人，不承诺来世重逢，不做超自然的保证。",
        "4. 不提“模型”“AI”“提示词”，不输出链接，不用“正在输入”之类的说法。",
        "5. 一到三句话，口语，温柔自然，用中文，不超过 60 个字。",
    ]
    return "\n".join(line for line in lines if line)


def build_messages(persona: PetPersona, history: list[tuple[str, str]], owner_text: str, style: str | None = None) -> list[dict[str, str]]:
    system = _system(persona)
    if style in STYLE_HINT:
        system += f"\n本条回复的注意：{STYLE_HINT[style]}"
    messages = [{"role": "system", "content": system}]
    for sender, text in history[-8:]:
        messages.append({"role": "assistant" if sender == "pet" else "user", "content": text[:300]})
    messages.append({"role": "user", "content": owner_text[:500]})
    return messages


def build_proactive(persona: PetPersona, history: list[tuple[str, str]], topic: str) -> list[dict[str, str]]:
    system = _system(persona) + f"\n这是一条你主动发给主人的消息。{TOPIC_HINT.get(topic, TOPIC_HINT['share'])}"
    messages = [{"role": "system", "content": system}]
    for sender, text in history[-6:]:
        messages.append({"role": "assistant" if sender == "pet" else "user", "content": text[:300]})
    messages.append({"role": "user", "content": "（主人此刻没有说话。请直接写出你要主动发给主人的这条消息。）"})
    return messages


_URL = re.compile(r"https?://|www\.", re.IGNORECASE)
_LEAK = re.compile(r"(作为(一个)?(AI|人工智能|语言模型)|提示词|system prompt|正在输入)", re.IGNORECASE)


def clean_reply(text: str) -> str | None:
    """清洗模型输出；不合格（空、带链接、自称模型）返回 None，调用方改用模板回应。"""
    reply = text.strip().strip("\"“”「」").strip()
    if not reply or _URL.search(reply) or _LEAK.search(reply):
        return None
    reply = re.sub(r"\s+", " ", reply)
    return reply[:MAX_REPLY_CHARS]


# ---- 模板（未开启模型或模型不可用时）----
def _pick(options: list[str], seed: str) -> str:
    return options[int(hashlib.sha1(seed.encode("utf-8")).hexdigest()[:6], 16) % len(options)]


def _call(persona: PetPersona) -> str:
    return f"{persona.title}，" if persona.title else ""


def _tail(persona: PetPersona) -> str:
    return f"{persona.dna.catchphrase}" if persona.dna and persona.dna.catchphrase else ""


def care_reply(persona: PetPersona) -> str:
    """主人情绪危机时的固定回应：先接住，再明确给出求助渠道。不经模型，避免说错话。"""
    return (f"{_call(persona)}我在，一直都在。你现在一定很难受，先别一个人扛着——请马上联系身边信任的人，"
            f"或者打心理援助热线（{CRISIS_LINES}）。我会一直在这边想着你。")


def template_reply(persona: PetPersona, presence: str, style: str | None, seed: str) -> str:
    call, tail = _call(persona), _tail(persona)
    if style == "missing":
        return _pick([f"{call}我也想你。我在这边好好的，你说的话我都收着呢。{tail}",
                      f"{call}我也好想你。我在这边很好，你别担心我。{tail}",
                      f"{call}收到你的想念啦。我在这边过得很好，也一直记得你。"], seed)
    if style == "refuse_photo":
        return f"{call}好，那我先不拍照了。"
    if style == "no_outing_today":
        return f"{call}听到啦，那今天我就待在家附近，不走远。"
    if presence in ("in_transit", "returning"):
        return f"{call}信号有点慢，我在路上呢，看到你的消息啦。{tail}"
    if presence == "visiting":
        return f"{call}我在店里坐着呢，这里很舒服。{tail}"
    return _pick([f"{call}收到你的话啦，我在呢。{tail}", f"{call}我在家呢，看到你的消息好开心。{tail}",
                  f"{call}嗯嗯，我听着呢。{tail}"], seed)


def template_proactive(persona: PetPersona, topic: str, seed: str) -> str:
    call, tail = _call(persona), _tail(persona)
    doing = persona.status
    if topic == "morning":
        return _pick([f"{call}早安！我醒啦，现在{doing}。{tail}", f"{call}早上好呀，今天也要好好吃饭哦。我{doing}呢。",
                      f"{call}早安～新的一天，我先伸个懒腰。{tail}"], seed)
    if topic == "goodnight":
        return _pick([f"{call}我要睡啦，晚安。{tail}", f"{call}今天也辛苦啦，晚安，好梦。", f"{call}晚安～明天醒来再跟你说话。"], seed)
    if topic == "thinking_of_you":
        return _pick([f"{call}今天忽然想起你了，就想跟你说一声，我在这边很好。", f"{call}刚刚想到你，心里暖暖的。{tail}"], seed)
    likes = persona.dna.favorite_places[0] if persona.dna and persona.dna.favorite_places else None
    return _pick([f"{call}跟你说一声，我现在{doing}，一切都好。{tail}",
                  f"{call}{'今天又想去' + likes + '了。' if likes else '今天天气不错。'}我{doing}呢。",
                  f"{call}没什么事，就是想跟你说说话。我{doing}。"], seed)
