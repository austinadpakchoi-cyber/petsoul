"""TA 主动发来的消息：像家人之间的微信——想到了、遇到好玩的就发过去，不按固定时段。

规则由服务端裁定，模型只负责措辞（用户 2026-09-22 的方向）：
- 每天在 TA 醒着的时间里随机挑几个时刻发（时刻按宠物与日期散开，可复现）；话多、黏人的性格发得多，安静独立的发得少；
- 发生了值得分享的事（例如半夜赶跑了来偷菜的）随时可以发，哪怕主人在睡觉——目前不推送，消息只是先留着；
- 爱熬夜的宠物（DNA 习惯里写了熬夜/夜猫子）夜里也可能冒出一句；
- 每天总数有上限（世界事件来信不计入）；主人刚在聊天（30 分钟内）或 TA 刚说过话（1 小时内）不插话；
- 主人关闭“TA 主动找我”或 7 天以上没来就不再发（不对空房间自言自语，也不产生模型费用）；
- 主人几天没来时，其中一条变成轻轻的“想起你了”：不责怪、不催促、不让主人内疚。

0.4.0 家庭：早安/分享/晚安/想你这些是和每位家人各自的私聊（按这位家人自己的偏好、时区和活跃情况，去重键带上家人编号）；
“新鲜事”（菜园守护、遇到朋友）发到家庭频道（user_id='*'），全家看到同一条，受家庭设置约束，每天上限另算。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from ..schemas.web.social import MessageComposer, MessageTopic
from ..web_communicator.persona import PetPersona, build_proactive, clean_reply, template_proactive
from ..web_communicator.service import FAMILY
from .moment import SLEEP_START, WAKE
from .profile import BehaviorProfile, derive_profile, profile_sources

DAILY_LIMIT = 6
INACTIVE_AFTER = timedelta(days=7)
MISSED_AFTER = timedelta(days=2)
OWNER_CHATTING = timedelta(minutes=30)
PET_JUST_SPOKE = timedelta(hours=1)
WINDOW = timedelta(hours=2)  # 随机时刻之后多久内还算“想到了”；过了就跳过，不补发


@dataclass(frozen=True)
class OwnerPrefs:
    pet_messages: bool
    timezone: str
    last_active_at: datetime | None


def _hash(*parts: object) -> int:
    return int(hashlib.sha1(":".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:8], 16)


def behavior(persona: PetPersona) -> BehaviorProfile:
    """没有装配统一画像（profile_of）时的后备：按扮演人设里的资料推导（与自主生活同一套规则）。"""
    return derive_profile(profile_sources(personality=persona.personality, dna=persona.dna, notes=persona.notes))


def pings_per_day(persona: PetPersona) -> int:
    return behavior(persona).chattiness


def night_owl(persona: PetPersona) -> bool:
    return behavior(persona).night_owl


def ping_times(pet_id: str, day: date, count: int, *, owl: bool = False, awake: tuple[time, time] | None = None) -> list[time]:
    """TA 在某一天（所在地当地）想找主人说话的时刻，落在 TA 醒着的时间里。
    awake＝(起床, 入睡)；不给时按默认作息 07:30–23:30，夜猫子延到凌晨 01:30。"""
    if awake is not None:
        start = awake[0].hour * 60 + awake[0].minute
        end = awake[1].hour * 60 + awake[1].minute
        end = end + 24 * 60 if end <= start else end
    else:
        start = WAKE.hour * 60 + WAKE.minute
        end = SLEEP_START.hour * 60 + SLEEP_START.minute + (120 if owl else 0)
    minutes = sorted(start + _hash(pet_id, day.isoformat(), "ping", i) % (end - start) for i in range(count))
    return [time((m // 60) % 24, m % 60) for m in minutes]


def dedupe_key(topic: MessageTopic, day: date, index: int | str, user_id: str | None = None) -> str:
    """私聊主动消息的去重键带上家人编号（同一只宠物给不同家人各发各的，UNIQUE(pet_id, source_event_id) 不会互相挡住）。"""
    return f"agent:{topic.value}:{day.isoformat()}:{index}" + (f"@{user_id}" if user_id else "")


class ProactiveMessenger:
    """communicator: WebCommunicatorService；moments: MomentBuilder；其余为装配时注入的回调。"""

    def __init__(self, communicator, moments, *, persona_of: Callable, prefs_of: Callable[[str], OwnerPrefs],
                 activated_pets: Callable[[], list[tuple[str, str]]], model_enabled: Callable[[str], bool]) -> None:
        self.communicator = communicator
        self.moments = moments
        self.persona_of = persona_of
        self.prefs_of = prefs_of
        self.activated_pets = activated_pets
        self.model_enabled = model_enabled
        # 统一的 DNA 行为画像（装配时注入，与作息、自主生活、DNA 页面展示同一份）
        self.profile_of: Callable[[str], BehaviorProfile] | None = None
        # 家庭频道：这只宠物的家庭是否允许发新鲜事、是否用模型措辞（家庭设置；装配时注入）
        self.family_allowed: Callable[[str], bool] = lambda pet_id: False
        self.family_model_enabled: Callable[[str], bool] = lambda pet_id: False

    def run(self, now: datetime) -> int:
        sent = 0
        for user_id, pet_id in self.activated_pets():
            if self.run_one(user_id, pet_id, now) is not None:
                sent += 1
        return sent

    # ---- 判断 ----
    def _allowed(self, user_id: str, pet_id: str, now: datetime, day_start: datetime) -> tuple[bool, set[str]]:
        prefs = self.prefs_of(user_id)
        if not prefs.pet_messages or prefs.last_active_at is None or now - prefs.last_active_at > INACTIVE_AFTER:
            return False, set()
        count, used, owner_last, pet_last = self.communicator.proactive_state(user_id, pet_id, day_start.astimezone(ZoneInfo("UTC")))
        if count >= DAILY_LIMIT:
            return False, used
        if (pet_last is not None and now - pet_last < PET_JUST_SPOKE) or (owner_last is not None and now - owner_last < OWNER_CHATTING):
            return False, used
        return True, used

    def due_ping(self, user_id: str, pet_id: str, now: datetime) -> tuple[MessageTopic, str] | None:
        """(话题, 去重键)；此刻没有该发的就返回 None。"""
        persona = self.persona_of(user_id, pet_id)
        if persona is None:
            return None
        moment = self.moments.build(pet_id, now)
        local = moment.local_time
        profile = self.profile_of(pet_id) if self.profile_of else behavior(persona)
        owl = profile.night_owl
        # 凌晨的夜猫子时刻属于前一天
        day = (local - timedelta(days=1)).date() if owl and local.time() < profile.wake else local.date()
        day_start = datetime.combine(day, time(0, 0), tzinfo=local.tzinfo)
        ok, used = self._allowed(user_id, pet_id, now, day_start)
        if not ok or (moment.asleep and not owl):
            return None
        times = ping_times(pet_id, day, profile.chattiness, awake=(profile.wake, profile.sleep_start))
        prefs = self.prefs_of(user_id)
        missed = prefs.last_active_at is not None and now - prefs.last_active_at > MISSED_AFTER
        for index, at_time in enumerate(times):
            at = datetime.combine(day, at_time, tzinfo=local.tzinfo)
            if at_time < profile.wake:
                at += timedelta(days=1)
            if not (at <= local < at + WINDOW):
                continue
            if missed and not any(k.startswith(f"agent:{MessageTopic.thinking_of_you.value}:{day.isoformat()}") for k in used):
                topic = MessageTopic.thinking_of_you
            elif index == 0 and local.time() < time(10, 30):
                topic = MessageTopic.morning
            elif index == len(times) - 1 and local.time() >= time(21, 0):
                topic = MessageTopic.goodnight
            else:
                topic = MessageTopic.share
            key = dedupe_key(topic, day, index, user_id)
            if not any(u.split("@", 1)[0].endswith(f":{day.isoformat()}:{index}") for u in used):
                return topic, key
        return None

    # ---- 发送 ----
    def _compose(self, user_id: str, pet_id: str, persona: PetPersona, topic: MessageTopic, now: datetime, seed: str, facts: str | None = None) -> tuple[str, str]:
        chat = self.communicator.chat
        enabled = self.family_model_enabled(pet_id) if user_id == FAMILY else self.model_enabled(user_id)
        if chat is not None and getattr(chat, "available", False) and enabled:
            try:
                messages = build_proactive(persona, self.communicator.recent_history(user_id, pet_id, now), topic.value)
                if facts:
                    messages[0]["content"] += f"\n刚刚真实发生的事（只说这件事，不添油加醋）：{facts}"
                text = clean_reply(chat.complete(messages, max_tokens=160, temperature=0.9).text)
                if text:
                    return text, MessageComposer.model.value
            except Exception:  # noqa: BLE001 - 模型不可用时用模板
                pass
        if facts:
            return f"{(persona.title + '，') if persona.title else ''}{facts}", MessageComposer.template.value
        return template_proactive(persona, topic.value, seed), MessageComposer.template.value

    def run_one(self, user_id: str, pet_id: str, now: datetime) -> MessageTopic | None:
        due = self.due_ping(user_id, pet_id, now)
        if due is None:
            return None
        topic, key = due
        persona = self.persona_of(user_id, pet_id)
        text, composed = self._compose(user_id, pet_id, persona, topic, now, key)
        posted = self.communicator.post_pet_message(user_id, pet_id, text, topic=topic, composed_by=composed, now=now, dedupe_key=key)
        return topic if posted else None

    def share_news(self, user_id: str, pet_id: str, now: datetime, event_key: str, facts: str) -> bool:
        """发生了值得分享的事就发（不看时段、家人睡没睡；受每日上限约束）。facts 为服务端认定的事实，模型只负责口吻。
        user_id='*'：发到家庭频道（全家一条，受家庭设置约束）；否则发给这位家人（受这位家人的偏好约束）。"""
        persona = self.persona_of(user_id, pet_id)
        if persona is None:
            return False
        local = self.moments.build(pet_id, now).local_time
        day_start = datetime.combine(local.date(), time(0, 0), tzinfo=local.tzinfo)
        if user_id == FAMILY:
            if not self.family_allowed(pet_id):
                return False
        elif not self.prefs_of(user_id).pet_messages:
            return False
        count, used, _, _ = self.communicator.proactive_state(user_id, pet_id, day_start.astimezone(ZoneInfo("UTC")))
        key = f"agent:news:{event_key}"
        if key in used or count >= DAILY_LIMIT:
            return False
        text, composed = self._compose(user_id, pet_id, persona, MessageTopic.news, now, key, facts=facts)
        return self.communicator.post_pet_message(user_id, pet_id, text, topic=MessageTopic.news, composed_by=composed, now=now, dedupe_key=key)
