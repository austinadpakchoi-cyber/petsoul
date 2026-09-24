"""待领养居民（用户 2026-09-22 的决定，数据见迁移 0240）。

- 还没被领养的伙伴已经是一只有稳定 pet_id 的宠物，住在星球居民驿站（世界规则：驿站提供食宿；不编造人类主人），
  会自己在附近走走、去打工攒钱；它的生活本来就是公开的（访客不登录也能看到），但没有家庭频道、没有私聊、不会调用模型或生图；
- 领养只改变归属：同一个事务里把它从驿站名单转进新家庭（pet_id、性格、钱包、证件与公开经历都保留）；
- 领养时它若正在外面，不会瞬移——等它回到驿站，新家人再为它办入住（从驿站搬进新家，记下 moved_home_at）。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from ..storage import JourneyStorage
from ..utils import iso, parse_dt

SYSTEM_USER = "sys-planet-residents"  # 居民的建档身份（没有网页账号，不能登录）


@dataclass(frozen=True)
class ResidentHome:
    """居民的“家”＝它住的驿站（给自主生活用：出门从这里出发，回到这里）。"""

    home_id: str
    activated_at: datetime | None = None


class ResidentService:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage

    # ---- 读取 ----
    def residence_of(self, pet_id: str) -> str | None:
        """还住在驿站的居民 → 驿站编号；已被领养或不是居民 → None。"""
        with self.storage.connect() as conn:
            row = conn.execute("SELECT residence_id FROM web_residents WHERE pet_id = ? AND status = 'resident'", (pet_id,)).fetchone()
        return row["residence_id"] if row else None

    def home_of(self, pet_id: str) -> ResidentHome | None:
        residence = self.residence_of(pet_id)
        return ResidentHome(residence) if residence else None

    def living(self) -> list[str]:
        """还在驿站生活的居民（按开始公开生活的先后）。"""
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT pet_id FROM web_residents WHERE status = 'resident' ORDER BY public_since, pet_id").fetchall()
        return [r["pet_id"] for r in rows]

    def timezone_of(self, pet_id: str) -> str | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT s.timezone FROM web_residents r JOIN web_residences s ON s.residence_id = r.residence_id WHERE r.pet_id = ?",
                               (pet_id,)).fetchone()
        return row["timezone"] if row else None

    def public_list(self) -> list[dict]:
        """访客页：还可以领养的居民（名字、物种、性格、梦想、住在哪、从什么时候开始在星球上生活）。不含任何家庭信息。"""
        with self.storage.connect() as conn:
            rows = conn.execute(
                "SELECT r.pet_id, r.candidate_id, r.public_since, s.label AS residence, s.city, c.name, c.species, c.personality, c.dream, c.origin, c.source_note "
                "FROM web_residents r JOIN web_residences s ON s.residence_id = r.residence_id "
                "JOIN web_adoption_candidates c ON c.candidate_id = r.candidate_id "
                "WHERE r.status = 'resident' AND r.kind = 'adoptable' AND c.availability = 'available' AND c.listed = 1 "  # 后台撤下的不上访客页（迁移 0260）
                "ORDER BY r.public_since, r.pet_id").fetchall()
        return [{"pet_id": r["pet_id"], "candidate_id": r["candidate_id"], "name": r["name"], "species": r["species"], "personality": r["personality"],
                 "dream": r["dream"], "origin": r["origin"], "source_note": r["source_note"], "residence": r["residence"], "city": r["city"],
                 "living_since": parse_dt(r["public_since"])} for r in rows]

    def public_row(self, pet_id: str) -> dict | None:
        return next((r for r in self.public_list() if r["pet_id"] == pet_id), None)

    # ---- 领养与搬家 ----
    def on_adopted(self, conn: sqlite3.Connection, pet_id: str, household_id: str, user_id: str, now: datetime) -> None:
        """在领养的同一个事务里调用：从驿站名单转进新家庭。身份、钱包、证件与公开经历都不动。"""
        conn.execute("UPDATE web_residents SET status = 'adopted', adopted_at = ?, adopted_household_id = ?, adopted_by = ? WHERE pet_id = ? AND status = 'resident'",
                     (iso(now), household_id, user_id, pet_id))

    def moved_home(self, pet_id: str, now: datetime) -> None:
        """领养后第一次住进新家（从驿站搬过去）。不是居民时什么也不做。"""
        with self.storage.connect() as conn:
            conn.execute("UPDATE web_residents SET moved_home_at = ? WHERE pet_id = ? AND status = 'adopted' AND moved_home_at IS NULL", (iso(now), pet_id))
