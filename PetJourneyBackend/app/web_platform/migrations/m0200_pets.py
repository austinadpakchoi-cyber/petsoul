"""0200：网页宠物画像（来源/公开范围/私有照片引用）与专属领养池（原创伙伴种子）。

领养候选均为 PetSoul 原创伙伴，source_note 明确标注原创；不包含任何真实原型或真实离世背景。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration

ORIGINAL_CANDIDATES = [
    ("adopt-lan", "小岚", "cat", "慢热、爱在高处看风景", "想去看一次真正的海"),
    ("adopt-lizi", "栗子", "dog", "热情、走路会蹦", "想当一次小小飞行员"),
    ("adopt-arong", "阿绒", "rabbit", "安静、喜欢收集叶子", "开一家小小植物店"),
    ("adopt-doudou", "豆豆", "hamster", "胆小但记性很好", "把每座城市的面包都尝一口"),
    ("adopt-qiuqiu", "秋秋", "bird", "爱唱歌、会模仿雨声", "在灯塔上看一次日出"),
    ("adopt-mochi", "麻薯", "cat", "黏人、午睡冠军", "坐一次夜班火车"),
    ("adopt-pudding", "布丁", "dog", "好奇、见谁都摇尾巴", "当一回小侦探"),
    ("adopt-yunduo", "云朵", "rabbit", "害羞、会给朋友留胡萝卜", "去山顶看云海"),
]


def _apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE web_pet_profiles (
            pet_id TEXT PRIMARY KEY REFERENCES pets(pet_id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            origin TEXT NOT NULL CHECK (origin IN ('own_pet', 'adopted_original', 'adopted_real_archive')),
            candidate_id TEXT UNIQUE,
            species TEXT NOT NULL,
            photo_ref TEXT,
            photo_content_type TEXT,
            visibility TEXT NOT NULL DEFAULT 'private' CHECK (visibility IN ('public', 'followers', 'private')),
            bio TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE web_adoption_candidates (
            candidate_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            species TEXT NOT NULL,
            personality TEXT NOT NULL,
            dream TEXT NOT NULL,
            origin TEXT NOT NULL,
            source_note TEXT,
            background_available INTEGER NOT NULL DEFAULT 0,
            availability TEXT NOT NULL CHECK (availability IN ('available', 'reserved', 'adopted')),
            adopted_by_user TEXT,
            adopted_pet_id TEXT,
            adopted_at TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    for candidate_id, name, species, personality, dream in ORIGINAL_CANDIDATES:
        conn.execute(
            "INSERT INTO web_adoption_candidates (candidate_id, name, species, personality, dream, origin, source_note, "
            "background_available, availability, created_at) VALUES (?, ?, ?, ?, ?, 'adopted_original', ?, 0, 'available', "
            "strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
            (candidate_id, name, species, personality, dream, "PetSoul 原创伙伴"),
        )


MIGRATION = WebMigration(
    migration_id="0200_pets",
    module="pets",
    description="web pet profiles + exclusive adoption pool (original companions)",
    apply=_apply,
)
