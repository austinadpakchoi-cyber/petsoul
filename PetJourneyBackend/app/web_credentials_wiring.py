"""证件卡包与驾考的装配（组合根的一部分，由 web_composition 调用；可以 import 任何模块）。

- 证件：身份卡 / 银行卡 / 照护档案随入住签发；护照、登机牌、船票车票随真实成立的行程签发（旅程世界事件 sink）；
- 爪爪驾校：愿望 → 报名 → 主人陪练、陪考（四科）→ 四科齐全时在同一事务里签发驾驶证与借车券 → 解锁自驾；
  TA 自己会产生愿望、自己报名并邀请主人陪练，但不会自己去考；定时器补投驾考消息、作废没开始的考局、在冷却结束时提醒；
- 签证、拿证等消息来自实际签发事件，按证件号去重。
- 0.4.0 家庭：证件属于宠物；签发与驾校的消息发到家庭频道（全家都看得到）；身份卡的签发时间是这只宠物自己住进来的时间；
  驾考陪练、陪考的是某位家人，但驾校进度与驾照是这只宠物的。
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from dataclasses import dataclass
from types import SimpleNamespace
from datetime import datetime, timedelta
from typing import Callable

from .schemas.web.reception import MemoryPurpose
from .utils import iso, parse_dt
from .web_credentials import CredentialService
from .web_driving import DrivingService

logger = logging.getLogger(__name__)

ANNOUNCE = {  # 拿驾照的消息由驾考模块和考试结果一起登记（web_driving.notes），不在这里发
    # 「星球居民证」是用户 2026-09-24 定的叫法（原「星球身份证」）。
    # **这处没有改成读 `CATALOG.label`**：它是一句完整的话、名字嵌在句中，抽成模板要改调用处，
    # 收益不抵改动面。**代价是它仍然是第二处名字**——改名时要记得连它一起改，
    # 而 `timeline.py` 那条注释里列了这个坑。
    "identity_card": "我的星球居民证办好啦，编号 {number}！以后我就是星球上正式的居民了。",
    "passport": "我领到护照啦，编号 {number}！第一次出远门，就去{title}。",
}


@dataclass
class DocumentWorld:
    credentials: CredentialService
    driving: DrivingService
    tick: Callable[[datetime], int]


def wire_documents(*, storage, pets, homes, economy, journeys, registry, dna_store, reception, communicator, moments, profile_of, collection, illustrations,
                   activated_pets: Callable[[], list[tuple[str, str]]], households) -> DocumentWorld:
    credentials = CredentialService(storage)

    def moved_in_home(pet_id: str):
        """证件用的“入住”：这只宠物住进家的那一刻（家庭里后加的宠物按它自己的入住时间）。还没住进来 → None。"""
        home = homes.by_pet(pet_id)
        row = households.onboarding_row(pet_id)
        if home is None or home.activated_at is None or row is None or not row["moved_in_at"]:
            return None
        return SimpleNamespace(home_id=home.home_id, activated_at=parse_dt(row["moved_in_at"]))

    credentials.home_of = moved_in_home
    credentials.legs_of = journeys.repo.legs

    def service_of(world_service_id):
        service = registry.by_id(world_service_id) if world_service_id else None
        return (service.carrier_name, service.service_code) if service else None

    credentials.service_of = service_of

    def on_issued(user_id: str, pet_id: str, kind: str, row: dict, announce: bool) -> None:
        text = ANNOUNCE.get(kind)
        if announce and text:
            title = next((link["title"] for link in row["links"] if link.get("kind") == "journey"), "外面")
            communicator.post_family_note(pet_id, text.format(number=row["number"], title=title), dedupe_key=f"credential:{row['credential_id']}",
                                          now=row["issued_at"])

    credentials.on_issued = on_issued
    journeys.add_consumer("credentials", credentials)

    # ---- 爪爪驾校 ----
    driving = DrivingService(storage)
    driving.license_in = credentials.license_in
    driving.profile_of = profile_of
    driving.say = lambda user_id, pet_id, text, key, now: communicator.post_family_note(pet_id, text, dedupe_key=key, now=now)

    def issue_license(conn: sqlite3.Connection, user_id: str, pet_id: str, source_id: str, issued_at: datetime, data: dict) -> dict:
        """在结算的同一事务里签发；已经有驾驶证就返回原来那本（一只宠物一本 C 照，重试不重复发证）。"""
        existing = credentials.license_in(conn, pet_id)
        if existing is not None:
            return existing
        title = "PetSoul · 爪爪驾驶证 · 小型车（C）"
        link_title = "旧版驾考通过" if data.get("legacy") else "爪爪驾校四科全部通过"
        row, _ = credentials.insert(conn, user_id=user_id, pet_id=pet_id, kind="driver_license", source_key="driver_license:C", issued_at=issued_at, title=title,
                                    data={**data, "source": source_id}, links=[{"kind": "exam", "ref_id": source_id, "title": link_title, "at": iso(issued_at)}])
        return row

    def grant_item(conn: sqlite3.Connection, user_id: str, pet_id: str, kind: str, title: str, note: str, source: str, now: datetime) -> None:
        collection.keepsake(conn, user_id=user_id, pet_id=pet_id, kind=kind, title=title, note=note, source_event_id=source, now=now)

    def memento_photo(user_id: str, pet_id: str, source: str) -> str | None:
        """领证合影：只有主人开启“生成照片”且配置了生图时才请求写实照片；否则是纸质纪念卡。"""
        home = homes.by_pet(pet_id)
        city = homes.place_of(home.home_id).city if home is not None and homes.place_of else "星球"
        task_id = illustrations.request_photo(user_id, pet_id, f"license_photo:{source}", place="爪爪驾校门口", city=city,
                                              scene="刚拿到驾照，站在驾校门口，爪子里捧着新领的驾照，旁边是一只慢吞吞的老乌龟教练")
        if task_id:
            collection.attach_image(pet_id, "license_photo", source, task_id)
        return task_id

    driving.issue_license = issue_license
    driving.grant_item = grant_item
    driving.voucher_of = lambda pet_id: collection.has(pet_id, "car_voucher")
    driving.memento_photo = memento_photo
    journeys.can_drive = lambda pet_id: credentials.license_of(pet_id) is not None
    journeys.waiver_available = lambda pet_id, key: key == "local:drive_trip" and collection.has(pet_id, "car_voucher")
    journeys.fee_waiver = lambda pet_id, key: key == "local:drive_trip" and collection.consume(pet_id, "car_voucher")
    # 借车券的核销要和行程、扣费在**同一个事务**里（C 的 CR-C9-b，A 的 consume_in）：
    # 两段写会留下"券用了、行程没建"或反过来，幂等键能防"扣两次"，防不了"根本没扣"。
    journeys.fee_waiver_in = lambda conn, pet_id, key: key == "local:drive_trip" and collection.consume_in(conn, pet_id, "car_voucher")

    def wish_text(pet_id: str) -> str:
        dna = dna_store.saved(pet_id)
        place = (dna.dna.favorite_places[0] if dna and dna.dna.favorite_places else None) or "远一点的地方"
        return f"坐车的时候我一直盯着司机看……我也想学开车，以后换我开车载你去{place}！"

    def tick_pet(user_id: str, pet_id: str, now: datetime) -> int:
        """TA 自己的学车节奏：可能产生学车愿望；有了愿望一天后自己报名并邀请主人陪练。考试由主人陪着完成，TA 不会自己去考。"""
        acted = int(driving.reconcile(pet_id, now))  # 系统补签（旧版“已通过未签发”），睡着也照常
        moment = moments.build(pet_id, now)
        if moment.asleep:
            return acted
        stage = driving.stage(pet_id)
        profile = profile_of(pet_id)
        day = moment.local_time.date().isoformat()
        if stage == "none":
            chance = 0.3 if (profile.curious or profile.sociability == "social") else 0.1
            roll = int(hashlib.sha1(f"{pet_id}:{day}:wish".encode()).hexdigest()[:8], 16) / 0x100000000
            taxi_rides = [k for k, _ in _history(journeys, pet_id) if k == "local:city_trip"]
            if (taxi_rides or profile.curious) and roll < chance and driving.wish(user_id, pet_id, wish_text(pet_id), now):
                acted += 1
        elif stage == "wish":
            row = driving._row(pet_id)
            if row and row["wish_at"] and now - parse_dt(row["wish_at"]) >= timedelta(hours=24):
                driving.enroll(user_id, pet_id, now, by_owner=False)
                acted += 1
        return acted

    def tick(now: datetime) -> int:
        acted = driving.notes.deliver() + driving.housekeeping(now)  # 补投驾考消息；作废没开始的考局；冷却结束的提醒
        for user_id, pet_id in activated_pets():
            try:
                acted += tick_pet(user_id, pet_id, now)
            except Exception:  # noqa: BLE001 - 一只宠物出错不影响其他宠物，下一轮再试
                logger.exception("driving tick failed pet=%s", pet_id)
        return acted

    return DocumentWorld(credentials=credentials, driving=driving, tick=tick)


def _history(journeys, pet_id: str) -> list[tuple[str, datetime]]:
    with journeys.storage.connect() as conn:
        rows = conn.execute("SELECT destination_key, departed_at FROM web_journeys WHERE pet_id = ? ORDER BY departed_at DESC LIMIT 20", (pet_id,)).fetchall()
    return [(r["destination_key"], parse_dt(r["departed_at"])) for r in rows]


def care_notes(dna_store, reception, user_id: str, pet_id: str) -> list[str]:
    """照护档案：主人确认过的习惯、怕什么、爱吃的、安抚方式与叮嘱（私密，只给主人）。"""
    notes: list[str] = []
    record = dna_store.record(user_id, pet_id)
    if record is not None:
        dna = record.dna
        notes += [f"习惯：{h}" for h in dna.habits] + [f"怕：{f}" for f in dna.fears] + [f"爱吃：{f}" for f in dna.favorite_foods]
    notes += [f"叮嘱：{i.text}" for i in reception.projection(user_id, pet_id, MemoryPurpose.private_chat).items]
    return list(dict.fromkeys(notes))
