"""0240：待领养居民真实生活在星球上（用户 2026-09-22 的新决定）。

- 每位还没被领养的伙伴从现在起就是一只有稳定 pet_id 的宠物：有外貌（物种）、性格、住处、钱包、行程与公开经历；
  领养只改变归属，不重建身份、不换性格、不丢弃领养前的公开经历。
- 没有家庭的居民住在“星球居民驿站”（世界规则：驿站提供食宿与照顾，居民可以打工攒钱、在附近走走），不编造人类主人；
  驿站只在已支持的城市（香港）设立，位置是片区里的概念地点，不对应真实门牌。
- 居民的建档身份是系统保留的“星球居民驿站”（users 里的一行，没有网页账号、不能登录，不是任何真实用户）；
  归属只看 web_household_pets：居民不在任何家庭里。
- 原创伙伴（adopted_original）、已核验真实原型（adopted_real_archive）与不可领养的公共 NPC（kind=public_npc）分开标注。
"""

from __future__ import annotations

import hashlib
import sqlite3

from . import WebMigration

SYSTEM_USER = "sys-planet-residents"
RESIDENCES = [
    # residence_id, city, area_key, 名字, 纬度, 经度, 时区（与 web_home.place 的片区中心一致；概念地点，不是门牌）
    ("res-hk-central", "香港", "hk_central", "星球居民驿站·中环", 22.2819, 114.1581, "Asia/Hong_Kong"),
    ("res-hk-saikung", "香港", "hk_saikung", "星球居民驿站·西贡海边", 22.3818, 114.2719, "Asia/Hong_Kong"),
]
SEASIDE_WORDS = ("海", "灯塔", "船", "日出")


def resident_pet_id(candidate_id: str) -> str:
    return "PJ-" + hashlib.sha1(f"resident:{candidate_id}".encode("utf-8")).hexdigest()[:8].upper()


def _apply(conn: sqlite3.Connection) -> None:
    now = conn.execute("SELECT strftime('%Y-%m-%dT%H:%M:%SZ', 'now') AS t").fetchone()["t"]
    conn.execute(
        """
        CREATE TABLE web_system_users (
            user_id TEXT PRIMARY KEY REFERENCES users(user_id),
            purpose TEXT NOT NULL,
            note TEXT
        )
        """
    )
    conn.execute("INSERT OR IGNORE INTO users (user_id, apple_sub, email, display_name, created_at) VALUES (?, NULL, NULL, ?, ?)",
                 (SYSTEM_USER, "星球居民驿站（系统）", now))
    conn.execute("INSERT OR IGNORE INTO web_system_users (user_id, purpose, note) VALUES (?, 'resident_records', ?)",
                 (SYSTEM_USER, "待领养居民的建档身份；没有网页账号，不能登录，不属于任何真实用户"))
    conn.execute(
        """
        CREATE TABLE web_residences (
            residence_id TEXT PRIMARY KEY,
            city TEXT NOT NULL,
            area_key TEXT NOT NULL,
            label TEXT NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            timezone TEXT NOT NULL
        )
        """
    )
    for residence in RESIDENCES:
        conn.execute("INSERT INTO web_residences (residence_id, city, area_key, label, lat, lng, timezone) VALUES (?, ?, ?, ?, ?, ?, ?)", residence)
    conn.execute(
        """
        CREATE TABLE web_residents (
            pet_id TEXT PRIMARY KEY REFERENCES pets(pet_id) ON DELETE CASCADE,
            candidate_id TEXT UNIQUE,
            residence_id TEXT NOT NULL REFERENCES web_residences(residence_id),
            kind TEXT NOT NULL CHECK (kind IN ('adoptable', 'public_npc')),
            status TEXT NOT NULL CHECK (status IN ('resident', 'adopted')),
            public_since TEXT NOT NULL,
            adopted_at TEXT,
            adopted_household_id TEXT,
            adopted_by TEXT,
            moved_home_at TEXT,
            move_journey_id TEXT
        )
        """
    )
    conn.execute("CREATE INDEX idx_web_residents_status ON web_residents (status, residence_id)")
    rows = conn.execute("SELECT * FROM web_adoption_candidates WHERE availability = 'available' AND adopted_pet_id IS NULL ORDER BY created_at, candidate_id").fetchall()
    for row in rows:
        pet_id = resident_pet_id(row["candidate_id"])
        species = row["species"]
        pet_type = species if species in {"dog", "cat", "parrot", "rabbit", "hamster", "bird", "other"} else "other"
        conn.execute("INSERT INTO pets (pet_id, name, pet_type, dna_json, created_at, photo_path, owner_user_id) VALUES (?, ?, ?, '{}', ?, NULL, NULL)",
                     (pet_id, row["name"], pet_type, now))
        conn.execute(
            "INSERT INTO web_pet_profiles (pet_id, user_id, origin, candidate_id, species, photo_ref, photo_content_type, visibility, bio, created_at) "
            "VALUES (?, ?, ?, ?, ?, NULL, NULL, 'public', ?, ?)",
            (pet_id, SYSTEM_USER, row["origin"], row["candidate_id"], species, row["personality"], now),
        )
        residence = "res-hk-saikung" if any(word in (row["dream"] or "") for word in SEASIDE_WORDS) else "res-hk-central"
        conn.execute("INSERT INTO web_residents (pet_id, candidate_id, residence_id, kind, status, public_since) VALUES (?, ?, ?, 'adoptable', 'resident', ?)",
                     (pet_id, row["candidate_id"], residence, now))
        conn.execute("UPDATE web_adoption_candidates SET adopted_pet_id = ? WHERE candidate_id = ?", (pet_id, row["candidate_id"]))


MIGRATION = WebMigration(
    migration_id="0240_residents",
    module="pets",
    description="adoptable residents become living pets with stable pet_id at planet residences (system record owner, no login); adoption keeps identity",
    apply=_apply,
)
