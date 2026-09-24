"""TA 此刻在做什么：在家/睡着/在船上/在飞机上/在店里。回复时机、主动消息和模型扮演都读同一份快照。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from ..schemas.web.pets import PetPresence
from ..web_journey.trip_titles import going_to

HOME_TZ = "Asia/Hong_Kong"
SLEEP_START = time(23, 30)
WAKE = time(7, 30)
MODE_DOING = {"walk": "走路去{dest}", "taxi": "坐车去{dest}", "ferry": "在去{dest}的船上", "flight": "在飞往{dest}的飞机上", "train": "在去{dest}的火车上"}
MODE_WAITING = {"ferry": "在{at}等船", "flight": "在{at}等登机", "train": "在{at}等火车"}


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or HOME_TZ)
    except Exception:  # noqa: BLE001 - 未知时区按香港处理
        return ZoneInfo(HOME_TZ)


@dataclass(frozen=True)
class PetMoment:
    presence: PetPresence
    doing: str  # 用主人能懂的话描述此刻，例如“在去澳门码头的船上”
    place: str | None
    timezone: str
    local_time: datetime
    asleep: bool
    in_flight: bool
    leg_ends_at: datetime | None = None
    visit_ends_at: datetime | None = None
    journey_title: str | None = None
    wake: time = WAKE  # TA 自己的起床时间（DNA 作息）

    def next_wake(self) -> datetime:
        """TA 所在地下一次起床时间（UTC）。"""
        local = self.local_time
        wake = local.replace(hour=self.wake.hour, minute=self.wake.minute, second=0, microsecond=0)
        if local.time() >= self.wake:
            wake += timedelta(days=1)
        return wake.astimezone(ZoneInfo("UTC"))


def is_sleep_time(local: datetime, window: tuple[time, time] = (SLEEP_START, WAKE)) -> bool:
    """window＝(入睡, 起床)；入睡可以在午夜后（夜猫子 01:30 睡、09:30 起）。"""
    sleep, wake = window
    t = local.time()
    if sleep > wake:  # 跨午夜
        return t >= sleep or t < wake
    return sleep <= t < wake


class MomentBuilder:
    """用旅程数据拼出 TA 此刻的状态。journeys 为网页旅程服务（鸭子类型，避免引擎之间直接依赖）。"""

    def __init__(self, journeys, presence_of: Callable[[str], PetPresence], home_tz_of: Callable[[str], str] = lambda pet_id: HOME_TZ,
                 sleep_window_of: Callable[[str], tuple[time, time]] = lambda pet_id: (SLEEP_START, WAKE)) -> None:
        self.journeys = journeys
        self.presence_of = presence_of
        self.home_tz_of = home_tz_of
        self.sleep_window_of = sleep_window_of

    def build(self, pet_id: str, now: datetime) -> PetMoment:
        presence = self.presence_of(pet_id)
        journey = self.journeys.repo.active_for_pet(pet_id) if presence not in (PetPresence.at_home, PetPresence.not_activated) else None
        if journey is None:
            tz = self.home_tz_of(pet_id)
            local = now.astimezone(_zone(tz))
            window = self.sleep_window_of(pet_id)
            asleep = presence is PetPresence.at_home and is_sleep_time(local, window)
            planned = self.journeys.repo.active_for_pet(pet_id) if presence is PetPresence.at_home else None
            if planned is not None and now < planned.departed_at:  # 行程定好了，出门时间还没到（按开船时间反推）
                leave = planned.departed_at.astimezone(_zone(tz)).strftime("%H:%M")
                return PetMoment(presence, f"在家收拾东西，{leave} 出门去{going_to(planned.title)}", "家", tz, local, False, False, wake=window[1],
                                 journey_title=planned.title)
            return PetMoment(presence, "在家睡觉" if asleep else "在家", "家", tz, local, asleep, False, wake=window[1])
        visit = self.journeys.repo.visit_for_journey(journey.journey_id)
        if presence is PetPresence.visiting and visit is not None:
            tz = visit.place.get("timezone") or HOME_TZ
            return PetMoment(presence, f"在{visit.place['name']}坐着", visit.place["name"], tz, now.astimezone(_zone(tz)), False, False,
                             visit_ends_at=visit.ends_at, journey_title=journey.title)
        legs = self.journeys.repo.legs(journey.journey_id)
        leg = next((l for l in legs if l.starts_at <= now < l.ends_at), None)
        if leg is None:
            tz = HOME_TZ
            return PetMoment(presence, f"在去{going_to(journey.title)}的路上", None, tz, now.astimezone(_zone(tz)), False, False, journey_title=journey.title)
        tz = leg.origin.get("timezone") or HOME_TZ
        dest = leg.destination.get("name", "").replace("（示意）", "")
        at = leg.origin.get("name", "").replace("（示意）", "")
        if leg.kind == "wait":
            doing = MODE_WAITING.get(leg.mode, "在{at}等车").format(at=at)
        else:
            doing = MODE_DOING.get(leg.mode, "在去{dest}的路上").format(dest=dest)
        in_flight = leg.mode == "flight" and leg.kind == "main"
        return PetMoment(presence, doing, at if leg.kind == "wait" else None, tz, now.astimezone(_zone(tz)), False, in_flight,
                         leg_ends_at=leg.ends_at, journey_title=journey.title)
