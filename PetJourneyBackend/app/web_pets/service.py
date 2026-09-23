"""网页宠物：建立自己的宠物（私有照片）、原子专属领养、公开主页投影与公开范围设置。

- 一只宠物只归属一个家庭；一个家庭可以有多只宠物（0.4.0）。建宠/领养时在同一个事务里：
  没有指定家庭 → 新建家庭（这个账号成为管理员）与一个家；指定了家庭 → 加进这个家（由路由先检查“家庭管理员”权限）。
  不再因为“已经有伙伴”拒绝；独占领养规则不变：同一只宠物不能进两个家庭。
- 建立宠物只创建归属与家（未入住），不调用旧 create_initial_journey；旅程在入住后开始。
- 宠物记录写入既有 pets 表（photo_path 为空，旧 /media 不会暴露网页照片），网页画像在 web_pet_profiles；
  web_pet_profiles.user_id 是“建档者”（待领养居民是系统保留的星球居民身份），不是权限依据——权限只看家庭成员关系。
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

from ..schemas import PetDNA
from ..schemas.web.pets import (
    AdoptionAvailability,
    AdoptionCandidate,
    AdoptResult,
    PetOrigin,
    PetPublicProfile,
    PetSpecies,
    ProfileVisibility,
)
from ..schemas.web.common import DataOrigin
from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from ..web_household import HouseholdService
from .media import resolve_private, sanitize_image, store_private


class AlreadyHasCompanion(Exception):
    """旧版“一个账号只陪伴一只伙伴”的错误：0.4.0 起不再抛出，保留类名给旧调用方。"""


class AdoptionTaken(Exception):
    pass


class CandidateNotFound(Exception):
    pass


@dataclass(frozen=True, slots=True)
class PetProfileRecord:
    pet_id: str
    user_id: str
    name: str
    species: PetSpecies
    origin: PetOrigin
    candidate_id: str | None
    photo_ref: str | None
    photo_content_type: str | None
    visibility: ProfileVisibility
    bio: str | None


LEGACY_PET_TYPES = {"dog", "cat", "parrot", "rabbit", "hamster", "bird", "other"}


class WebPetsService:
    def __init__(self, storage: JourneyStorage, private_media_root: Path, households: HouseholdService) -> None:
        self.storage = storage
        self.media_root = private_media_root
        self.households = households
        # 领养一位待领养居民时（居民模块装配后注入）：同一事务里把它从驿站名单转到这个家庭，保留身份与经历
        self.on_resident_adopted = None  # Callable[[sqlite3.Connection, pet_id, household_id, user_id, now], None]

    # ---- 建立伙伴 ----
    def create_own(self, user_id: str, name: str, species: PetSpecies, photo: bytes | None, household_id: str | None = None) -> PetProfileRecord:
        """household_id 为空：新建家庭（这个账号成为管理员）；否则加进这个家庭（调用方已检查管理员权限）。"""
        photo_ref = content_type = None
        if photo:
            clean, content_type = sanitize_image(photo)
            photo_ref = store_private(self.media_root, user_id, clean, content_type)
        now = utcnow()
        pet_id = f"PJ-{uuid.uuid4().hex[:8].upper()}"
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._insert_pet(conn, pet_id, user_id, name.strip()[:24], species, PetOrigin.own_pet, None, photo_ref, content_type, now)
            if household_id is None:
                self.households.create_with_pet(conn, user_id, pet_id, "upload", now)
            else:
                self.households.add_pet(conn, household_id, pet_id, user_id, "upload", now)
        return self.profile(pet_id)  # type: ignore[return-value]

    def adopt(self, user_id: str, candidate_id: str, household_id: str | None = None) -> AdoptResult:
        """原子专属领养：只有仍 available 的候选能被领走，两个家庭同时抢同一只最多一个成功（其余 AdoptionTaken）。
        已经在星球上生活的待领养居民（有 pet_id）保留身份、性格与公开经历，只改变归属；老的纯资料候选才在这时建宠物。"""
        now = utcnow()
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM web_adoption_candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
            if row is None:
                raise CandidateNotFound()
            resident_pet = row["adopted_pet_id"] if row["availability"] == "available" and row["adopted_pet_id"] else None
            pet_id = resident_pet or f"PJ-{uuid.uuid4().hex[:8].upper()}"
            claimed = conn.execute(
                "UPDATE web_adoption_candidates SET availability = 'adopted', adopted_by_user = ?, adopted_pet_id = ?, adopted_at = ? "
                "WHERE candidate_id = ? AND availability = 'available'",
                (user_id, pet_id, iso(now), candidate_id),
            ).rowcount
            if claimed != 1:
                raise AdoptionTaken()
            if resident_pet is None:
                self._insert_pet(conn, pet_id, user_id, row["name"], PetSpecies(row["species"]), PetOrigin(row["origin"]), candidate_id, None, None, now)
            if household_id is None:
                household_id, _ = self.households.create_with_pet(conn, user_id, pet_id, "adoption", now)
            else:
                self.households.add_pet(conn, household_id, pet_id, user_id, "adoption", now)
            if resident_pet is not None and self.on_resident_adopted is not None:
                self.on_resident_adopted(conn, pet_id, household_id, user_id, now)
        return AdoptResult(pet_id=pet_id, candidate_id=candidate_id, adopted_at=now)

    def _insert_pet(self, conn: sqlite3.Connection, pet_id, user_id, name, species, origin, candidate_id, photo_ref, content_type, now) -> None:
        pet_type = species.value if species.value in LEGACY_PET_TYPES else "other"
        conn.execute(
            "INSERT INTO pets (pet_id, name, pet_type, dna_json, created_at, photo_path, owner_user_id) VALUES (?, ?, ?, ?, ?, NULL, ?)",
            (pet_id, name, pet_type, PetDNA().model_dump_json(by_alias=True), iso(now), user_id),
        )
        conn.execute(
            "INSERT INTO web_pet_profiles (pet_id, user_id, origin, candidate_id, species, photo_ref, photo_content_type, visibility, bio, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'private', NULL, ?)",
            (pet_id, user_id, origin.value, candidate_id, species.value, photo_ref, content_type, iso(now)),
        )

    def is_resident(self, pet_id: str) -> bool:
        """还没有家庭、住在星球居民驿站的待领养居民。"""
        with self.storage.connect() as conn:
            row = conn.execute("SELECT status FROM web_residents WHERE pet_id = ?", (pet_id,)).fetchone()
        return bool(row and row["status"] == "resident")

    # ---- 读取 ----
    def profile(self, pet_id: str) -> PetProfileRecord | None:
        with self.storage.connect() as conn:
            row = conn.execute(
                "SELECT p.*, pets.name AS name FROM web_pet_profiles p JOIN pets ON pets.pet_id = p.pet_id WHERE p.pet_id = ?",
                (pet_id,),
            ).fetchone()
        if row is None:
            return None
        return PetProfileRecord(
            pet_id=row["pet_id"],
            user_id=row["user_id"],
            name=row["name"],
            species=PetSpecies(row["species"]),
            origin=PetOrigin(row["origin"]),
            candidate_id=row["candidate_id"],
            photo_ref=row["photo_ref"],
            photo_content_type=row["photo_content_type"],
            visibility=ProfileVisibility(row["visibility"]),
            bio=row["bio"],
        )

    def set_portrait(self, pet_id: str, image: bytes, content_type: str) -> bool:
        """没有照片的伙伴：存一张生成的写实“证件照”作为它的样子（不覆盖主人上传的真实照片）。"""
        record = self.profile(pet_id)
        if record is None or record.photo_ref or content_type not in ("image/jpeg", "image/png", "image/webp"):
            return False
        ref = store_private(self.media_root, record.user_id, image, content_type)
        with self.storage.connect() as conn:
            return conn.execute("UPDATE web_pet_profiles SET photo_ref = ?, photo_content_type = ?, photo_generated = 1 WHERE pet_id = ? AND photo_ref IS NULL",
                                (ref, content_type, pet_id)).rowcount == 1

    def photo_generated(self, pet_id: str) -> bool:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT photo_generated FROM web_pet_profiles WHERE pet_id = ?", (pet_id,)).fetchone()
        return bool(row and row["photo_generated"])

    def photo_url(self, record: PetProfileRecord) -> str | None:
        return f"/api/v1/web/media/pets/{record.pet_id}/photo" if record.photo_ref else None

    def traits(self, record: PetProfileRecord) -> tuple[str | None, str | None]:
        """(性格, 梦想)：领养伙伴取候选资料；自己的宠物只用主人写的简介，没有就留空（不编造）。"""
        if record.candidate_id:
            with self.storage.connect() as conn:
                row = conn.execute("SELECT personality, dream FROM web_adoption_candidates WHERE candidate_id = ?", (record.candidate_id,)).fetchone()
            if row is not None:
                return row["personality"], row["dream"]
        return record.bio, None

    def is_member(self, viewer_user_id: str | None, pet_id: str) -> bool:
        return viewer_user_id is not None and self.households.access_pet(viewer_user_id, pet_id) is not None

    def can_view(self, viewer_user_id: str | None, record: PetProfileRecord, is_follower: bool = False) -> bool:
        """家庭成员总能看；公开的谁都能看；“仅关注者”要求看的人的宠物关注了它。被移出家庭后立即失去访问。"""
        if self.is_member(viewer_user_id, record.pet_id):
            return True
        if record.visibility is ProfileVisibility.public:
            return True
        return record.visibility is ProfileVisibility.followers and is_follower

    def photo_path(self, pet_id: str) -> tuple[Path, str] | None:
        """内部用（生图参考等）：这只宠物自己的照片文件。不做查看权限判断，不能直接回给浏览器。"""
        record = self.profile(pet_id)
        if record is None or not record.photo_ref:
            return None
        path = resolve_private(self.media_root, record.photo_ref)
        return (path, record.photo_content_type or "application/octet-stream") if path else None

    def photo_file(self, viewer_user_id: str | None, pet_id: str, is_follower: bool = False) -> tuple[Path, str] | None:
        record = self.profile(pet_id)
        if record is None or not record.photo_ref or not self.can_view(viewer_user_id, record, is_follower):
            return None
        return self.photo_path(pet_id)

    def public_profile(self, record: PetProfileRecord, follower_count: int, post_count: int) -> PetPublicProfile:
        origin_label = {"own_pet": "自己的宠物", "adopted_original": "PetSoul 原创伙伴", "adopted_real_archive": "真实原型纪念档案"}
        return PetPublicProfile(
            pet_id=record.pet_id,
            display_name=record.name,
            species=record.species,
            avatar_url=self.photo_url(record),
            bio=record.bio,
            origin_label=origin_label[record.origin.value],
            visibility=record.visibility,
            follower_count=follower_count,
            post_count=post_count,
            data_origin=DataOrigin.live,
        )

    def update_profile(self, user_id: str, pet_id: str, visibility: ProfileVisibility | None, bio: str | None) -> PetProfileRecord | None:
        """公开范围与简介（调用方已检查：公开范围需要家庭管理员）。"""
        with self.storage.connect() as conn:
            cur = conn.execute(
                "UPDATE web_pet_profiles SET visibility = COALESCE(?, visibility), bio = COALESCE(?, bio) WHERE pet_id = ?",
                (visibility.value if visibility else None, bio, pet_id),
            )
            if cur.rowcount != 1:
                return None
        return self.profile(pet_id)

    def candidates(self) -> list[AdoptionCandidate]:
        """领养卡。还在星球上生活的待领养居民带上稳定 pet_id、住处与开始公开生活的时间（领养后不再给出，避免暴露新家庭）。"""
        with self.storage.connect() as conn:
            rows = conn.execute(
                "SELECT c.*, r.pet_id AS resident_pet_id, r.status AS resident_status, r.public_since, s.label AS residence_label "
                "FROM web_adoption_candidates c LEFT JOIN web_residents r ON r.candidate_id = c.candidate_id "
                "LEFT JOIN web_residences s ON s.residence_id = r.residence_id "
                "ORDER BY c.availability = 'available' DESC, c.created_at, c.candidate_id").fetchall()
        result = []
        for row in rows:
            living = row["availability"] == "available" and row["resident_status"] == "resident"
            result.append(AdoptionCandidate(
                candidate_id=row["candidate_id"],
                name=row["name"],
                species=PetSpecies(row["species"]),
                personality=row["personality"],
                dream=row["dream"],
                origin=PetOrigin(row["origin"]),
                source_note=row["source_note"],
                background_available=bool(row["background_available"]),
                availability=AdoptionAvailability(row["availability"]),
                data_origin=DataOrigin.live,
                pet_id=row["resident_pet_id"] if living else None,
                residence=row["residence_label"] if living else None,
                living_since=parse_dt(row["public_since"]) if living and row["public_since"] else None,
            ))
        return result

    def candidate_for_pet(self, pet_id: str) -> str | None:
        """这只待领养居民对应的领养卡（仍可领养时）。"""
        with self.storage.connect() as conn:
            row = conn.execute("SELECT c.candidate_id FROM web_adoption_candidates c JOIN web_residents r ON r.candidate_id = c.candidate_id "
                               "WHERE r.pet_id = ? AND r.status = 'resident' AND c.availability = 'available'", (pet_id,)).fetchone()
        return row["candidate_id"] if row else None

    def adopted_at(self, candidate_id: str):
        with self.storage.connect() as conn:
            row = conn.execute("SELECT adopted_at FROM web_adoption_candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
        return parse_dt(row["adopted_at"]) if row and row["adopted_at"] else None
