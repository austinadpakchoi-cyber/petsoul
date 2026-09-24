"""每只宠物一张证件照（CR-6C2B-IDPHOTO）：护照、居民证、驾照等全部证件都用它。

用户原话（6c2b 转来）「我们每一只宠物都要有一个证件照！！用于这些地方！！」。
**付费口径由用户直接定**（A 窗口 2026-09-24 问、答）：**新宠物自动生成、默认开；存量不批量补**。
提示词、取景与校验照 P《宠物证件照导演规范》（`docs/coordination/ID-PHOTO-DIRECTOR-SPEC-ada5.md`），依据版本以 A 日志登记为准。

### 谁要付费画、谁不用

  - 有主人原照（`owner_original`）或领养档案照（`real_archive`）：以那张照片为参考画**一张**，参考照版本变了才重画；
  - **没有照片的宠物不另付费**：插画链路第一次给它画照片时本来就会先画一张基准证件照（`photo_generated=1`）。
    那张就是它的证件照（`source="companion_portrait"`），不落本模块的表、不排任务；它画出来之前是 `absent`。
    **已知差异**（P 规范 §五）：底色不是 `#DCE8F2`、构图是半身；**它没有服务端裁好的头像**，头像地址给 None，不拿整图冒充。

### 两条路线（P 规范 §4.1／§4.3）

  - **透明（推荐，适配器能请求透明时）**：请求 `background=transparent`，按规范 §4.2 的 5 条校验，
    发布时按 alpha 合成到界面常量 `#DCE8F2`。底色分毫不差、颜色词不进提示词；**透明原图私下保留**，将来换底色只需重新合成；
  - **不透明（备选）**：提示词只换最后一句（颜色词只出现一次、放在最后），校验只看解得开、够大、是竖幅、不是整片单色。

两条路线都产出：从上方裁成竖幅 3:4 的证件用图（1024 宽即 1024×1365），和从上方正方形缩成 256×256 的地图头像。

### 触发（看页面、刷新**绝不触发**）

上传成功（`web_pets.create_own` 同一事务，与角色同一个钩子）；领养（`web_pets.adopt` 同一事务，`on_pet_adopted`——
角色的触发范围不变，只登记证件照）；主人显式重画（`regenerate`，前端放进「调整形象」；存量宠物也靠它补——
眼下没有换照片的入口，存量宠物只有点重画才会有证件照）。

自动触发（上传、领养）受 `auto` 管：装配从 `settings.web_id_photo_auto` 读，**没有这个字段就是开**（用户定：默认开）。
**主人点重画不受它管**——那是主人自己要的，关掉自动不等于不让主人画。

### 与角色链路共用、不另抄的

参考照读取与版本号（同一张照片拿同一个号）、归属判断、参考来源闸、领取时的早停、账本、按实结算、
**成功结果恢复**（`paid_result`：小票＋认领，预占编号 `id_photo:<task>:<代数>`，认领回来的原图照样重新合成与裁切）。
额度走**独立车道** `pet:<id>:id_photo`——不和角色车道混，免得打乱"每宠 12 ＝ 一天两套"的算术。
**任务不由 `character.run_pending` 领**（那样会打乱只领角色任务的用例与合同）：生产里由生图泵带上，见 `ImageWorkPump`。
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import struct
import uuid
import zlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..utils import iso, utcnow
from ..web_platform import paid_result
from ..web_platform.budget import BudgetLimit
from ..web_platform.tasks import WebTask, WebTaskQueue, run_once
from . import flatten, prompts, raster, validate
from .model import (
    ABSENT,
    ALREADY_QUEUED,
    ATTEMPTS_EXHAUSTED,
    BUDGET_DENIED,
    FAILED,
    NO_HOUSEHOLD,
    NO_REFERENCE,
    NO_RETRY_REASONS,
    NOT_CONFIGURED,
    NOT_SENT_REASONS,
    QUEUED,
    READY,
    REFERENCE_CHANGED,
    RUNNING,
    UNCONFIRMED,
    UNKNOWN,
)

if TYPE_CHECKING:
    from .service import CharacterService

logger = logging.getLogger("petsoul.web.character")

KIND = "pet_id_photo"
GENERATED, COMPANION_PORTRAIT = "generated", "companion_portrait"
# 界面常量：前端 6c2b 按 UI-ASSET-005 定的低饱和浅蓝。**只用于合成，不进提示词**（P 规范 §4.1）
BACKDROP = (0xDC, 0xE8, 0xF2)
BACKDROP_HEX = "#DCE8F2"
AVATAR_EDGE = 256  # 地图头像边长（像素）
MIN_EDGE = 512  # 不透明路线：短边至少这么大
ASPECT = (0.55, 0.80)  # 不透明路线：宽÷高，请求的是 2:3（0.667），3:4（0.75）也收
MIN_SPREAD = 12  # 不透明路线：抽样亮度极差低于它＝整片几乎一个颜色
RETRYABLE = frozenset({"provider_error"})


@dataclass(frozen=True, slots=True)
class IdPhotoView:
    """纯读结果。`status` 与角色同一口径（`unknown` 不折进 `failed`）。"""

    status: str
    source: str | None = None
    url: str | None = None
    avatar_url: str | None = None
    width: int | None = None
    height: int | None = None
    content_sha256: str | None = None
    reference_version: int | None = None
    revision: int | None = None
    reason: str | None = None
    task_id: str | None = None


class IdPhotoService:
    kind = KIND

    def __init__(self, character: "CharacterService") -> None:
        self.character = character
        self.auto = True  # 用户 2026-09-24 定：新宠物自动生成、**默认开**。只管自动触发，主人点重画不受它管
        self.compile_prompt = prompts.build_id_photo_prompt

    # ---- 地址 ----
    @staticmethod
    def url(asset_id: str) -> str:
        return f"/api/v1/web/media/id-photos/{asset_id}"

    @staticmethod
    def avatar_url(asset_id: str) -> str:
        return f"/api/v1/web/media/id-photos/{asset_id}/avatar"

    # ---- 登记：上传成功／领养的同一事务里，或主人显式重画 ----
    def request_in(self, conn: sqlite3.Connection, pet_id: str, user_id: str, *, now=None, again: bool = False) -> str | None:
        """在**调用方的写事务里**登记一次证件照任务。前置条件不满足就什么都不写（返回 None）。

        自动触发（`again=False`）时，这张参考照已经有在排、在画或已生效的证件照就不再排——**多排就是多花一次钱**；
        主人显式重画（`again=True`）才开新的一轮。
        """
        character = self.character
        if (not again and not self.auto) or not character.available():
            return None
        record = conn.execute("SELECT species FROM web_pet_profiles WHERE pet_id = ?", (pet_id,)).fetchone()
        if record is None or record["species"] not in prompts.ID_PHOTO_FACE:
            return None
        reference_key, generated = character._reference_of(conn, pet_id)
        if not reference_key or generated:
            return None  # 没照片、或只有基准证件照：复用它，不另画
        if not character._in_household(conn, pet_id):
            return None
        stamp = iso(now or utcnow())
        version = character._reference_version_in(conn, pet_id, reference_key, stamp)
        if not again:
            existing = conn.execute(
                "SELECT task_id FROM web_pet_id_photos WHERE pet_id = ? AND reference_version = ? AND style_version = ? "
                "AND state IN ('queued', 'running', 'ready') ORDER BY revision DESC LIMIT 1",
                (pet_id, version, prompts.ID_PHOTO_STYLE_VERSION)).fetchone()
            if existing is not None:
                return existing["task_id"]
        revision = int(conn.execute("SELECT COALESCE(MAX(revision), 0) + 1 AS n FROM web_pet_id_photos WHERE pet_id = ?",
                                    (pet_id,)).fetchone()["n"])
        asset_id = f"ip-{uuid.uuid4().hex[:12]}"
        payload = {"asset_id": asset_id, "pet_id": pet_id, "user_id": user_id, "species": record["species"],
                   "reference_key": reference_key, "reference_version": version,
                   "style_version": prompts.ID_PHOTO_STYLE_VERSION, "revision": revision}
        dedupe = f"id_photo:{pet_id}:{version}:{prompts.ID_PHOTO_STYLE_VERSION}:{revision}"
        task, created = character.tasks.enqueue_in(conn, KIND, dedupe, payload, max_attempts=2, now=now)
        if created:
            conn.execute(
                "INSERT INTO web_pet_id_photos (asset_id, pet_id, user_id, state, task_id, revision, reference_key, "
                "reference_version, style_version, created_at, updated_at) VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?)",
                (asset_id, pet_id, user_id, task.task_id, revision, reference_key, version, prompts.ID_PHOTO_STYLE_VERSION,
                 stamp, stamp))
        return task.task_id

    def regenerate(self, pet_id: str, user_id: str) -> tuple[bool, str, str | None]:
        """主人显式重画。**已有在排、在画的就拒绝**，不再排一个——重复点击、丢回执、刷新都落在这条上。"""
        from ..web_platform.uow import unit_of_work

        with unit_of_work(self.character.storage) as conn:
            # 看**最近一轮**而不是展示状态：已有生效的证件照时展示的永远是它（ready），新一轮在画也会被它盖住
            latest = conn.execute("SELECT state FROM web_pet_id_photos WHERE pet_id = ? ORDER BY revision DESC LIMIT 1",
                                  (pet_id,)).fetchone()
            if latest is not None and latest["state"] in (QUEUED, RUNNING):
                return (False, latest["state"], ALREADY_QUEUED)
            status = self.view_in(conn, pet_id).status
            task_id = self.request_in(conn, pet_id, user_id, again=True)
            if task_id is None:
                return (False, status, self.character.blocked_reason_in(conn, pet_id) or NOT_CONFIGURED)
            return (True, QUEUED, task_id)

    # ---- 纯读（绝不触发生成）----
    def view(self, pet_id: str) -> IdPhotoView:
        with self.character.storage.connect() as conn:
            return self.view_in(conn, pet_id)

    def view_in(self, conn: sqlite3.Connection, pet_id: str) -> IdPhotoView:
        """有已生效的就给它——新一轮在画或失败了，旧的照常显示（证件上不能忽然没了照片）；
        没有已生效的就说最近一轮的状态；都没有时，没照片的宠物给那张基准证件照；再没有就是 `absent`。"""
        active = conn.execute("SELECT p.* FROM web_pet_id_photo_active a JOIN web_pet_id_photos p ON p.asset_id = a.asset_id "
                              "WHERE a.pet_id = ?", (pet_id,)).fetchone()
        if active is not None:
            return IdPhotoView(READY, GENERATED, url=self.url(active["asset_id"]),
                               avatar_url=self.avatar_url(active["asset_id"]) if active["avatar_rel_path"] else None,
                               width=active["width"], height=active["height"], content_sha256=active["sha256"],
                               reference_version=int(active["reference_version"]), revision=int(active["revision"]),
                               task_id=active["task_id"])
        latest = conn.execute("SELECT * FROM web_pet_id_photos WHERE pet_id = ? ORDER BY revision DESC LIMIT 1", (pet_id,)).fetchone()
        if latest is not None:
            state = latest["state"]
            if state == FAILED and self._maybe_sent(latest["task_id"]):
                state = UNKNOWN  # 可能已经发出、结果未确认：**不能说成没画成**，那会让主人再付一次
            return IdPhotoView(state, GENERATED, reason=latest["reason"], reference_version=int(latest["reference_version"]),
                               revision=int(latest["revision"]), task_id=latest["task_id"])
        reference_key, generated = self.character._reference_of(conn, pet_id)
        if reference_key and generated:
            # 那张基准证件照就是宠物照片本身。**没有服务端裁好的头像**：头像给 None，不拿整图冒充（W1 的前提）
            return IdPhotoView(READY, COMPANION_PORTRAIT, url=f"/api/v1/web/media/pets/{pet_id}/photo")
        return IdPhotoView(ABSENT)

    def avatar_url_of(self, pet_id: str) -> str | None:
        """地图头像：**256×256**、从已生效证件照的上方正方形缩成的小方图的受保护地址。给世界状态（W1）用。

        **纯读，绝不触发生成**。没有就返回 None——**不回退到任何别的图**（没照片的宠物那张基准照不是裁好的头像，也给 None）。
        """
        view = self.view(pet_id)
        return view.avatar_url if view.status == READY else None

    def media_path(self, asset_id: str, *, avatar: bool = False):
        """(文件, content_type, pet_id)。**裁定归路由**——这里只解析路径，不做可见性判断。透明原图不对外。"""
        with self.character.storage.connect() as conn:
            row = conn.execute("SELECT pet_id, rel_path, avatar_rel_path FROM web_pet_id_photos "
                               "WHERE asset_id = ? AND state = 'ready'", (asset_id,)).fetchone()
        rel = (row["avatar_rel_path"] if avatar else row["rel_path"]) if row is not None else None
        if not rel:
            return None
        root = self.character.root
        path = (root / rel).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            return None
        return (path, "image/png", row["pet_id"]) if path.is_file() else None

    def _maybe_sent(self, task_id: str) -> bool:
        """这一轮的最近一笔预占是否停在"可能已经发出"（或账本读不到）。与认领用同一个判定，不另写一份 SQL。"""
        last = paid_result._last_reservation(self.character.storage, f"id_photo:{task_id}:")
        return last == "ledger_unreadable" or (isinstance(last, tuple) and last[0] in paid_result.MAYBE_SENT)

    # ---- 执行 ----
    def precheck(self, task: WebTask) -> bool:
        """领取时的早停：主人原照换了就不执行（与角色同一道、读同一列）。"""
        return self.character.precheck(task)

    def run_pending(self, worker_id: str = "web-id-photos", limit: int = 5) -> int:
        handled = 0
        for _ in range(limit):
            task = run_once(self.character.tasks, {KIND: self}, worker_id)
            if task is None:
                break
            handled += 1
            if task.status in ("failed", "superseded"):
                with self.character.storage.connect() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    self._fail_in(conn, task.payload["asset_id"],
                                  REFERENCE_CHANGED if task.status == "superseded" else ATTEMPTS_EXHAUSTED)
        return handled

    def run_claimed(self, task: WebTask, claim, queue: WebTaskQueue) -> None:
        """付费调用在事务外发；写记录、切生效、完成任务在同一个领取围栏事务里（与角色同一副骨架，表不同）。"""
        with queue.fenced(claim, complete=False) as conn:
            conn.execute("UPDATE web_pet_id_photos SET state = 'running', updated_at = ? WHERE asset_id = ? AND state = 'queued'",
                         (iso(utcnow()), task.payload["asset_id"]))
        rendered, refused = self._render(task, attempt=claim.claim_generation)
        if rendered is None:
            with queue.fenced(claim, complete=False) as conn:
                self._fail_in(conn, task.payload["asset_id"], refused)
            queue.fail_claim(claim, f"id_photo {refused}", retryable=refused not in NO_RETRY_REASONS)
            return
        with queue.fenced(claim) as conn:
            self._publish_in(conn, task, rendered)

    def _render(self, task: WebTask, *, attempt: int) -> tuple:
        """返回 ((三份文件与尺寸, 图片) 或 None, 不发布的原因 或 None)。可自动重试的供应商失败往外抛。"""
        from ..web_providers import ImageUnavailable

        character = self.character
        payload = task.payload
        pet_id, user_id = payload["pet_id"], payload["user_id"]
        template = f"id-photos/{user_id}/{payload['asset_id']}-{{attempt}}"
        # 自动重试：可能已经发出 → 不重发；已付费成功、只是没写进去 → 认领那张原图、重新合成与裁切（成功结果恢复）
        if task.last_error:
            resumed = paid_result.resume(character.storage, f"id_photo:{task.task_id}:", character.root, template)
            if resumed is not None:
                finished = self._finish(resumed.image, resumed.rel, template.format(attempt=resumed.attempt)) if resumed.image else None
                if finished is None:
                    logger.info("id photo not resent task=%s previous=%s", task.task_id, resumed.blocked or "reclaimed_invalid")
                    return None, UNCONFIRMED
                return finished
        if not character.available():
            return None, NOT_CONFIGURED
        gate = character._reference_gate(payload)
        if gate is not None:
            return None, gate  # 全部在预占之前：0 预占、0 发送
        reference = character.reference_photo_of(pet_id)
        if reference is None:
            return None, NO_REFERENCE
        transparent = character.transparency_requested
        prompt = self.compile_prompt(payload["species"], tuple(character.appearance_tags_of(pet_id)), opaque=not transparent)
        permit = self._reserve(f"id_photo:{task.task_id}:{attempt}", pet_id)
        if permit is not None and getattr(permit, "status", None) != "reserved":
            logger.info("id photo budget denied task=%s reason=%s", task.task_id, getattr(permit, "reason", "unknown"))
            return None, BUDGET_DENIED
        try:
            if transparent:
                image = character.illustrator.render(prompt, reference, size=prompts.ID_PHOTO_CANVAS, background="transparent")
            else:
                image = character.illustrator.render(prompt, reference, size=prompts.ID_PHOTO_CANVAS)
        except ImageUnavailable as exc:
            character._settle_calls(permit, exc.reason, 0 if exc.reason in NOT_SENT_REASONS else 1)
            if exc.reason in RETRYABLE:
                raise
            return None, exc.reason
        character._settle_calls(permit, "succeeded", 1)
        refused = self._inspect(image.image_bytes, image.mime_type, transparent)
        if refused is not None:
            logger.info("id photo rejected task=%s reason=%s", task.task_id, refused)
            return None, refused
        stem = template.format(attempt=attempt)
        (character.root / "id-photos" / user_id).mkdir(parents=True, exist_ok=True)
        rel = f"{stem}.png"
        (character.root / rel).write_bytes(image.image_bytes)
        paid_result.write_receipt(character.root, stem, rel, image, transparent=transparent)
        finished = self._finish(image, rel, stem)
        return finished if finished is not None else (None, validate.UNDECODABLE)  # 校验过了却合成不了：不发布、不重试

    def _inspect(self, data: bytes, mime_type: str, transparent: bool) -> str | None:
        """透明路线照 P 规范 §4.2 的 5 条（`validate.inspect_id_photo`）；不透明路线看解得开、够大、是竖幅、不是整片单色。"""
        if transparent:
            verdict = validate.inspect_id_photo(data, mime_type)
            return None if verdict.ok else (verdict.reason or validate.UNDECODABLE)
        try:
            width, height, rgb = raster.decode(data)
        except (ValueError, struct.error, zlib.error) as exc:
            reason = str(exc)
            return reason if reason in (validate.NOT_PNG, validate.PALETTE, validate.BIT_DEPTH, validate.TOO_LARGE) else validate.UNDECODABLE
        if min(width, height) < MIN_EDGE:
            return validate.PHOTO_TOO_SMALL
        if not ASPECT[0] <= width / height <= ASPECT[1]:
            return validate.PHOTO_WRONG_SHAPE
        if raster.luma_spread(width, height, rgb) < MIN_SPREAD:
            return validate.PHOTO_BLANK
        return None

    def _finish(self, image, rel: str, stem: str) -> tuple | None:
        """原图 → 证件用图（合成底色、从上方裁 3:4）＋ 地图头像（上方正方形缩到 256）。解不开返回 None。

        透明原图私下保留在 `rel`；认领回来时从它重新合成与裁切，结果与第一次一致（纯函数）。
        """
        try:
            if validate._shape(image.image_bytes) == validate.NO_ALPHA_CHANNEL:
                width, height, rgb = raster.decode(image.image_bytes)  # 不透明路线
                backdrop = None
            else:
                width, height, rgb = flatten.onto(image.image_bytes, BACKDROP)  # 透明路线：按 alpha 合成到界面常量
                backdrop = BACKDROP_HEX
            photo = raster.top_portrait(width, height, rgb)
            avatar = raster.avatar_of(width, height, rgb, AVATAR_EDGE)
        except (ValueError, struct.error, zlib.error):
            logger.warning("id photo could not be composed rel=%s", rel)
            return None
        root = self.character.root
        (root / f"{stem}.photo.png").write_bytes(photo)
        (root / f"{stem}.avatar.png").write_bytes(avatar)
        photo_height = min(height, width * 4 // 3)
        return ((rel, f"{stem}.photo.png", f"{stem}.avatar.png", backdrop, width, photo_height, photo), image), None

    def _reserve(self, operation_id: str, pet_id: str):
        """独立车道 `pet:<id>:id_photo` ＋ 全局 `provider:image:daily`（上限取值与角色同源，0＝该层不限）。"""
        character = self.character
        if character.reserve is None:
            return None
        limits = [BudgetLimit("provider:image:daily", character.global_daily)] if character.global_daily else []
        if character.per_pet_daily:
            limits.append(BudgetLimit(f"pet:{pet_id}:id_photo", character.per_pet_daily))
        return character.ledger.reserve(operation_id, provider="image", purpose="id_photo", subject_scope=f"pet:{pet_id}",
                                        units=1, limits=limits)

    # ---- 落定 ----
    @staticmethod
    def _fail_in(conn: sqlite3.Connection, asset_id: str, reason: str | None) -> None:
        conn.execute("UPDATE web_pet_id_photos SET state = 'failed', reason = COALESCE(?, reason), updated_at = ? "
                     "WHERE asset_id = ? AND state IN ('queued', 'running')", (reason, iso(utcnow()), asset_id))

    def _publish_in(self, conn: sqlite3.Connection, task: WebTask, rendered: tuple) -> None:
        """最终复核（原照没换、还有家）→ 写记录 → 原子切生效（revision 更大才换）。"""
        payload = task.payload
        pet_id = payload["pet_id"]
        current, _ = self.character._reference_of(conn, pet_id)
        refused = REFERENCE_CHANGED if current != payload["reference_key"] else (
            None if self.character._in_household(conn, pet_id) else NO_HOUSEHOLD)
        if refused is not None:
            logger.info("id photo not published task=%s reason=%s", task.task_id, refused)
            self._fail_in(conn, payload["asset_id"], refused)
            return
        (source_rel, photo_rel, avatar_rel, backdrop, width, height, photo), image = rendered
        now = iso(utcnow())
        conn.execute(
            "UPDATE web_pet_id_photos SET state = 'ready', reason = NULL, rel_path = ?, avatar_rel_path = ?, source_rel_path = ?, "
            "backdrop = ?, content_type = 'image/png', provider = ?, model = ?, sha256 = ?, width = ?, height = ?, "
            "reference_digest = ?, updated_at = ? WHERE asset_id = ?",
            (photo_rel, avatar_rel, source_rel, backdrop, image.provider, image.model, hashlib.sha256(photo).hexdigest(),
             width, height, self.character._reference_digest(pet_id), now, payload["asset_id"]))
        conn.execute(
            "INSERT INTO web_pet_id_photo_active (pet_id, asset_id, revision, published_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(pet_id) DO UPDATE SET asset_id = excluded.asset_id, revision = excluded.revision, "
            "published_at = excluded.published_at WHERE excluded.revision > web_pet_id_photo_active.revision",
            (pet_id, payload["asset_id"], payload["revision"], now))
