"""TA 在外面遇到的朋友（用户 2026-09-22 的方向：宠物会遇到好朋友）。

- 真实账号的宠物：两只宠物同一时间在同一个地方（同一地点，或同城 300 米内）才算遇到；
  双方主人都开了公开动态（视为允许 TA 自主社交），而且互相没有拉黑；不能凭空说“我刚坐你旁边”；
- 星球居民（NPC）：明确标注是星球居民，不冒充真实玩家；到了店里、公园或城里，有一定几率认识一位；
- 关系会累积：见过几次、第一次和最近一次在哪；再遇到时 TA 会记得；
- 遇到后双方宠物都会主动告诉自己的主人（受每日主动消息上限约束）。
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from ..storage import JourneyStorage
from ..utils import iso, parse_dt

MEET_RADIUS_M = 300
RESIDENT_CHANCE = 0.35
SPECIES_CN = {"cat": "猫", "dog": "狗", "rabbit": "兔子", "hamster": "仓鼠", "bird": "小鸟", "parrot": "鹦鹉", "other": "小动物"}
# 场景模板 → 可能认识的星球居民 (id, 名字, 介绍)
RESIDENTS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "cafe": (("npc:parrot_lu", "鹦鹉阿绿", "咖啡馆的常客，爱学客人说话"), ("npc:cat_mocha", "老猫摩卡", "在店里打盹的星球居民")),
    "park": (("npc:turtle_man", "老乌龟慢慢", "每天在公园晒太阳的老居民"), ("npc:sparrow_qiu", "麻雀啾啾", "消息最灵通的小麻雀")),
    "generic": (("npc:pigeon_hui", "邮差鸽子小灰", "给整个星球送信的邮差"), ("npc:dog_wang", "导游犬旺旺", "带新来的朋友逛城的热心居民")),
}


def _roll(*parts: object) -> float:
    return int(hashlib.sha1(":".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:8], 16) / 0x100000000


def _distance_m(a: dict, b: dict) -> float:
    if a.get("lat") is None or b.get("lat") is None:
        return math.inf
    dlat = (a["lat"] - b["lat"]) * 111_320
    dlng = (a["lng"] - b["lng"]) * 111_320 * math.cos(math.radians(a["lat"]))
    return math.hypot(dlat, dlng)


def closeness(meet_count: int) -> str:
    return "好朋友" if meet_count >= 4 else ("熟人" if meet_count >= 2 else "初识")


@dataclass(frozen=True)
class Meeting:
    pet_id: str
    user_id: str
    friend_id: str
    friend_kind: str  # pet / resident
    friend_name: str
    place: str
    count: int


class FriendService:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage
        self.allowed_social: Callable[[str], bool] = lambda pet_id: False  # 这只宠物的家庭是否允许公开动态（视为允许 TA 自主社交）
        self.blocked_between: Callable[[str, str], bool] = lambda a, b: False
        self.pet_brief: Callable[[str], tuple[str, str] | None] = lambda pet_id: None  # (名字, 物种)
        self.on_meet: Callable[[Meeting, str, datetime, str], None] = lambda meeting, text, now, key: None
        self.roll: Callable[..., float] = _roll

    # ---- 世界事件：到了店里/公园/城里 ----
    def on_world_event(self, event) -> None:
        if event.kind != "visit_started" or event.visit is None:
            return
        met_real = self._meet_pets(event)
        if not met_real:
            self._meet_resident(event)

    def _claim(self, key: str, now: datetime) -> bool:
        with self.storage.connect() as conn:
            return conn.execute("INSERT OR IGNORE INTO web_pet_encounters (encounter_key, created_at) VALUES (?, ?)", (key, iso(now))).rowcount == 1

    def _befriend(self, pet_id: str, user_id: str, friend_id: str, kind: str, name: str, place: str, now: datetime) -> Meeting:
        with self.storage.connect() as conn:
            conn.execute(
                "INSERT INTO web_pet_friends (pet_id, user_id, friend_id, friend_kind, friend_name, first_met_at, last_met_at, meet_count, last_place, places_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?) ON CONFLICT(pet_id, friend_id) DO UPDATE SET last_met_at = excluded.last_met_at, "
                "meet_count = meet_count + 1, last_place = excluded.last_place, friend_name = excluded.friend_name",
                (pet_id, user_id, friend_id, kind, name, iso(now), iso(now), place, json.dumps([place], ensure_ascii=False)),
            )
            count = conn.execute("SELECT meet_count FROM web_pet_friends WHERE pet_id = ? AND friend_id = ?", (pet_id, friend_id)).fetchone()["meet_count"]
        return Meeting(pet_id, user_id, friend_id, kind, name, place, int(count))

    def _meet_pets(self, event) -> bool:
        journey, visit, now = event.journey, event.visit, event.occurred_at
        if not self.allowed_social(journey.pet_id):
            return False
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT visit_id, pet_id, user_id, place_json FROM web_visits WHERE pet_id != ? AND starts_at <= ? AND ends_at > ?",
                                (journey.pet_id, iso(now), iso(now))).fetchall()
        met = False
        for row in rows:
            other_place = json.loads(row["place_json"])
            same = other_place.get("place_id") == visit.place.get("place_id") or _distance_m(other_place, visit.place) <= MEET_RADIUS_M
            if not same or not self.allowed_social(row["pet_id"]) or self.blocked_between(journey.user_id, row["user_id"]):
                continue
            key = ":".join(sorted((visit.visit_id, row["visit_id"])))
            if not self._claim(key, now):
                continue
            mine, theirs = self.pet_brief(journey.pet_id), self.pet_brief(row["pet_id"])
            if mine is None or theirs is None:
                continue
            place = visit.place["name"]
            for me, my_user, friend, friend_brief in ((journey.pet_id, journey.user_id, row["pet_id"], theirs), (row["pet_id"], row["user_id"], journey.pet_id, mine)):
                meeting = self._befriend(me, my_user, friend, "pet", friend_brief[0], place, now)
                species = SPECIES_CN.get(friend_brief[1], "小动物")
                text = (f"又在{place}遇到{friend_brief[0]}啦！这是我们第 {meeting.count} 次见面了。" if meeting.count > 1
                        else f"今天在{place}遇到了一只{species}，叫{friend_brief[0]}，我们打了个招呼，聊了好一会儿。")
                self.on_meet(meeting, text, now, f"meet:{key}:{me}")
            met = True
        return met

    def _meet_resident(self, event) -> None:
        journey, visit, now = event.journey, event.visit, event.occurred_at
        residents = RESIDENTS.get(visit.template) or RESIDENTS["generic"]
        if self.roll(journey.journey_id, "resident") >= RESIDENT_CHANCE:
            return
        npc_id, name, intro = residents[int(self.roll(journey.journey_id, "which") * len(residents)) % len(residents)]
        if not self._claim(f"npc:{visit.visit_id}", now):
            return
        place = visit.place["name"]
        meeting = self._befriend(journey.pet_id, journey.user_id, npc_id, "resident", name, place, now)
        text = (f"在{place}又见到星球居民{name}了，它还记得我！" if meeting.count > 1
                else f"在{place}认识了一位星球居民：{name}，{intro}。")
        self.on_meet(meeting, text, now, f"meet:{npc_id}:{visit.visit_id}")

    # ---- 读取 ----
    def friends(self, user_id: str, pet_id: str) -> list[dict]:
        """这只宠物交到的朋友（属于宠物本身，全家成员看到的是同一份；调用方已检查成员关系）。"""
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT * FROM web_pet_friends WHERE pet_id = ? ORDER BY last_met_at DESC", (pet_id,)).fetchall()
        result = []
        for r in rows:
            species = None
            if r["friend_kind"] == "pet":
                brief = self.pet_brief(r["friend_id"])
                species = brief[1] if brief else None
            result.append({"friend_id": r["friend_id"], "kind": r["friend_kind"], "name": r["friend_name"], "species": species,
                           "meet_count": r["meet_count"], "closeness": closeness(r["meet_count"]), "first_met_at": parse_dt(r["first_met_at"]),
                           "last_met_at": parse_dt(r["last_met_at"]), "last_place": r["last_place"]})
        return result
