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

# 平台自己的原创居民形象（随仓打包，不是任何用户上传的文件）：`photo_ref` 记成 `platform:<文件名>`。
# 为什么不放进私有媒体目录：那个目录是**各环境各一份**的运行数据，而建档是迁移做的——迁移只拿得到
# 数据库连接、放不了文件。打包进仓之后每个环境（开发、隔离后端、将来的部署）看到的都是同一张图。
# **只在这个目录里、只认严格的文件名**：前缀后面带斜杠、点点、盘符的一律当不存在，不做路径拼接之外的任何解析。
PLATFORM_PHOTO_PREFIX = "platform:"
PLATFORM_PHOTO_DIR = Path(__file__).resolve().parent / "platform_photos"


def _platform_photo(ref: str) -> Path | None:
    name = ref[len(PLATFORM_PHOTO_PREFIX):]
    if not name or name != Path(name).name or not name.endswith(".png") or name.startswith(".") or ".." in name:
        return None
    path = PLATFORM_PHOTO_DIR / name
    return path if path.is_file() else None


class AlreadyHasCompanion(Exception):
    """旧版“一个账号只陪伴一只伙伴”的错误：0.4.0 起不再抛出，保留类名给旧调用方。"""


class AdoptionTaken(Exception):
    pass


class CandidateNotFound(Exception):
    pass


class PhotoNotAddable(Exception):
    """补照片被拒。reason：`photo_exists`（已有照片——含没照片时生成的形象照，换掉它就是「替换」，要等用户拍板）／
    `not_own_pet`（领养的伙伴有自己设定的样子，不补真实照片）。"""

    def __init__(self, reason: str, generated: bool = False) -> None:
        super().__init__(reason)
        self.reason, self.generated = reason, generated


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
        # 主人上传的原照刚落库（角色模块装配后注入）：**在同一个事务里**登记世界角色生成任务。
        # 为什么必须同事务：上传那一步回滚了，队列里却留着一张要花钱的图，就是"上传没成功但任务排上了"；
        # 反过来另开连接排队还会读到事务外的旧授权快照。钩子没接时这里什么都不做，行为与接线前完全一致。
        self.on_pet_photo_stored = None  # Callable[[conn, pet_id, user_id, species, photo_ref, content_type, now], None]
        # 领养成功（证件照模块装配后注入）：**同一个事务里、归属写好之后**登记证件照任务。只管证件照，角色的触发范围不变；
        # 有没有照片、能不能画由那边判断。钩子没接时这里什么都不做，行为与接线前完全一致。
        self.on_pet_adopted = None  # Callable[[conn, pet_id, user_id, now], None]

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
            # **建好家之后**才登记角色任务：授权是家庭级的，新建的家没显式设置时要回落到建家人的个人选择，
            # 家还没建出来就读不到授权，会把"其实已授权"读成"没授权"。
            if photo_ref and self.on_pet_photo_stored is not None:
                self.on_pet_photo_stored(conn, pet_id, user_id, species.value, photo_ref, content_type, now)
        return self.profile(pet_id)  # type: ignore[return-value]

    def adopt(self, user_id: str, candidate_id: str, household_id: str | None = None) -> AdoptResult:
        """原子专属领养：只有仍 available、且还在领养名单上（没被后台撤下，迁移 0260）的候选能被领走，
        两个家庭同时抢同一只最多一个成功（其余 AdoptionTaken）；撤下的按「找不到」处理（CandidateNotFound）。
        已经在星球上生活的待领养居民（有 pet_id）保留身份、性格与公开经历，只改变归属；老的纯资料候选才在这时建宠物。"""
        now = utcnow()
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM web_adoption_candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
            if row is None or not row["listed"]:
                raise CandidateNotFound()
            resident_pet = row["adopted_pet_id"] if row["availability"] == "available" and row["adopted_pet_id"] else None
            pet_id = resident_pet or f"PJ-{uuid.uuid4().hex[:8].upper()}"
            claimed = conn.execute(
                "UPDATE web_adoption_candidates SET availability = 'adopted', adopted_by_user = ?, adopted_pet_id = ?, adopted_at = ? "
                "WHERE candidate_id = ? AND availability = 'available' AND listed = 1",
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
            if self.on_pet_adopted is not None:
                self.on_pet_adopted(conn, pet_id, user_id, now)
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

    def add_photo(self, pet_id: str, photo: bytes) -> PetProfileRecord:
        """入住时没带照片、之后补一张（6c2b 2026-09-24：兑现入住时写的「照片可以以后再补」）。**只补不换**。

        - 只对「自己的宠物」开放；已经有照片的（包括没照片时生成的那张形象照）一律 `photo_exists`——
          把已有的换掉是「替换」，要不要开放由用户拍板；
        - 与建宠物同一条路径：先清洗（剥元数据、只收三种格式），再私有存储，文件放在主人名下；
        - **不调 `on_pet_photo_stored`**：那个钩子会自动登记形象与证件照（付费调用）；补照片要不要自动生成，等用户拍板。
          钩子没接线时建宠物那条路的行为逐字节不变，这里也不改它；
        - 写入用条件更新（`photo_ref IS NULL`）：两个请求同时补，只有一个成功，另一个回 `photo_exists`，它先存下的文件删掉。
        调用方已检查照顾权限。
        """
        record = self.profile(pet_id)
        if record is None or record.origin is not PetOrigin.own_pet:
            raise PhotoNotAddable("not_own_pet")
        if record.photo_ref:
            raise PhotoNotAddable("photo_exists", generated=self.photo_generated(pet_id))
        clean, content_type = sanitize_image(photo)
        ref = store_private(self.media_root, record.user_id, clean, content_type)
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            updated = conn.execute("UPDATE web_pet_profiles SET photo_ref = ?, photo_content_type = ?, photo_generated = 0 "
                                   "WHERE pet_id = ? AND photo_ref IS NULL", (ref, content_type, pet_id)).rowcount
        if updated != 1:
            stored = resolve_private(self.media_root, ref)
            if stored is not None:
                stored.unlink(missing_ok=True)
            raise PhotoNotAddable("photo_exists", generated=self.photo_generated(pet_id))
        return self.profile(pet_id)  # type: ignore[return-value]

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
        if record.photo_ref.startswith(PLATFORM_PHOTO_PREFIX):
            platform = _platform_photo(record.photo_ref)
            return (platform, record.photo_content_type or "image/png") if platform else None
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
                "SELECT c.*, r.pet_id AS resident_pet_id, r.status AS resident_status, r.public_since, s.label AS residence_label, "
                "p.photo_ref AS resident_photo_ref, p.visibility AS resident_visibility "
                "FROM web_adoption_candidates c LEFT JOIN web_residents r ON r.candidate_id = c.candidate_id "
                "LEFT JOIN web_residences s ON s.residence_id = r.residence_id "
                "LEFT JOIN web_pet_profiles p ON p.pet_id = r.pet_id "
                "WHERE c.listed = 1 "  # 后台撤下的不出现在领养卡里（迁移 0260）
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
                # 走**公开**路由（领养卡是给还没领养的访客看的，成员路由 `/media/pets/…` 他们打不开）；
                # 与 pet_id 同一条规则：只在仍可领养时给，领养后不再从领养卡暴露。
                photo_url=(f"/api/v1/web/public/media/pets/{row['resident_pet_id']}/photo"
                           if living and row["resident_photo_ref"] and row["resident_visibility"] == "public" else None),
            ))
        return result

    def candidate_for_pet(self, pet_id: str) -> str | None:
        """这只待领养居民对应的领养卡（仍可领养时）。"""
        with self.storage.connect() as conn:
            row = conn.execute("SELECT c.candidate_id FROM web_adoption_candidates c JOIN web_residents r ON r.candidate_id = c.candidate_id "
                               "WHERE r.pet_id = ? AND r.status = 'resident' AND c.availability = 'available' AND c.listed = 1",
                               (pet_id,)).fetchone()
        return row["candidate_id"] if row else None

    def set_listed_in(self, conn: sqlite3.Connection, candidate_id: str, listed: bool) -> str:
        """撤下 / 放回一位待领养居民（运营后台调用，在调用方的写事务里；迁移 0260）。

        撤下＝不再出现在领养卡、访客页，也不能被领养；TA 照常在驿站生活（不暂停、不删除）。放回＝恢复。
        返回 `changed`（改了）/ `unchanged`（本来就是这个状态）/ `not_eligible`（已被领养或正在领养：身份与经历必须连续，不动）/ `missing`。
        更新语句里带上前提条件，并发时以数据库里那一刻的状态为准。
        """
        row = conn.execute("SELECT availability, listed FROM web_adoption_candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
        if row is None:
            return "missing"
        if row["availability"] != "available":
            return "not_eligible"
        if bool(row["listed"]) == listed:
            return "unchanged"
        changed = conn.execute("UPDATE web_adoption_candidates SET listed = ? WHERE candidate_id = ? AND availability = 'available' AND listed = ?",
                               (int(listed), candidate_id, int(not listed))).rowcount
        return "changed" if changed == 1 else "unchanged"

    def adopted_at(self, candidate_id: str):
        with self.storage.connect() as conn:
            row = conn.execute("SELECT adopted_at FROM web_adoption_candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
        return parse_dt(row["adopted_at"]) if row and row["adopted_at"] else None
