"""宠物 DNA：主人描述并确认的性格、说话方式与小习惯。模型扮演宠物时读取它，让主人感到“就是 TA”。

- 主人没保存过时，按已有资料整理一份草稿（领养伙伴的性格与梦想、主人写的简介、接待时确认的称呼与心爱物件），
  草稿只作为起点，页面上标明“待你确认”；
- 保存时统一清洗：去空白、去重、截断过长条目，不做任何改写；
- shared_memories（和主人之间的小暗号、趣事）只用于私信，不进公开动态与生图。
- 0.4.0 家庭共同照顾：DNA 分两层——全家共用的一份（带版本号与修改记录，带着旧版本号保存会被拒绝，不会无声覆盖家人的修改），
  与每位家人各自的一份（TA 怎么称呼这位家人、和这位家人之间的小暗号），个人层只在和这位家人的私信里使用。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Callable

from ..schemas.web.pets import PetDNA
from ..storage import JourneyStorage
from ..utils import iso, parse_dt

ITEM_MAX = 40
MEMORY_MAX = 80
LIST_FIELDS = ("nicknames", "favorite_foods", "favorite_places", "hobbies", "habits", "fears", "shared_memories")
PERSONAL_FIELDS = ("owner_title", "shared_memories")  # 每位家人各自一份


def normalize(dna: PetDNA) -> PetDNA:
    data = dna.model_dump()
    for key in ("owner_title", "personality", "voice_style", "catchphrase"):
        value = (data.get(key) or "").strip()
        data[key] = value or None
    for key in LIST_FIELDS:
        limit = MEMORY_MAX if key == "shared_memories" else ITEM_MAX
        seen: list[str] = []
        for item in data.get(key) or []:
            text = " ".join(str(item).split())[:limit]
            if text and text not in seen:
                seen.append(text)
        data[key] = seen
    return PetDNA.model_validate(data)


@dataclass(frozen=True)
class DNARecord:
    dna: PetDNA
    confirmed: bool
    sources: list[str]
    updated_at: datetime | None
    version: int | None = None  # 共用部分的版本号（草稿为 None）
    updated_by: str | None = None


class DNAConflict(Exception):
    """带着旧版本号保存：家人在这之后改过共用 DNA。"""

    def __init__(self, current_version: int) -> None:
        super().__init__(f"dna version is {current_version}")
        self.current_version = current_version


def shared_part(dna: PetDNA) -> PetDNA:
    return dna.model_copy(update={"owner_title": None, "shared_memories": []})


def draft(*, personality: str | None, dream: str | None, bio: str | None, notes: list[tuple[str | None, str | None, str]]) -> DNARecord:
    """没有保存过 DNA 时的草稿：就是注册和接待时主人给的内容（领养资料、简介、确认过的叮嘱），不编造性格。

    notes: [(槽位, 槽位值, 原文)]，来自 MemoryPolicy(private_chat) 投影——都是主人确认过、允许 TA 在私信里用的。
    """
    sources: list[str] = []
    data: dict = {"favorite_places": [], "hobbies": [], "habits": []}
    if personality:
        data["personality"] = personality
        sources.append("adoption_profile")
    elif bio:
        data["personality"] = bio[:80]
        sources.append("owner_bio")
    if dream:
        data["favorite_places"].append(dream[:ITEM_MAX])
    for slot, value, text in notes:
        if slot == "owner_title" and value:
            data.setdefault("owner_title", value)
        elif slot == "favorite_object" and value:
            data["hobbies"].append(f"玩{value}"[:ITEM_MAX])
        elif slot == "wish_place" and value:
            data["favorite_places"].append(value[:ITEM_MAX])
        else:
            data["habits"].append(text[:ITEM_MAX])
    if notes:
        sources.append("reception_notes")
    return DNARecord(normalize(PetDNA.model_validate(data)), False, sources, None)


class PetDNAStore:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage
        # 没保存过时的草稿来源（装配时注入：领养资料、简介、这位家人确认过的接待叮嘱）
        self.draft_of: Callable[[str, str], DNARecord | None] = lambda user_id, pet_id: None

    def record(self, user_id: str, pet_id: str) -> DNARecord | None:
        """这位家人看到/私信里用的 DNA：共用部分 + 这位家人自己的称呼与小暗号。没保存过共用部分时是草稿。"""
        shared = self.saved(pet_id)
        if shared is None:
            return self.draft_of(user_id, pet_id)
        title, memories = self.personal(user_id, pet_id)
        return replace(shared, dna=shared.dna.model_copy(update={"owner_title": title, "shared_memories": memories}))

    def saved(self, pet_id: str) -> DNARecord | None:
        """全家共用的那一份（个人层字段为空）：行为画像、证件与公开内容只读这一份。"""
        with self.storage.connect() as conn:
            row = conn.execute("SELECT dna_json, confirmed_at, updated_at, version, updated_by FROM web_pet_dna WHERE pet_id = ?", (pet_id,)).fetchone()
        if row is None:
            return None
        dna = shared_part(PetDNA.model_validate(json.loads(row["dna_json"])))
        return DNARecord(dna, row["confirmed_at"] is not None, ["owner"], parse_dt(row["updated_at"]), int(row["version"]), row["updated_by"])

    def personal(self, user_id: str, pet_id: str) -> tuple[str | None, list[str]]:
        """(TA 怎么称呼这位家人, 和这位家人之间的小暗号)。称呼在家庭关系表里，与“关系与称呼”页面是同一份。"""
        with self.storage.connect() as conn:
            title = conn.execute("SELECT owner_title FROM web_pet_relationships WHERE pet_id = ? AND user_id = ?", (pet_id, user_id)).fetchone()
            row = conn.execute("SELECT shared_memories_json FROM web_pet_dna_personal WHERE pet_id = ? AND user_id = ?", (pet_id, user_id)).fetchone()
        return (title["owner_title"] if title else None), (list(json.loads(row["shared_memories_json"] or "[]")) if row else [])

    def save(self, user_id: str, pet_id: str, dna: PetDNA, now: datetime, expected_version: int | None = None) -> DNARecord:
        """保存（即确认）。共用部分：内容有变化才升版本并留下修改记录；expected_version 与当前不一致 → DNAConflict。
        个人部分（称呼、小暗号）只写这位家人自己的一份。"""
        clean = normalize(dna)
        shared_json = shared_part(clean).model_dump_json()
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT dna_json, version, confirmed_at FROM web_pet_dna WHERE pet_id = ?", (pet_id,)).fetchone()
            if row is not None and expected_version is not None and int(row["version"]) != expected_version:
                raise DNAConflict(int(row["version"]))
            if row is None:
                conn.execute("INSERT INTO web_pet_dna (pet_id, user_id, dna_json, confirmed_at, updated_at, version, updated_by) VALUES (?, ?, ?, ?, ?, 1, ?)",
                             (pet_id, user_id, shared_json, iso(now), iso(now), user_id))
                version = 1
            elif row["dna_json"] != shared_json or row["confirmed_at"] is None:
                version = int(row["version"]) + 1
                conn.execute("UPDATE web_pet_dna SET dna_json = ?, confirmed_at = ?, updated_at = ?, version = ?, updated_by = ? WHERE pet_id = ?",
                             (shared_json, iso(now), iso(now), version, user_id, pet_id))
            else:
                version = int(row["version"])
            conn.execute("INSERT OR IGNORE INTO web_pet_dna_history (pet_id, version, updated_by, dna_json, created_at) VALUES (?, ?, ?, ?, ?)",
                         (pet_id, version, user_id, shared_json, iso(now)))
            conn.execute(
                "INSERT INTO web_pet_dna_personal (pet_id, user_id, shared_memories_json, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(pet_id, user_id) DO UPDATE SET shared_memories_json = excluded.shared_memories_json, updated_at = excluded.updated_at",
                (pet_id, user_id, json.dumps(clean.shared_memories, ensure_ascii=False), iso(now)),
            )
            conn.execute(
                "INSERT INTO web_pet_relationships (pet_id, user_id, owner_title, relation_label, created_at, updated_at) VALUES (?, ?, ?, NULL, ?, ?) "
                "ON CONFLICT(pet_id, user_id) DO UPDATE SET owner_title = excluded.owner_title, updated_at = excluded.updated_at",
                (pet_id, user_id, clean.owner_title, iso(now), iso(now)),
            )
        return self.record(user_id, pet_id)  # type: ignore[return-value]
