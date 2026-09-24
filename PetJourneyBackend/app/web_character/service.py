"""世界角色：照片上传成功 → 同事务自动排队 → 编译 → 生图 → 校验 → 原子发布 → 家园纯读。

CR-PLAYER-CHARACTER-01 的后端闭环。**正常路径主人不点"开始生成"、也不逐张确认**；
「调整形象」是可选操作。原照片始终是身份参考，**永不被角色覆盖**。

**逐次授权询问已取消**（用户 2026-09-23 直接决定；计划文档「上传处说明照片会用于准备专属形象；
按图片服务的新策略自动处理，不另设家庭生图许可」）。本模块里 `generated_photos` 那道闸已摘除。
**取消的是「询问」，不是保护**——下面这些一条都没动：额度与每宠上限、费用与账本、幂等与恢复、
`unknown` 不自动重试、越权读挡下、换参考后旧结果不得发布。
原先那道许可顺带承担的**归属判断**单列成 `_in_household`：没有家的宠物不生成，
因为那样的角色不属于任何人，也没人有权读它。

### 四条硬约束，实现位置都标在下面

  - **GET 不出图**：`view_in` 只读，不排队、不调供应商。家园每次渲染都会打那条路由，
    它要是能触发生成，刷新页面就是在烧钱。
  - **重启不重发**：`_unconfirmed_attempt` 看上一次的额度预占停没停在 `reserved/unknown/expired`，
    停在那儿就说明很可能已经发出去了，恢复回来也不重发。
  - **unknown 不自动重试**：`UNCONFIRMED` 在 `NO_RETRY_REASONS` 里，任务直接进终态，
    要重来只能由主人显式发起。
  - **换参考或撤权后旧结果不得发布**：发送前、发布前各复核一次；发布走
    `WHERE excluded.revision > 现有 revision` 的条件 upsert，**过期任务在 SQL 层就覆盖不了新形象**。

### 额度

全局那一层与插画链路**共用 `provider:image:daily`**（那是生图供应商本身的每日上限，两条链路花同一份钱）；
每宠那一层是单独的 `pet:<id>:character`。`reserve` / `settle` **默认就接上**，不是"组合根接了才有"。

### 批次二：其余五个姿态（`poses.py`）

中性姿态发布、并且 active **真的切到这一套**时，在同一个事务里给其余姿态登记任务；它们以**同一套已生效的中性姿态**为参考
（压到灰底上再发），发布时不切 active。开关 `poses.enabled` **默认关**（用户 2026-09-24 决定），关着时行为与批次一相同。
预占、发请求、校验、落盘走同一段 `_draw`，领取围栏里的骨架走同一段 `_run_claimed`——两种任务不各写一份。

### 透明这件事，这里不含糊

角色调用 `render(..., background="transparent")` **按调用**请求透明底（照片链路共用同一个适配器但不传，画面照常有背景）。
**请求了不等于拿到了**，所以本服务**自己验**（`validate.inspect`），不过就不发布，并把三种原因分开记：

  - 适配器**没请求**透明（能力标记为假，如 Seedream）→ `transparency_not_requested`：改参数或换实现；
  - 请求了，拿回来**不透明** → `opaque_background`：报能力缺失；
  - 请求了，拿回来**把棋盘格画进了 RGB** → `checkerboard_drawn`：alpha 在上游产出过、被传输压平了，改响应格式/端点。

`transparency_requested` 由装配从适配器的 `requests_transparent_background` 读出，**不猜**。
GPT 这一侧的透传是**实测过的**（P 2026-09-23，用户授权，各 n=1，有对照），不是照文档加的；
单价未知、账单未核、产品链路尚未产出过任何一张。
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import uuid
from pathlib import Path
from typing import Callable

from ..storage import JourneyStorage
from ..utils import iso, utcnow
from ..web_platform import paid_result
from ..web_platform.budget import BudgetLedger, BudgetLimit
from ..web_platform.tasks import WebTask, WebTaskQueue, run_once
from . import prompts, validate
from .model import (
    ALREADY_QUEUED,
    ATTEMPTS_EXHAUSTED,
    NOT_SENT_REASONS,
    UNKNOWN_REASONS,
    BUDGET_DENIED,
    FAILED,
    GENERATED_REFERENCE,
    KIND,
    NO_HOUSEHOLD,
    NO_REFERENCE,
    NO_RETRY_REASONS,
    ABSENT,
    NOT_CONFIGURED,
    POSE_KIND,
    POSE_NEUTRAL,
    PROVIDER_MISSING,
    QUEUED,
    READY,
    REFERENCE_CHANGED,
    RUNNING,
    SPECIES_UNSUPPORTED,
    TRANSPARENCY_NOT_REQUESTED,
    UNCONFIRMED,
    UNKNOWN,
    CharacterView,
    asset_of,
    mark_ready_in,
)
from .id_photo import IdPhotoService
from .poses import PoseService

logger = logging.getLogger("petsoul.web.character")

# `NOT_SENT_REASONS` / `UNKNOWN_REASONS` 定义在 `model.py`（`NO_RETRY_REASONS` 要用它们），
# 这里只 import，**不另抄一份**。判定函数本身只有一处：`web_providers/images.py::failure_reason`。
# "可能已经发出"的那几种预占状态，与插画链路共用 `paid_result.MAYBE_SENT` 这一份。
UNCONFIRMED_RESERVATION_STATUSES = paid_result.MAYBE_SENT
# 供应商可自动重试的那一类（连不上、被限流）：换个时间可能就成了。其余一律进终态。
RETRYABLE = frozenset({"provider_error"})


class CharacterService:
    kind = KIND

    def __init__(self, storage: JourneyStorage, media_root: Path, tasks: WebTaskQueue, *,
                 per_pet_daily: int = 0, global_daily: int = 0) -> None:
        self.storage = storage
        self.root = Path(media_root)
        self.tasks = tasks
        self.illustrator = None  # web_providers.Illustrator
        # 适配器**真的会把 `background` 发出去**吗。**默认 False**——不声明就是不支持，不猜。
        # 装配从 `illustrator.requests_transparent_background` 读出（GPT 为真，Seedream 为假）。
        self.transparency_requested = False
        self.character_of: Callable[[str], tuple[str, str, str | None] | None] = lambda pet_id: None
        self.reference_photo_of: Callable[[str], tuple[bytes, str] | None] = lambda pet_id: None
        # 身份来源。**只接受主人原照或已核实的真实档案**：拿我们自己画的基准照当身份源，
        # 会把"像不像它"锁死在我们画的那张脸上，而角色是后续所有场景的长期依据（P 规范第 36 行）。
        self.reference_origin_of: Callable[[str], str | None] = lambda pet_id: None
        self.appearance_tags_of: Callable[[str], tuple[str, ...]] = lambda pet_id: ()
        # 提示词编译。**P 的角色用途到位后只换这一处**，别处不用动。
        self.compile_prompt: Callable[..., str] = prompts.build_character_prompt
        ledger = BudgetLedger(storage)
        self.ledger = ledger

        def reserve(operation_id: str, pet_id: str, units: int):
            # **全局那一层必须和插画链路共用 `provider:image:daily`**：它代表生图供应商本身的每日上限，
            # 两条链路花的是同一份钱。我第一版用了 `provider:image:character` —— 那等于给角色开了一条
            # 不计入总账的旁路，配了上限也拦不住它（P 指出我注释里的事实错误时顺带查出来的）。
            #
            # 每宠那一层**刻意分开**成 `pet:<id>:character`：角色是一次性的身份资产（同一张参考照只画一次），
            # 与"主人反复点重画"的插画不是一回事。分开的代价说清楚——**一只宠物在两条车道上各自能花到
            # 每宠上限，合起来是配置值的两倍**。这是有意的取舍，不是漏算：
            # 一只把插画额度用光的宠物，不该因此连自己的形象都没有。
            limits = [BudgetLimit("provider:image:daily", global_daily)] if global_daily else []
            if per_pet_daily:
                limits.append(BudgetLimit(f"pet:{pet_id}:character", per_pet_daily))
            return ledger.reserve(operation_id, provider="image", purpose="character", subject_scope=f"pet:{pet_id}",
                                  units=units, limits=limits)

        # 上限取值与插画链路同源（`web_image_daily_cap` / `web_image_per_pet_daily_cap`，计量表接上了以它为准），
        # 由 `install_character_service` 读配置传进来。**0 表示该层不限**，沿用既有约定——
        # 我第一版在这里自己编了 4 / 200 两个默认值，那是给角色单独发明了一套没人配过的政策，
        # 对运维来说是"配了上限却拦不住、没配上限反而有"的惊吓。
        self.reserve: Callable[..., object] | None = reserve
        self.settle: Callable[..., None] | None = lambda permit, outcome, actual_units=None: ledger.settle(
            permit, outcome, actual_units=actual_units)
        # 批次二的五个姿态（`poses.py`）。**开关默认关**：关着时一个姿态任务都不登记、也不领取。
        self.poses = PoseService(self)
        # 证件照（`id_photo.py`，用户 2026-09-24 定：新宠物自动生成、默认开）。它的额度车道单独算，上限取值与这里同源。
        self.per_pet_daily, self.global_daily = per_pet_daily, global_daily
        self.id_photo = IdPhotoService(self)
        # **证件照任务不由本服务的 `run_pending` 领**（那会打乱只领角色任务的用例与合同）：生图泵照这张表顺带泵它。
        self.pumped_with = (self.id_photo,)

    # ---- 基本 ----
    def available(self) -> bool:
        return self.illustrator is not None and bool(getattr(self.illustrator, "available", False))

    @staticmethod
    def url(asset_id: str) -> str:
        return f"/api/v1/web/media/characters/{asset_id}"

    @staticmethod
    def _in_household(conn: sqlite3.Connection, pet_id: str) -> bool:
        """这只宠物此刻还属于某个家庭吗。**在调用方的连接上读**，不另开。

        它**不是**授权闸（用户 2026-09-23 已决定取消逐次询问，计划文档 63 行「不另设家庭生图许可」）。
        它是归属闸：没有家的宠物，生成出来的角色不属于任何人，也没有任何人有权读它
        （`routers/web/character.py` 的三条路由都走 `require_pet`，无家即无人可授权）。
        原先那道 `generated_photos_in` 顺带承担了这件事——摘授权时**不能把它一起摘掉**。

        直接读列、不走注入钩子：这是围栏，钩子没接线会静悄悄变成永远为真的假闸。
        """
        return conn.execute("SELECT 1 FROM web_household_pets WHERE pet_id = ?", (pet_id,)).fetchone() is not None

    @staticmethod
    def _reference_of(conn: sqlite3.Connection, pet_id: str) -> tuple[str | None, bool]:
        """这一刻库里那张原照：(photo_ref, 是不是我们自己生成的)。

        直接读列、不走注入钩子：这是**围栏**，钩子没接线时会静悄悄变成"永远相等"的假闸——
        那比没有闸更坏（看起来有一道门，其实永远不触发）。
        """
        row = conn.execute("SELECT photo_ref, photo_generated FROM web_pet_profiles WHERE pet_id = ?", (pet_id,)).fetchone()
        return (None, False) if row is None else (row["photo_ref"], bool(row["photo_generated"]))

    @staticmethod
    def _reference_version_in(conn: sqlite3.Connection, pet_id: str, reference_key: str, now: str) -> int:
        """给这只宠物的每一张参考照一个单调递增的整数版本。同一张照片重复问拿回同一个号。

        契约要的 `source_reference_version` 是整数（比大小就能判"是不是换过照片"），
        而 `web_pet_profiles.photo_ref` 是个 uuid 文件名，比不出先后，所以在这里建号。
        """
        row = conn.execute("SELECT version FROM web_pet_character_references WHERE pet_id = ? AND reference_key = ?",
                           (pet_id, reference_key)).fetchone()
        if row is not None:
            return int(row["version"])
        nxt = conn.execute("SELECT COALESCE(MAX(version), 0) + 1 AS n FROM web_pet_character_references WHERE pet_id = ?",
                           (pet_id,)).fetchone()["n"]
        conn.execute("INSERT INTO web_pet_character_references (pet_id, reference_key, version, first_seen_at) VALUES (?, ?, ?, ?)",
                     (pet_id, reference_key, int(nxt), now))
        return int(nxt)

    # ---- 自动触发（上传成功的那个事务里）----
    def request_in(self, conn: sqlite3.Connection, pet_id: str, user_id: str, species: str,
                   reference_key: str | None, *, now=None) -> str | None:
        """在**调用方的写事务里**登记一次角色任务：不自己开连接、不 BEGIN、不提交、不联网。

        必须和"照片落库"同生共死：另开连接排队的话，上传那一步回滚了、队列里却留下一张要花钱的图。
        这是 COORD-A-ATOMIC 那批修过的同型缺陷，不重犯。

        前置条件不满足就**什么都不写**（返回 None），不落一条假的 `queued`——
        为什么没排上由 `view_in` 读时现算，状态永远是当下的真话，不会停在一条过时的记录上。
        """
        if not reference_key or not self.available() or not prompts.supported(species):
            return None
        _, generated = self._reference_of(conn, pet_id)
        if generated:
            return None  # 只有我们自己画的基准照：不能当身份源
        if not self._in_household(conn, pet_id):
            return None  # 没有家的宠物：角色不属于任何人，也没人有权读它
        stamp = iso(now or utcnow())
        version = self._reference_version_in(conn, pet_id, reference_key, stamp)
        revision = int(conn.execute("SELECT COALESCE(MAX(revision), 0) + 1 AS n FROM web_pet_characters WHERE pet_id = ?",
                                    (pet_id,)).fetchone()["n"])
        asset_id, set_id = f"pc-{uuid.uuid4().hex[:12]}", f"cs-{uuid.uuid4().hex[:12]}"
        payload = {"asset_id": asset_id, "set_id": set_id, "pet_id": pet_id, "user_id": user_id, "species": species,
                   "pose": POSE_NEUTRAL, "reference_key": reference_key, "reference_version": version,
                   "style_version": prompts.STYLE_VERSION, "revision": revision}
        dedupe = f"character:{pet_id}:{POSE_NEUTRAL}:{version}:{prompts.STYLE_VERSION}:{revision}"
        task, created = self.tasks.enqueue_in(conn, KIND, dedupe, payload, max_attempts=2, now=now)
        if not created:
            return task.task_id  # 同一张参考、同一轮次重复登记：拿回同一张任务，不多排（多排就是多花一次钱）
        conn.execute(
            "INSERT INTO web_pet_characters (asset_id, set_id, pet_id, user_id, pose, state, task_id, revision, "
            "reference_key, reference_version, style_version, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?)",
            (asset_id, set_id, pet_id, user_id, POSE_NEUTRAL, task.task_id, revision, reference_key, version,
             prompts.STYLE_VERSION, stamp, stamp))
        return task.task_id

    # ---- 纯读 ----
    def view(self, pet_id: str, conn: sqlite3.Connection | None = None) -> CharacterView:
        if conn is not None:
            return self.view_in(conn, pet_id)
        with self.storage.connect() as own:
            return self.view_in(own, pet_id)

    def view_in(self, conn: sqlite3.Connection, pet_id: str) -> CharacterView:
        """**绝不触发生成。** 有 `active` 就给 `active`，哪怕在建那一版正在失败——旧形象不因新任务出错而消失。

        `active` 与 `candidate` **都只看中性姿态那一行**：一套里有了其余姿态之后，
        原先的 `ORDER BY c.pose LIMIT 1` 会按字母序拿到 `eating`（还可能是在排队的那张），
        「最近一行」也会是某个姿态而不是中性姿态——综合状态就会跟着那个姿态走。
        其余姿态单列在 `extras`／`poses` 里，**只取 active 那一套**。
        """
        active_row = conn.execute(
            "SELECT c.*, a.published_at AS published_at FROM web_pet_character_active a "
            "JOIN web_pet_characters c ON c.set_id = a.set_id WHERE a.pet_id = ? AND c.pose = ? LIMIT 1",
            (pet_id, POSE_NEUTRAL)).fetchone()
        active = asset_of(active_row, self.url(active_row["asset_id"])) if active_row else None
        published_at = active_row["published_at"] if active_row else None
        extras, poses = self.poses.view_in(conn, active_row["set_id"]) if active_row else ((), ())
        blocked = self.blocked_reason_in(conn, pet_id)
        latest = conn.execute(
            "SELECT * FROM web_pet_characters WHERE pet_id = ? AND pose = ? ORDER BY revision DESC, rowid DESC LIMIT 1",
            (pet_id, POSE_NEUTRAL)).fetchone()
        candidate = None
        if latest is not None and (active_row is None or latest["asset_id"] != active_row["asset_id"]):
            candidate = asset_of(latest, None)  # 在建的那一版没有可读地址：还没发布，给了也读不到
        if candidate is not None:
            state = candidate.state
            if state == FAILED and self._unconfirmed_attempt(latest["task_id"], conn):
                state = UNKNOWN  # 可能已经发出、结果未确认。**不能说成"没生成"**，那会让主人再付一次费
            return CharacterView(state, latest["reason"], active, candidate, published_at, blocked, extras, poses)
        if active is not None:
            return CharacterView(READY, None, active, None, published_at, blocked, extras, poses)
        return CharacterView(ABSENT, blocked, None, None, None, blocked)

    def blocked_reason_in(self, conn: sqlite3.Connection, pet_id: str) -> str | None:
        """从来没有过任务时，**读时现算**为什么没有。比落一条过时的失败记录诚实。"""
        reference_key, generated = self._reference_of(conn, pet_id)
        if not reference_key:
            return NO_REFERENCE
        if generated:
            return GENERATED_REFERENCE
        character = self.character_of(pet_id)
        if character is None or not prompts.supported(character[0]):
            return SPECIES_UNSUPPORTED
        if not self._in_household(conn, pet_id):
            return NO_HOUSEHOLD
        return None if self.available() else PROVIDER_MISSING

    def media_path(self, asset_id: str) -> tuple[Path, str, str] | None:
        """(文件, content_type, pet_id)。**裁定归路由**——这里只解析路径，不做可见性判断。"""
        with self.storage.connect() as conn:
            row = conn.execute("SELECT pet_id, rel_path, content_type FROM web_pet_characters "
                               "WHERE asset_id = ? AND state = 'ready'", (asset_id,)).fetchone()
        if row is None or not row["rel_path"]:
            return None
        path = (self.root / row["rel_path"]).resolve()
        try:
            path.relative_to(self.root.resolve())
        except ValueError:
            return None
        return (path, row["content_type"] or "image/png", row["pet_id"]) if path.is_file() else None

    # ---- 可选的「调整形象」----
    def regenerate(self, pet_id: str, user_id: str) -> tuple[bool, str, str | None]:
        """主人显式发起。返回 (是否接受, 状态, 任务号或原因)。

        **已有在建任务就拒绝**，不再排一个——重复点击、丢回执、刷新都落在这条上。
        `unknown` 下也走这里：必须是主人显式发起才算新的付费尝试，后台不自己补发。
        """
        from ..web_platform.uow import unit_of_work

        with unit_of_work(self.storage) as conn:
            view = self.view_in(conn, pet_id)
            if view.state in (QUEUED, RUNNING):
                return (False, view.state, ALREADY_QUEUED)
            character = self.character_of(pet_id)
            reference_key, _ = self._reference_of(conn, pet_id)
            species = character[0] if character else ""
            task_id = self.request_in(conn, pet_id, user_id, species, reference_key)
            if task_id is None:
                return (False, view.state, self.blocked_reason_in(conn, pet_id) or NOT_CONFIGURED)
            return (True, QUEUED, task_id)

    # ---- 执行 ----
    def precheck(self, task: WebTask) -> bool:
        """这个任务依据的**来源版本**是否仍然有效：主人换了照片，这一次就不该再执行。

        `_render` 里的 `_reference_gate` 是权威那一道（它给得出具体原因码）；这里只是领取时的早停，
        省掉一次没有意义的执行。两道**读的是同一列**，不会各说各话。

        原先这里读的是生成授权（`opted_in`）——用户 2026-09-23 决定取消逐次询问后那道闸已摘除。
        """
        with self.storage.connect() as own:
            current, _ = self._reference_of(own, task.payload["pet_id"])
        return bool(current) and current == task.payload["reference_key"]

    def run_pending(self, worker_id: str = "web-characters", limit: int = 5) -> int:
        """中性姿态与其余姿态**同一个泵**：组合根不用为批次二多接一行。

        开关关着时**不领取**姿态任务——关掉就是不再为它花钱；已经排上的留在队里，
        状态照实显示为 `queued`，打开后再执行（执行前的复核会把过时的那些作废）。
        """
        handlers = {KIND: self, POSE_KIND: self.poses} if self.poses.enabled else {KIND: self}
        handled = 0
        for _ in range(limit):
            task = run_once(self.tasks, handlers, worker_id)
            if task is None:
                break
            handled += 1
            if task.status in ("failed", "superseded"):
                # superseded＝领取后 precheck 发现主人已经换了照片。展示状态也要跟着落定，
                # 否则家园会永远停在"正在准备 TA 的形象"。
                # failed 走到这里只剩一种情形：可重试的失败把次数用完了（具体哪一次为什么，不猜）。
                # 已经写过具体原因的那些行状态已是 failed，下面的 UPDATE 不会命中它们。
                with self.storage.connect() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    self._fail_in(conn, task.payload["asset_id"],
                                  REFERENCE_CHANGED if task.status == "superseded" else ATTEMPTS_EXHAUSTED)
        return handled

    def run_claimed(self, task: WebTask, claim, queue: WebTaskQueue) -> None:
        self._run_claimed(task, claim, queue, self._render, self._publish_in)

    def _run_claimed(self, task: WebTask, claim, queue: WebTaskQueue, render, publish_in) -> None:
        """付费调用在事务外发；写资产、切生效版本、完成任务在**同一个领取围栏事务**里。中性与其余姿态共用这副骨架。

        被别的进程接手或已撤回时队列抛 `StaleClaim`，这次结果整批作废：不写库、不切 active
        （多画的那张图只留在磁盘上，没有记录引用它）。
        """
        with queue.fenced(claim, complete=False) as conn:
            conn.execute("UPDATE web_pet_characters SET state = 'running', updated_at = ? WHERE asset_id = ? AND state = 'queued'",
                         (iso(utcnow()), task.payload["asset_id"]))
        rendered, refused = render(task, attempt=claim.claim_generation)
        if rendered is None:
            with queue.fenced(claim, complete=False) as conn:
                self._fail_in(conn, task.payload["asset_id"], refused)
            queue.fail_claim(claim, f"character {refused}", retryable=refused not in NO_RETRY_REASONS)
            return
        with queue.fenced(claim) as conn:
            publish_in(conn, task, rendered)

    def _render(self, task: WebTask, *, attempt: int) -> tuple:
        """中性姿态：返回 ((相对路径, 图片, 校验结论) 或 None, 不发布的原因 或 None)。可自动重试的失败往外抛。

        **超时那一路的正确性靠两道闸串起来，不是一道**（P 追这条路径时问出来的，写在这里免得下一个人只看一边）：

          1. `"timeout"` **不在** `NO_RETRY_REASONS` 里 ⇒ `fail_claim(retryable=True)` ⇒ 任务会被排回去；
          2. 排回来时 `task.last_error` 已置，下面这道 `_resume`（`paid_result.resume`）从预占表读到
             `reserved/unknown/expired` ⇒ 返回 `UNCONFIRMED` ⇒ **在预占之前短路，0 发送 0 计费**；
             读到 `settled ＋ succeeded`（付过钱、只是没写进去）⇒ **凭小票认领那张图**，同样 0 预占 0 发送；
             而 `UNCONFIRMED` 在 `NO_RETRY_REASONS` 里，于是进终态。

        代价是多走一个空任务周期，行为是对的。**危险在于这个依赖是单向可见的**：
        谁动了第 2 道闸，超时立刻变成二次付费，而第 1 道那边一个字都没改，从那边看不出来。
        要拆的话请把 `"timeout"`/`"unconfirmed"` 一并加进 `NO_RETRY_REASONS`，让第 1 道自己就拦得住。
        """
        payload = task.payload
        pet_id = payload["pet_id"]
        # 自动重试：上一次可能已经发出、结果没确认 → **不重发**；上一次已付费成功、只是没写进去 → **认领那张图**。
        if task.last_error:
            resumed = self._resume(task)
            if resumed is not None:
                return resumed
        if not self.available():
            return None, NOT_CONFIGURED
        gate = self._reference_gate(payload)
        if gate is not None:
            return None, gate  # 全部在预占之前：0 预占、0 发送
        reference = self.reference_photo_of(pet_id)
        if reference is None:
            return None, NO_REFERENCE
        prompt = self.compile_prompt(payload["species"], tuple(self.appearance_tags_of(pet_id)))
        return self._draw(task, attempt, prompt, reference, prompts.CANVAS)

    def _draw(self, task: WebTask, attempt: int, prompt: str, reference, size: str) -> tuple:
        """预占 → 发请求 → 按实结算 → 校验 → 落盘。中性与其余姿态**共用这一段**，只有参考、提示词、画幅不同。

        返回值与 `_render` 相同；可自动重试的供应商失败往外抛。调用方负责在它**之前**做完全部不花钱的判断。
        """
        from ..web_providers import ImageUnavailable

        payload = task.payload
        pet_id, user_id = payload["pet_id"], payload["user_id"]
        permit = self.reserve(f"character:{task.task_id}:{attempt}", pet_id, 1) if self.reserve else None
        if permit is not None and getattr(permit, "status", None) != "reserved":
            logger.info("character budget denied task=%s reason=%s", task.task_id, getattr(permit, "reason", "unknown"))
            return None, BUDGET_DENIED
        try:
            # 透明底**按调用**请求：照片链路共用同一个适配器，但它不传这个参数，画面照常有背景。
            image = self.illustrator.render(prompt, reference, size=size, background="transparent")
        except ImageUnavailable as exc:
            self._settle_calls(permit, exc.reason, 0 if exc.reason in NOT_SENT_REASONS else 1)
            if exc.reason in RETRYABLE:
                raise  # 确定没受理、换个时间可能就成：交给任务重试
            return None, exc.reason
        self._settle_calls(permit, "succeeded", 1)
        verdict = validate.inspect(image.image_bytes, image.mime_type)
        if not verdict.ok:
            logger.info("character rejected task=%s reason=%s", task.task_id, verdict.reason)
            return None, self._alpha_reason(verdict.reason)
        folder = self.root / "characters" / user_id
        folder.mkdir(parents=True, exist_ok=True)
        stem = f"characters/{user_id}/{payload['asset_id']}-{attempt}"
        rel = f"{stem}.png"
        (self.root / rel).write_bytes(image.image_bytes)
        # 小票：发布若失败，自动重试凭它认领这张已付费的图，不再付第二次（`paid_result`）
        paid_result.write_receipt(self.root, stem, rel, image)
        return (rel, image, verdict), None

    def _resume(self, task: WebTask) -> tuple | None:
        """自动重试之前问上一次（`paid_result.resume`）。返回 None＝照常执行；否则就是这一次的 `(rendered, reason)`。

        中性站姿与其余姿态共用：两者落盘路径同形（`characters/<user>/<asset_id>-<代数>.png`）。
        认领到的图**再过一遍校验**：小票对得上、图却过不了，说明文件在两次之间被换过——不认，也不重付。
        """
        payload = task.payload
        resumed = paid_result.resume(self.storage, f"character:{task.task_id}:", self.root,
                                     f"characters/{payload['user_id']}/{payload['asset_id']}-{{attempt}}")
        if resumed is None:
            return None
        verdict = validate.inspect(resumed.image.image_bytes, resumed.image.mime_type) if resumed.image else None
        if verdict is None or not verdict.ok:
            logger.info("character not resent task=%s previous=%s", task.task_id, resumed.blocked or "reclaimed_invalid")
            return None, UNCONFIRMED
        logger.info("character reclaimed paid result task=%s attempt=%s", task.task_id, resumed.attempt)
        return (resumed.rel, resumed.image, verdict), None

    def _reference_gate(self, payload: dict) -> str | None:
        """执行这一刻重新读参考照：换过、或只剩我们自己画的基准照，就不发。返回原因码或 None。"""
        with self.storage.connect() as own:
            current, generated = self._reference_of(own, payload["pet_id"])
        if not current:
            return NO_REFERENCE
        if current != payload["reference_key"]:
            return REFERENCE_CHANGED  # 排队期间主人换了照片：这一版作废
        if generated:
            return GENERATED_REFERENCE
        origin = self.reference_origin_of(payload["pet_id"])
        if origin == "original_companion":
            return GENERATED_REFERENCE
        return None if origin in ("owner_original", "real_archive") else NO_REFERENCE

    def _alpha_reason(self, reason: str | None) -> str:
        """把三种"拿回来不透明"分开记——处置完全不同（P 规范 4.2 第 6 条）：

          - **没请求**（适配器不发 `background`）→ `transparency_not_requested`：改参数或换实现。
            这一条**优先于棋盘格**：没请求透明却画出了方格，那是模型自己画的，先该问的是"你请求了吗"；
          - 请求了、画了棋盘格 → `checkerboard_drawn`：alpha 在上游有过、被压平了，改响应格式／端点；
          - 请求了、纯不透明 → `opaque_background`：参数被忽略，报能力缺失。

        兜底落在 `undecodable` 而不是新造一个码：`Verdict(ok=False)` 按构造一定带原因，
        所以这条兜底现在到不了。但万一将来有人加了个忘记填原因的返回路径，
        落在**已经在对外码表里的码**上，前端至少还有话可说；新造一个码只会让玩家看到原始串。
        """
        opaque = (validate.OPAQUE, validate.NO_ALPHA_CHANNEL, validate.CHECKERBOARD)
        if reason in opaque and not self.transparency_requested:
            return TRANSPARENCY_NOT_REQUESTED
        return reason or validate.UNDECODABLE

    # ---- 结算 ----
    def _settle_calls(self, permit, reason: str, sent: int) -> None:
        """按实际发出的次数结算：一次都没发出才整笔释放**本地预占**（与供应商那边收不收费无关）。"""
        if sent == 0:
            self._settle(permit, "not_sent")
            return
        outcome = "succeeded" if reason == "succeeded" else ("unknown" if reason in UNKNOWN_REASONS else "failed")
        self._settle(permit, outcome, sent)

    def _settle(self, permit, outcome: str, actual_units: int | None = None) -> None:
        if permit is not None and self.settle is not None and getattr(permit, "status", None) == "reserved":
            self.settle(permit, outcome, actual_units)

    def _unconfirmed_attempt(self, task_id: str, conn: sqlite3.Connection | None = None) -> bool:
        """最近一次尝试的额度预占停在 `reserved/unknown/expired` 就算"可能已经发出、结果未确认"。

        读不到账本（锁死、损坏）也按"不确定"处理——**读不到就不敢再发一次**。
        迁移 0050 之前的库没有额度表，返回 False，维持旧行为。
        """
        prefix = f"character:{task_id}:"
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        sql = ("SELECT status FROM web_budget_reservations WHERE operation_id LIKE ? ESCAPE '\\' "
               "ORDER BY CAST(substr(operation_id, ?) AS INTEGER) DESC, rowid DESC LIMIT 1")
        params = (escaped + "%", len(prefix) + 1)
        try:
            if conn is not None:
                row = conn.execute(sql, params).fetchone()
            else:
                with self.storage.connect() as own:
                    row = own.execute(sql, params).fetchone()
        except sqlite3.Error as exc:
            if isinstance(exc, sqlite3.OperationalError) and "no such table" in str(exc).lower():
                return False
            logger.warning("character budget lookup failed task=%s: %s", task_id, type(exc).__name__)
            return True
        return row is not None and row["status"] in UNCONFIRMED_RESERVATION_STATUSES

    # ---- 落定 ----
    def _fail_in(self, conn: sqlite3.Connection, asset_id: str, reason: str | None) -> None:
        """在建那一版落 failed。**已生效的 active 一个字节都不动**——一次调整失败不该破坏旧形象。"""
        # `COALESCE(?, reason)`：说不出新原因时**保留已经记下的那个**，不要用一个 NULL 把它抹掉。
        conn.execute("UPDATE web_pet_characters SET state = 'failed', reason = COALESCE(?, reason), updated_at = ? "
                     "WHERE asset_id = ? AND state IN ('queued', 'running')", (reason, iso(utcnow()), asset_id))

    def _publish_in(self, conn: sqlite3.Connection, task: WebTask, rendered: tuple) -> None:
        """最终复核 → 写资产 → 原子切 active →（开关开着时）登记其余姿态，全在领取围栏这一个事务里。"""
        payload = task.payload
        pet_id = payload["pet_id"]
        current, _ = self._reference_of(conn, pet_id)
        refused = None
        if current != payload["reference_key"]:
            refused = REFERENCE_CHANGED
        elif not self._in_household(conn, pet_id):
            refused = NO_HOUSEHOLD
        if refused is not None:
            # 图已经画出来了、费用也按实际发出的次数结算过——**不发布的是"把它拿给主人看"**，
            # 不是假装什么都没发生。旧 active 继续有效。
            logger.info("character not published task=%s reason=%s", task.task_id, refused)
            self._fail_in(conn, payload["asset_id"], refused)
            return
        digest = mark_ready_in(conn, payload["asset_id"], rendered, self._reference_digest(pet_id), iso(utcnow()))
        # **原子切换 ＋ 过期任务挡在 SQL 层**：条件 upsert 只在 revision 更大时才换过去，
        # 一个慢任务后来才回来，也覆盖不了已经生效的新形象。
        conn.execute(
            "INSERT INTO web_pet_character_active (pet_id, set_id, revision, published_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(pet_id) DO UPDATE SET set_id = excluded.set_id, revision = excluded.revision, "
            "published_at = excluded.published_at WHERE excluded.revision > web_pet_character_active.revision",
            (pet_id, payload["set_id"], payload["revision"], iso(utcnow())))
        # 批次二：**真的切到了这一套**才给其余姿态登记任务（开关关着时 `enqueue_in` 什么都不写）。
        # 条件 upsert 没换过去（更新的一套已经生效）就不登记——为一套不会被看到的形象画五张，是白花钱。
        now_active = conn.execute("SELECT set_id FROM web_pet_character_active WHERE pet_id = ?", (pet_id,)).fetchone()
        if now_active is not None and now_active["set_id"] == payload["set_id"]:
            self.poses.enqueue_in(conn, payload, digest)

    def _reference_digest(self, pet_id: str) -> str | None:
        """这一版依据的那张原照的内容摘要。拿不到就留空，不编。"""
        reference = self.reference_photo_of(pet_id)
        return hashlib.sha256(reference[0]).hexdigest() if reference else None
