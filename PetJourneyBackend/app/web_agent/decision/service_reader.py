"""ContextReader 的服务实现：只调用现有网页服务的读取方法（不写库），按 life_plan 的受众给出最小资料。

语义版本（Versions）不在这里拼：由集成窗口注入 versions_of(pet_id)，按 runtime-internal 的定义从可信存储投影。
每个方法先按受众取资料（家庭成员关系、接待记忆的 (家人, 宠物) 投影、居民驿站），决策包还会再按受众、用途与模型许可核一遍。

- shared_dna 用给全家的草稿（draft_of(None, …)），不会带出某位家人的私信叮嘱；
- memory_items 逐位家人取 reception.projection(家人, 宠物, 用途)，每条标成这位家人私有，model_ok 取这位家人的“模型回信”开关；
- observations 用生活时间线，但 user_id 传空串：不是任何家人，所以不会带出某位家人自己的“一起听歌”回忆；
- commitments 只给合并后的信号：24 小时内还在考虑的建议、有人说过“今天别出门”，不带原话，也不指明是谁。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ...schemas.runtime_internal import ActivityRef, AudienceScope, Versions
from ...schemas.web.reception import MemoryPurpose
from ..timeline import timeline
from .ports import DnaSnapshot, PetBrief, Record
from .projections import dna_snapshot

PRESENCE_KIND = {"at_home": "at_home", "in_transit": "travel", "returning": "travel", "at_destination": "visit", "visiting": "visit",
                 "not_activated": "not_activated"}
# 叮嘱按种类标注：还没发生的心愿不能被读成已经发生的事（过去的事实另有发生时间，在观察一栏）
NOTE_LABEL = {"habit": "小习惯", "wish": "愿望（还没发生）", "shared_story": "主人讲过的往事", "letter": "主人写给它的话"}
SUGGESTION_HOURS, STAY_HOME_HOURS = 24, 12


class ServiceContextReader:
    """web：WebServices（household / pets / dna / reception / identity / life / communicator / moments / journeys / economy / residents）。"""

    def __init__(self, web, *, versions_of: Callable[[str], Versions], now: Callable[[], datetime],
                 activity_of: Callable[[str, datetime], ActivityRef | None] | None = None,
                 timezone_of: Callable[[str, datetime], str | None] | None = None) -> None:
        self.web = web
        self.versions_of = versions_of
        self.now = now
        # 集成窗口可以把每宠运行投影的主活动与时区传进来（与心跳同一个来源），不传就按下面的默认推。
        self.activity_of = activity_of
        # 默认只认生活基地（家或驿站）的时区；TA 在外地时那不是所在地时区，所以正式装配请注入投影的 state(...).timezone
        self.timezone_of = timezone_of

    def versions(self, pet_id: str) -> Versions:
        return self.versions_of(pet_id)

    def audience_valid(self, pet_id: str, audience: AudienceScope) -> bool:
        if audience.kind == "household":
            return self.web.households.household_of_pet(pet_id) == audience.household_id
        return audience.kind == "public" and self.web.residents.residence_of(pet_id) is not None

    def pet_brief(self, pet_id: str) -> PetBrief | None:
        record = self.web.pets.profile(pet_id)
        return PetBrief(record.name, record.species.value) if record else None

    def shared_dna(self, pet_id: str) -> DnaSnapshot | None:
        return dna_snapshot(self.web.dna.saved(pet_id) or self.web.dna.draft_of(None, pet_id))

    def memory_items(self, pet_id: str, audience: AudienceScope, purposes: Sequence[str], limit: int) -> Sequence[Record]:
        if audience.kind != "household":
            return []
        found: dict[str, Record] = {}
        for user_id in self.web.households.member_ids(audience.household_id):
            model_ok = bool(self.web.identity.prefs(user_id)["model_replies"])
            scope = AudienceScope("private", household_id=audience.household_id, user_id=user_id)
            for purpose in purposes:
                for item in self.web.reception.projection(user_id, pet_id, MemoryPurpose(purpose)).items:
                    ref = f"note:{item.note_id}@{item.note_version}"
                    earlier = found.get(ref)
                    kind = item.kind.value
                    text = f"{NOTE_LABEL[kind]}：{item.text}" if kind in NOTE_LABEL else item.text
                    found[ref] = Record(ref, "owner_report", text, scope, kind, (earlier.purposes if earlier else ()) + (purpose,), model_ok)
        return list(found.values())[:limit]

    def observations(self, pet_id: str, audience: AudienceScope, limit: int) -> Sequence[Record]:
        items = timeline(self.web.dna.storage, "", pet_id, limit=limit)
        return [Record(f"{i['kind']}:{i['ref_id'] or i['at'].isoformat()}", "world_event", i["title"] + (f"（{i['detail']}）" if i["detail"] else ""),
                       audience, i["kind"], observed_at=i["at"]) for i in items if i["kind"] != "shared_memory"]

    def commitments(self, pet_id: str, audience: AudienceScope, limit: int) -> Sequence[Record]:
        if audience.kind != "household":
            return []
        now = self.now()
        found: dict[str, Record] = {}
        for user_id in self.web.households.member_ids(audience.household_id):
            for s in self.web.life.recent_suggestions(user_id, pet_id):
                if s["status"] == "pending" and s["created_at"] >= now - timedelta(hours=SUGGESTION_HOURS):
                    ref = f"suggestion:{s['destination_key']}"
                    found.setdefault(ref, Record(ref, "owner_report", f"有家人建议：{s['title']}", audience, "suggestion",
                                                 deadline_at=s["created_at"] + timedelta(hours=SUGGESTION_HOURS)))
        if self.web.communicator.owner_asked_stay_home("", pet_id, now - timedelta(hours=STAY_HOME_HOURS)):
            found["signal:stay_home"] = Record("signal:stay_home", "owner_report", "家人希望你今天在家歇着", audience, "stay_home")
        return list(found.values())[:limit]

    def activity(self, pet_id: str, now: datetime) -> ActivityRef | None:
        if self.activity_of is not None:
            return self.activity_of(pet_id, now)
        moment = self.web.moments.build(pet_id, now)
        kind = PRESENCE_KIND.get(moment.presence.value, "unknown")
        if kind == "at_home":
            return ActivityRef("at_home", None)
        journey = self.web.journeys.repo.active_for_pet(pet_id)
        return ActivityRef(kind, f"journey:{journey.journey_id}" if journey else None, journey.departed_at if journey else None,
                           moment.leg_ends_at or moment.visit_ends_at, interruptible=False)

    def local_time(self, pet_id: str, now: datetime) -> datetime | None:
        """TA 所在地的当地钟点；时区认不出就返回 None，不套用某个默认城市。

        注入了 timezone_of（运行投影：店里 → 这段交通的起点 → 生活基地）就用它；没注入时只认生活基地的时区，
        TA 在外地时会偏成家里的钟点——正式装配请注入，别用默认。
        """
        zone = self.timezone_of(pet_id, now) if self.timezone_of is not None else self._base_timezone(pet_id)
        if not zone:
            return None
        try:
            return now.astimezone(ZoneInfo(zone))
        except Exception:  # noqa: BLE001 - 时区名认不出：当作未知，不编一个时间
            return None

    def _base_timezone(self, pet_id: str) -> str | None:
        residence = self.web.residents.residence_of(pet_id) if self.web.residents is not None else None
        if residence is None:
            home = self.web.homes.by_pet(pet_id)
            if home is None:
                return None
            residence = home.home_id
        try:
            return getattr(self.web.home_places.get(residence), "timezone", None)
        except Exception:  # noqa: BLE001 - 取不到就当作未知，由心跳给出明确的不可用结果
            return None

    def wallet_balance(self, pet_id: str) -> int | None:
        return self.web.economy.wallet(pet_id).balance
