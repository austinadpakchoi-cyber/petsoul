"""按 TA 此刻的真实状态决定何时回复主人（沿用旧 iOS 回复策略的思路，修掉“推迟后永远不回”的问题）。

- 主人情绪危机：立即回，并温和提示求助渠道；这是安全规则，不受意图层开关影响；
- 睡着：等到当地早上醒来；在飞机上：落地后；在路上/在店里：晚几分钟；在家醒着：很快；
- 推迟的消息都会排队，到点一定回复；同一段时间里的多条消息合并成一次回复；
- 不伪装“正在输入”，只给出等待说明（例如“TA 睡着啦，醒来会看到”）。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..schemas.web.pets import PetPresence
from .moment import PetMoment

COMPOSE_NOW_WITHIN = timedelta(minutes=5)

# 宁可多接住一次，也不漏掉；误判的代价只是多一句关心。不据此执行任何操作。
_DISTRESS = re.compile(
    r"(不想活|活不下去|活着没意思|想死|去死|自杀|轻生|结束(自己的)?生命|撑不下去|了结自己|割腕|跳楼|跳下去|安眠药|"
    r"去陪你|去找你|跟你一起走|随你而去|kill myself|suicide|end my life)",
    re.IGNORECASE,
)


def is_distress(text: str) -> bool:
    return bool(_DISTRESS.search(text or ""))


@dataclass(frozen=True)
class ReplyPlan:
    due_at: datetime
    reason: str  # distress / asleep / in_flight / on_the_way / visiting / at_home
    note: str | None  # 给主人的等待说明

    def compose_now(self, now: datetime) -> bool:
        return self.due_at - now <= COMPOSE_NOW_WITHIN


def _jitter(seed: str, low: int, high: int) -> int:
    digest = int(hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8], 16)
    return low + digest % max(1, high - low + 1)


def plan_reply(moment: PetMoment, now: datetime, *, distress: bool, seed: str) -> ReplyPlan:
    if distress:
        return ReplyPlan(now + timedelta(seconds=3), "distress", None)
    if moment.asleep:
        return ReplyPlan(moment.next_wake() + timedelta(minutes=_jitter(seed, 2, 25)), "asleep", "TA 睡着啦，醒来会看到。")
    if moment.in_flight and moment.leg_ends_at is not None:
        return ReplyPlan(moment.leg_ends_at + timedelta(minutes=_jitter(seed, 3, 10)), "in_flight", "TA 在飞机上，落地后会看到。")
    if moment.presence in (PetPresence.in_transit, PetPresence.returning):
        return ReplyPlan(now + timedelta(seconds=_jitter(seed, 90, 240)), "on_the_way", "TA 在路上，信号有点慢，会晚一点回。")
    if moment.presence is PetPresence.visiting:
        return ReplyPlan(now + timedelta(seconds=_jitter(seed, 45, 150)), "visiting", "TA 在店里，稍后回你。")
    return ReplyPlan(now + timedelta(seconds=_jitter(seed, 8, 20)), "at_home", None)
