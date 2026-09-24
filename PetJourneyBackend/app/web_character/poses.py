"""姿态 2..N（CR-PLAYER-CHARACTER 批次二）：睡觉、晒太阳、吃东西、走动、回应抚摸。

依据 P《世界角色导演模式》§6-4／§6-5。与中性姿态走**同一个任务队列、同一份额度、同一套校验**，
不同的只有三处：参考是谁、提示词怎么编、发布时切不切 active。

  - **参考**：同一套里**已生效的中性姿态**，不是主人原照（§6-4 规则一：每个姿态都从原照重画，
    就是把「像不像它」重赌 N 次）。登记时绑定它的 sha256；发送前把文件读出来**现算**再比。
  - **发出去之前压灰底**（`flatten.py`）：参考图不带 alpha，接口把透明区当蒙版的歧义直接消失。
  - **发布不切 active**：这一套在中性姿态通过时已经整体切过去了，其余姿态只是在这一套里补齐。
    读取只看 active 那一套，**缺的姿态只能回落到同一套的中性姿态，绝不回落到旧套的那张**（§6-4 唯一不可放松的不变量）。

执行前与发布前**各核一次同一份判定**（`_stale_in`）：主人原照换没换、宠物还有没有家、active 还是不是这一套。
任何一条变了，这一张作废、不发布。中性姿态本身在执行前另核一次字节（`_source`）。

### 开关：默认关

`enabled` 默认 False——用户 2026-09-24 决定：后端全套做完，**额外姿态的自动生成默认关，不新增付费调用**，
什么时候打开由用户另定。关着的时候**一个姿态任务都不登记、也不领取**，行为与批次一相同。
装配从 `settings.web_character_extra_poses` 读（字段由 config 的持有人加；没有这个字段就是关）。

**打开之前要一起看额度**：一套 6 张（中性 ＋ 五个姿态）全走 `pet:<id>:character` 与全局 `provider:image:daily`。
**历史宠物不补图**（CR「本 CR 不启动历史用户全量补图」）：打开之后，只有新上传或「调整形象」的宠物才生成整套。

### 与中性姿态共用、不另抄的

恢复不重发（`_unconfirmed_attempt`）、预占与结算、发请求＋校验＋落盘（`_draw`）、领取围栏里的执行骨架（`_run_claimed`）、
落 failed（`_fail_in`）、写 ready 行（`model.mark_ready_in`）——全部调中性那一边的同一份。
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import struct
import uuid
import zlib
from typing import TYPE_CHECKING

from ..utils import iso, utcnow
from ..web_platform.tasks import WebTask, WebTaskQueue
from . import flatten, prompts, validate
from .model import (
    FAILED,
    GENERATED_REFERENCE,
    NO_HOUSEHOLD,
    NO_REFERENCE,
    NOT_CONFIGURED,
    POSE_KIND,
    POSE_NEUTRAL,
    READY,
    REFERENCE_CHANGED,
    UNKNOWN,
    CharacterAsset,
    PoseProgress,
    asset_of,
    mark_ready_in,
)

if TYPE_CHECKING:
    from .service import CharacterService

logger = logging.getLogger("petsoul.web.character")

# 姿态任务从中性那一张继承的字段：它们描述的是"这一套"，同一套里每张都一样。
_SET_FIELDS = ("set_id", "pet_id", "user_id", "species", "reference_key", "reference_version", "style_version", "revision")


class PoseService:
    kind = POSE_KIND

    def __init__(self, character: "CharacterService") -> None:
        self.character = character
        self.enabled = False  # 默认关，见模块抬头
        self.compile_prompt = prompts.build_pose_prompt

    # ---- 登记：就在中性姿态发布的那个领取围栏事务里 ----
    def enqueue_in(self, conn: sqlite3.Connection, neutral: dict, neutral_sha256: str) -> list[str]:
        """这一套的中性姿态刚生效：给其余姿态各登记一个任务。**关着就什么都不写**。

        必须和「切 active」在同一个事务里：切过去了、姿态任务却没登记上，这一套就永远补不齐；
        反过来，登记了、切换却回滚了，就会为一套没生效的形象花钱。
        """
        if not self.enabled:
            return []
        stamp = iso(utcnow())
        task_ids = []
        for pose in prompts.EXTRA_POSES:
            if not prompts.pose_supported(neutral["species"], pose):
                continue
            asset_id = f"pc-{uuid.uuid4().hex[:12]}"
            payload = {**{key: neutral[key] for key in _SET_FIELDS}, "asset_id": asset_id, "pose": pose,
                       "source_asset_id": neutral["asset_id"], "source_sha256": neutral_sha256}
            dedupe = (f"character:{neutral['pet_id']}:{pose}:{neutral['reference_version']}:"
                      f"{neutral['style_version']}:{neutral['revision']}")
            task, created = self.character.tasks.enqueue_in(conn, POSE_KIND, dedupe, payload, max_attempts=2)
            if created:
                # `reference_digest` 登记时就写：这一张依据的是**同一套中性姿态**的那串字节，不是原照
                conn.execute(
                    "INSERT INTO web_pet_characters (asset_id, set_id, pet_id, user_id, pose, state, task_id, revision, "
                    "reference_key, reference_version, reference_digest, style_version, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?)",
                    (asset_id, neutral["set_id"], neutral["pet_id"], neutral["user_id"], pose, task.task_id,
                     neutral["revision"], neutral["reference_key"], neutral["reference_version"], neutral_sha256,
                     neutral["style_version"], stamp, stamp))
            task_ids.append(task.task_id)
        return task_ids

    # ---- 执行 ----
    def precheck(self, task: WebTask) -> bool:
        """领取时的早停：主人原照换了就不执行。与中性姿态**同一道、读同一列**；其余复核在 `_render` 里。"""
        return self.character.precheck(task)

    def run_claimed(self, task: WebTask, claim, queue: WebTaskQueue) -> None:
        self.character._run_claimed(task, claim, queue, self._render, self._publish_in)

    def _render(self, task: WebTask, *, attempt: int) -> tuple:
        character = self.character
        payload = task.payload
        # 自动重试：可能已经发出 → 不重发；已付费成功、只是没写进去 → 认领那张图（与中性姿态同一道 `_resume`）。
        # 认领到的图照样要过发布时那道 `_stale_in`（active 还是不是这一套等），**只是不再预占、不再发送**。
        if task.last_error:
            resumed = character._resume(task)
            if resumed is not None:
                return resumed
        if not character.available():
            return None, NOT_CONFIGURED
        source, refused = self._source(payload)
        if refused is not None:
            return None, refused  # 全部在预占之前：0 预占、0 发送
        try:
            flat, _gray = flatten.flatten(source)
        except (ValueError, struct.error, zlib.error):
            # 字节刚核过、发布时也过了校验，走到这里说明解码器与文件之间有我没想到的情况——**不发**
            logger.warning("character pose source undecodable task=%s", task.task_id)
            return None, validate.UNDECODABLE
        prompt = self.compile_prompt(payload["species"], payload["pose"], tuple(character.appearance_tags_of(payload["pet_id"])))
        return character._draw(task, attempt, prompt, (flat, "image/png"), prompts.POSE_CANVAS[payload["pose"]])

    def _stale_in(self, conn: sqlite3.Connection, payload: dict) -> str | None:
        """这一张依据的东西还在不在。执行前、发布前**各问一次这同一份判定**，返回原因码或 None。

          - 主人原照没换（姿态的身份最终来自原照，CR「换参考后旧结果不得发布」）；
          - 宠物仍属于某个家庭（没有家的宠物，角色不属于任何人）；
          - active 还是这一套（旧套在途的姿态，发布前核到 active 已换即作废）。
        """
        current, generated = self.character._reference_of(conn, payload["pet_id"])
        if not current:
            return NO_REFERENCE
        if current != payload["reference_key"]:
            return REFERENCE_CHANGED
        if generated:
            return GENERATED_REFERENCE
        if not self.character._in_household(conn, payload["pet_id"]):
            return NO_HOUSEHOLD
        active = conn.execute("SELECT set_id, revision FROM web_pet_character_active WHERE pet_id = ?",
                              (payload["pet_id"],)).fetchone()
        if active is None or active["set_id"] != payload["set_id"] or int(active["revision"]) != int(payload["revision"]):
            return REFERENCE_CHANGED
        return None

    def _source(self, payload: dict) -> tuple[bytes | None, str | None]:
        """核完 `_stale_in`，再读出同一套中性姿态的字节，**现算 sha256** 与登记时绑定的值比——不信库里记的那一列。"""
        character = self.character
        with character.storage.connect() as own:
            refused = self._stale_in(own, payload)
            row = own.execute("SELECT rel_path, sha256 FROM web_pet_characters "
                              "WHERE asset_id = ? AND set_id = ? AND pose = ? AND state = 'ready'",
                              (payload["source_asset_id"], payload["set_id"], POSE_NEUTRAL)).fetchone()
        if refused is not None:
            return None, refused
        if row is None or not row["rel_path"] or row["sha256"] != payload["source_sha256"]:
            return None, REFERENCE_CHANGED
        path = (character.root / row["rel_path"]).resolve()
        try:
            path.relative_to(character.root.resolve())
            data = path.read_bytes()
        except (ValueError, OSError):
            return None, NO_REFERENCE
        if hashlib.sha256(data).hexdigest() != payload["source_sha256"]:
            return None, REFERENCE_CHANGED  # 文件在发布之后被换过：不认
        return data, None

    def _publish_in(self, conn: sqlite3.Connection, task: WebTask, rendered: tuple) -> None:
        """发布前再问一次 `_stale_in`，然后只把这一行落成 ready。**不切 active**：这一套早已生效。"""
        payload = task.payload
        refused = self._stale_in(conn, payload)
        if refused is not None:
            # 图已经画出来、费用也按实际发出的次数结算过——不发布的是"把它拿给主人看"
            logger.info("character pose not published task=%s reason=%s", task.task_id, refused)
            self.character._fail_in(conn, payload["asset_id"], refused)
            return
        mark_ready_in(conn, payload["asset_id"], rendered, payload["source_sha256"], iso(utcnow()))

    # ---- 纯读 ----
    def view_in(self, conn: sqlite3.Connection, set_id: str) -> tuple[tuple[CharacterAsset, ...], tuple[PoseProgress, ...]]:
        """active 那一套里的其余姿态：(已就绪的资产, 每个姿态的进度)，按 `EXTRA_POSES` 的顺序。**绝不触发生成。**"""
        character = self.character
        order = {pose: index for index, pose in enumerate(prompts.EXTRA_POSES)}
        rows = sorted(conn.execute("SELECT * FROM web_pet_characters WHERE set_id = ? AND pose != ?",
                                   (set_id, POSE_NEUTRAL)).fetchall(),
                      key=lambda row: order.get(row["pose"], len(order)))
        ready = tuple(asset_of(row, character.url(row["asset_id"])) for row in rows if row["state"] == READY)
        progress = tuple(
            PoseProgress(row["pose"],
                         UNKNOWN if row["state"] == FAILED and character._unconfirmed_attempt(row["task_id"], conn) else row["state"],
                         row["reason"], row["task_id"])
            for row in rows)
        return ready, progress
