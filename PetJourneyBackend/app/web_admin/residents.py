"""待领养居民名单（方案 §3「游戏内容：原创居民」的运营视图）。只读。

一只居民＝驿站里的一只宠物（`web_residents`）＋ 它的领养档案（`web_adoption_candidates`）＋ 它住的驿站（`web_residences`）。
性格、梦想、来源说明是内容侧发布的公开档案（玩家在领养页就看得到），这里照样给；被谁领养只给家与账号的编号和名字。
居民的档案怎么改走「内容发布」（居民类型），这里不改任何东西。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from ..storage import JourneyStorage
from ..utils import parse_dt
from .resident_listing import DELIST_EFFECTS, RELIST_EFFECTS
from .social import people


def _dt(value: str | None) -> datetime | None:
    return parse_dt(value) if value else None


class AdminResidents:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage

    def list(self) -> dict[str, Any]:
        with self.storage.connect() as conn:
            try:
                rows = conn.execute(
                    "SELECT r.pet_id, r.candidate_id, r.kind, r.status, r.public_since, r.adopted_at, r.adopted_household_id, r.adopted_by, "
                    "c.name, c.species, c.personality, c.dream, c.origin, c.source_note, c.availability, c.listed, "
                    "s.city, s.label AS residence_label "
                    "FROM web_residents r LEFT JOIN web_adoption_candidates c ON c.candidate_id = r.candidate_id "
                    "LEFT JOIN web_residences s ON s.residence_id = r.residence_id ORDER BY r.status, s.city, c.name").fetchall()
            except sqlite3.OperationalError:
                return {"residents": None, "note": "这个库里还没有居民记录，查不了（不等于没有）。"}
            adopters = people(conn, [r["adopted_by"] for r in rows])
            # 这位居民在「内容发布」里有没有已建的文案内容：居民页的「编辑档案」直接去那一条（一种内容一个条目只能有一条）
            try:
                content = {r["slug"]: r for r in conn.execute("SELECT item_id, slug, status, live_revision, draft_revision FROM admin_content_items "
                                                                 "WHERE content_type = 'resident'")}
            except sqlite3.OperationalError:
                content = {}
            homes = {r["household_id"]: r["home_id"] for r in conn.execute("SELECT household_id, home_id FROM web_homes WHERE household_id IS NOT NULL")}
            # 最近一次撤下 / 放回的后台依据（谁、什么时候、为什么、第几版）；表还不在就当没有记录
            try:
                listing = {r["candidate_id"]: r for r in conn.execute("SELECT * FROM admin_resident_listing")}
            except sqlite3.OperationalError:
                listing = {}
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        return {
            "counts": counts,
            "residents": [{
                "pet_id": r["pet_id"], "candidate_id": r["candidate_id"], "name": r["name"], "species": r["species"],
                "kind": r["kind"], "status": r["status"], "availability": r["availability"], "origin": r["origin"],
                "city": r["city"], "residence_label": r["residence_label"],
                "personality": r["personality"], "dream": r["dream"], "source_note": r["source_note"],
                "public_since": _dt(r["public_since"]), "adopted_at": _dt(r["adopted_at"]),
                "adopted_by": r["adopted_by"], "adopted_by_name": adopters.get(r["adopted_by"]),
                "adopted_household_id": r["adopted_household_id"], "adopted_home_id": homes.get(r["adopted_household_id"]),
                "content_item": ({"item_id": content[r["candidate_id"]]["item_id"], "status": content[r["candidate_id"]]["status"],
                                  "live_revision": content[r["candidate_id"]]["live_revision"],
                                  "draft_revision": content[r["candidate_id"]]["draft_revision"]}
                                 if r["candidate_id"] in content else None),
                # 是否在领养名单上（领养卡表的上架列，迁移 0260）；撤下只对还可以领养的居民生效
                "listed": bool(r["listed"]) if r["listed"] is not None else None,
                "listing": ({"reason": listing[r["candidate_id"]]["reason"], "changed_by": listing[r["candidate_id"]]["changed_by"],
                             "changed_at": _dt(listing[r["candidate_id"]]["changed_at"]), "version": int(listing[r["candidate_id"]]["version"])}
                            if r["candidate_id"] in listing else None),
            } for r in rows],
            "listing_effects": {"delist": list(DELIST_EFFECTS), "relist": list(RELIST_EFFECTS)},
            "note": "居民的档案（性格、梦想、来源说明）是玩家在领养页也看得到的公开内容；要改它走「内容发布」里的居民类型。",
        }
