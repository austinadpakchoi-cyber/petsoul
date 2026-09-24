"""冒险插画：主人在设置里开启“生成冒险插画”后，冒险事件会排一个生图任务（异步、可重试、失败如实显示）。

- 生图请求只含：宠物物种/名字/性格与冒险场景描述；主人上传过照片的，一并作为角色参考（开关的披露里写明）；
- 画风要求原创动物生活绘本，不出现文字、真实品牌或真人；
- 文件放在私有媒体目录，只有主人能通过鉴权路由读取；失败不影响勋章与故事（规则结算不依赖生图）。
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Callable

from ..storage import JourneyStorage
from ..utils import iso, utcnow
from ..web_platform import paid_result
from ..web_platform.runtime_epochs import versions_in
from ..web_platform.tasks import WebTask, WebTaskQueue, run_once
from ..web_platform.uow import execute_in, unit_of_work
from . import photo_director_bridge as bridge
from .adventures import ADVENTURES, render_story  # 冒险插画按模板不带叮嘱重渲（CR-IMAGE-MEMORY-PURPOSE）
from ..web_photo_director import Readiness
from ..web_travel.journal import reference_for_brief  # 旅行手账：身份参考只认编译时那一张（TRV-03）
# 提示词构造拆在 photo_prompts.py（COORD-A-ATOMIC：给原子登记腾定义数）。
# 这里连带重新导出，历史调用方（app/routers/web/credentials.py、web_journey/guides.py 用 SPECIES_CN）不受影响。
from .photo_prompts import (  # noqa: F401
    EXT,
    SPECIES_CN,
    SPECIES_EN,
    build_journal_prompt,
    build_portrait_prompt,
    build_prompt,
    build_selfie_prompt,
)

logger = logging.getLogger("petsoul.web.illustrations")
KIND = "illustration"
# 确定没受理，可以把**本地账本里的预占整笔释放**：没配置、到了每日上限、被当场拒绝（4xx）、连不上或被限流。
# 这只影响本地额度记账，与供应商那边收不收费、退不退款无关（真实费用一律按“未验证”对待）。
# 注意"没受理"与"适合自动重试"是两件事，后者见 NO_RETRY_REASONS。
NOT_SENT_REASONS = frozenset({"daily_cap", "not_configured", "rejected", "provider_error"})
# 结果不明：timeout＝发出去没等到响应；unconfirmed＝响应已回、生成已受理，之后解析/解码/取图才失败。
# 两种都可能已经计费，保守计入，且不自动重试（判定在 web_providers/images.py 的 failure_reason）
UNKNOWN_REASONS = frozenset({"timeout", "unconfirmed"})
# 恢复时发现上一次可能已经发出、结果没确认（或付过钱的结果找不回来）：同样不重发（见 `paid_result.resume`）
UNCONFIRMED_REASON = "unknown_result"
# 上一次尝试的额度预占停在这些状态，就说明那次很可能已经发出去了：
# reserved＝崩在调用中途还没结算，unknown＝超时，expired＝预占到期都没结算。与角色链路共用 `paid_result` 那一份。
UNCONFIRMED_RESERVATION_STATUSES = paid_result.MAYBE_SENT
# 这几类不排自动重试：如实显示“没画成”／“还没确认”，等主人点“重画”。
# 结果不明的不能重发（可能已经计费）；rejected/not_configured/daily_cap 重发也是同样的结果，白费一次。
# provider_error（连不上、被限流）确定没受理、换个时间可能就成功，所以**不在**这里，仍走自动重试。
# `consent_revoked` 已从这里删除：逐次授权询问取消后（用户 2026-09-23）它不可能再产生。
NO_RETRY_REASONS = (NOT_SENT_REASONS - {"provider_error"}) | UNKNOWN_REASONS | {UNCONFIRMED_REASON}

class IllustrationService:
    def __init__(self, storage: JourneyStorage, media_root: Path, tasks: WebTaskQueue) -> None:
        self.storage = storage
        self.root = media_root
        self.tasks = tasks
        self.illustrator = None  # web_providers.Illustrator
        # 逐次授权询问已取消（用户 2026-09-23），原先的 `opted_in` / `consent_in` 两个接线口已删除（2026-09-24）。
        # 谁以原名把读它们的检查加回来，`test_web_consent_boundary` 与 `test_web_photo_atomic` 的反向用例当场红。
        # 能不能看这只宠物的照片：有效家庭成员（被移除后立即失效）
        self.can_view_pet: Callable[[str, str], bool] | None = None
        self.character_of: Callable[[str], tuple[str, str, str | None] | None] = lambda pet_id: None  # (species, name, personality)
        self.reference_photo_of: Callable[[str], tuple[bytes, str] | None] = lambda pet_id: None
        # 这张参考照是哪来的："owner_original"（主人原照）/ "original_companion"（我们自己画的基准照）。
        # **不知道就返回 None**：目标场景会据此 hold，绝不把来源不明的旧图冒名成主人原照（已向 I 发 CR 要这个来源）。
        self.reference_origin_of: Callable[[str], str | None] = lambda pet_id: None
        # 这次到访/事件**此刻**的代数（B 装配时接到 visit.version 的实读）。没接线时下面那道
        # "排队期间事件被更正过" 的闸是空转的——两边都回读 payload，永远相等。
        self.event_revision_of: Callable[[str], int | None] | None = None
        # 没有照片的伙伴：先生成并保存一张写实“证件照”，之后都以它为参考（返回是否保存成功）
        self.portrait_saver: Callable[[str, bytes, str], bool] | None = None
        # 付费生图的额度预占（装配时注入 A 的 BudgetLedger）：发出调用前预占，调用后按结果结算；没接入时为 None
        self.reserve: Callable[..., object] | None = None
        self.settle: Callable[[object, str], None] | None = None
        # 结果回调：conn 是插画任务的领取围栏事务（为 None 时回调自己开短连接）
        self.on_ready: Callable[..., None] = lambda task_id, url, conn=None: None
        self.on_failed: Callable[..., None] = lambda task_id, conn=None: None
        # 结果不明（可能已被受理，见 outcome_of）。没接线时为 None——那就退回 on_failed，行为与接线前完全一致。
        self.on_unknown: Callable[..., None] | None = None
        # 主人点“重画”、任务真的排回去了：把展示状态改回“处理中”，和重排在同一个事务里（没接线时展示状态不动）。
        self.on_retrying: Callable[..., None] | None = None

    def available(self) -> bool:
        return self.illustrator is not None and bool(getattr(self.illustrator, "available", False))

    @staticmethod
    def url(illustration_id: str) -> str:
        return f"/api/v1/web/media/illustrations/{illustration_id}"

    # ---- 排队（世界事件 sink 调用，事件号去重）----
    def request(self, event) -> str | None:
        journey = event.journey
        if not self.available():  # 逐次授权询问已取消（用户 2026-09-23），只看供应商配没配
            return None
        illustration_id = f"il-{uuid.uuid4().hex[:12]}"
        # **不存 `story`，只存 `adventure_key`**（CR-IMAGE-MEMORY-PURPOSE-2026-09-24 的 A 半）。
        # 冒险故事里可能夹着接待叮嘱（`keepsake_of` → `render_story` 插进"带着你准备的…"那一句），
        # 而那份叮嘱未必授权过 `media_generation`——曾经只授权 `private_chat` 的也照样被拼了进来。
        # 本批**彻底不让任何叮嘱内容进生图**：载荷里连那段文本都不留，发送时按模板**不带叮嘱**重渲（见 `_render`）。
        # 这样任务表里也不会再积攒一份私人叮嘱的副本。
        payload = {"illustration_id": illustration_id, "user_id": journey.user_id, "pet_id": journey.pet_id,
                   "title": event.data.get("title", ""), "adventure_key": event.data.get("adventure_key")}
        task, created = self.tasks.enqueue(KIND, f"illustration:{event.source_event_id}", payload, max_attempts=2)
        if created:
            now = iso(utcnow())
            with self.storage.connect() as conn:
                conn.execute("INSERT OR IGNORE INTO web_illustrations (illustration_id, user_id, pet_id, source_event_id, task_id, status, created_at, updated_at) "
                             "VALUES (?, ?, ?, ?, ?, 'processing', ?, ?)", (illustration_id, journey.user_id, journey.pet_id, event.source_event_id, task.task_id, now, now))
        return task.task_id

    def request_photo(self, user_id: str, pet_id: str, source_key: str, *, place: str, city: str, scene: str,
                      scene_key: str | None = None) -> str | None:
        """写实自拍（明信片、店里的合影）。主人开启“生成照片”且供应商可用时排队；返回任务号。

        自己开事务。要和 visit、photo_taken 事件一起提交，请用 `request_photo_in`。
        `scene_key`：调用方**显式指定**的场景键（cafe / train / home / flight_adventure），照片导演按它选配方；
        不传就没有，导演那边按"缺必需事实"处理，**不猜**。
        """
        with unit_of_work(self.storage) as conn:
            return self.request_photo_in(conn, user_id, pet_id, source_key, place=place, city=city, scene=scene, scene_key=scene_key)

    def request_photo_in(self, conn, user_id: str, pet_id: str, source_key: str, *, place: str, city: str, scene: str,
                         captured_at=None, scene_key: str | None = None, **extras) -> str | None:
        """在**调用方的写事务里**登记一次拍照（COORD-A-ATOMIC 方案 B）：不自己开连接、不 BEGIN、不提交、不联网。

        `captured_at`＝主人按下“拍一张”的那一刻，随 payload 存下来给导演用；
        **不能被任务执行时刻覆写**——worker 什么时候跑是队列的事，和照片拍摄时间无关。
        `source_key` 与 photo_taken 的事件键同源，去重靠它（`dedupe_key = illustration:<source_key>`）。
        """
        return self.request_image_in(conn, user_id, pet_id, source_key, style="selfie", place=place, city=city, scene=scene,
                                     captured_at=iso(captured_at) if captured_at is not None else None, scene_key=scene_key, **extras)

    def request_journal(self, *, user_id: str, pet_id: str, source_key: str, title: str, lines: list[str], city: str) -> str | None:
        """攻略手账图（竖版）。"""
        return self.request_image(user_id, pet_id, source_key, style="journal", title=title, lines=lines, city=city)

    def request_image(self, user_id: str, pet_id: str, source_key: str, *, style: str, **extras) -> str | None:
        """自己开一个写事务登记。SQL 只有 `request_image_in` 那一份，这里是它的包装。"""
        with unit_of_work(self.storage) as conn:
            return self.request_image_in(conn, user_id, pet_id, source_key, style=style, **extras)

    def request_image_in(self, conn, user_id: str, pet_id: str, source_key: str, *, style: str, **extras) -> str | None:
        """在调用方的写事务里登记：任务与插画记录一起提交、一起回滚，**不会出现有任务没记录或反过来**。

        **逐次授权询问已取消**（用户 2026-09-23 直接决定，角色与生活/旅行两类都取消；计划文档
        「上传处说明照片会用于准备专属形象；按图片服务的新策略自动处理，不另设家庭生图许可」）。
        原先这里在**登记时刻**查一次、`_render` 在每次可能付费的发送之前再查一次，两处都已摘除。
        **摘掉的是「询问」，不是别的保护**：额度与每宠上限、幂等、恢复不重发、`unknown` 不自动重试、
        换参考不发布、越权读挡下，一条都没动。

        `extras` 里为 None 的键不写进 payload——“没有这个事实”和“这个事实是 None”要能分得开。
        """
        if not self.available():
            return None
        illustration_id = f"il-{uuid.uuid4().hex[:12]}"
        # source_key 也存进 payload：worker 里的照片导演要用它当事件标识（跨重试不变，进 context_key）。
        # versions＝**登记那一刻**这只宠物的真实语义代数快照；执行时再读一次当前值，两者不一致就是
        # "排队期间授权或 DNA 变了"，导演会据此拒绝。不是自比的假零。
        snapshot = versions_in(conn, pet_id)
        payload = {"illustration_id": illustration_id, "user_id": user_id, "pet_id": pet_id, "style": style,
                   "source_key": source_key,
                   "versions": {"dna": snapshot.dna_version, "privacy": snapshot.privacy_epoch, "activity": snapshot.activity_epoch},
                   **{k: v for k, v in extras.items() if v is not None}}
        task, created = self.tasks.enqueue_in(conn, KIND, f"illustration:{source_key}", payload, max_attempts=2)
        if created:
            now = iso(utcnow())
            conn.execute("INSERT OR IGNORE INTO web_illustrations (illustration_id, user_id, pet_id, source_event_id, task_id, status, created_at, updated_at) "
                         "VALUES (?, ?, ?, ?, ?, 'processing', ?, ?)", (illustration_id, user_id, pet_id, source_key, task.task_id, now, now))
        return task.task_id

    def retry(self, ticket: str) -> str:
        """主人点“重画”：失败的任务按队列规则重排（次数只放宽不清零，领取代数保持单调），插画回到处理中。

        ``ticket`` 是查询入口给出的**重画凭据** `<任务号>#<当时看到的失败尝试次数>`（见各消费者的 `*_retrying`）。
        只传任务号也能用（没有版本围栏的老接法）。

        **三件事在同一个事务里**：任务重排、插画记录、消息/收藏/攻略上的展示状态。任何一步失败就一起回滚，
        不会出现"任务已经重排、页面还显示没画成"，也不会出现"页面转圈、队列里其实没有任务"（包 A 的 CR-A5）。

        返回这次点击**实际发生了什么**，调用方据此给响应，**不能一律当成"新尝试已创建"**：
        - `requeued`：真的排了一次新尝试；
        - `already_queued`：已经在排队或执行中——连点第二次、或两个请求同时点会走到这里；回当前状态，不是新尝试；
        - `stale_attempt`：任务确实又是 failed，但**这次点击对应的是更早那次失败**（中间已经跑过一轮又失败了）。
          这是迟到的重复请求，不能当成新的一次重画；调用方回当前状态并提示刷新，主人看到新失败后重新点是合法的；
        - `not_retryable`：这个任务不能重试（已经画好、已作废，或任务号不存在）——应当明确拒绝。

        **防重复发起的最终保护在这里，不在调用方的查询**：`retry_failed` 的条件更新（状态 ＋ 失败版本）
        和展示状态在同一个写事务里，所以并发的两个请求即使都查到同一个凭据，也只有一方能把任务排回去。
        """
        now = iso(utcnow())
        task_id, _, seen = ticket.partition("#")
        expected = int(seen) if seen.isdigit() else None
        with unit_of_work(self.storage) as conn:
            if self.tasks.retry_failed(task_id, expected_attempts=expected, conn=conn):
                conn.execute("UPDATE web_illustrations SET status = 'processing', updated_at = ? WHERE task_id = ?", (now, task_id))
                if self.on_retrying is not None:
                    self.on_retrying(task_id, conn)
                return "requeued"
            row = conn.execute("SELECT status, attempts FROM web_tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            return "not_retryable"
        if row["status"] in ("queued", "running"):
            return "already_queued"
        return "stale_attempt" if row["status"] == "failed" and expected is not None else "not_retryable"

    # ---- 执行 ----
    kind = KIND

    def precheck(self, task: WebTask) -> bool:
        # 原先这里读生成授权（关掉开关后未开始的任务不再执行）。逐次询问已取消（用户 2026-09-23），
        # 这道早停没有依据了；真正的依据（供应商配没配、参考照还在不在、事件代数变没变）都在 `_render` 里判，
        # 而且那边给得出具体原因码。**不留一个永远为真的假 precheck**，直接如实说"没有可前置检查的东西"。
        return True

    def run(self, task: WebTask) -> None:
        """旧式执行（没有领取令牌时）：生图后自己开事务写结果。任务队列走 run_claimed。"""
        rendered, _ = self._render(task, suffix="", attempt=task.attempts)
        with self.storage.connect() as conn:
            self._commit(task, rendered, conn)

    def run_claimed(self, task: WebTask, claim, queue: WebTaskQueue) -> None:
        """领取围栏内提交：生图（付费外部调用）在事务外；写插画记录、更新消息/收藏/攻略里的图、完成任务在同一个事务里。
        被别的进程接管或已撤回时，队列抛 StaleClaim，这次的结果整批作废：不写库、不发消息（多画的那张图只留在磁盘上，没有记录引用它）。

        不该自动重试的失败（没配置、到了每日上限、超时结果不明）：展示状态与任务终态一起落定为"没画成"，
        由主人点"重画"再发起新的一次尝试——任务、预算与页面上看到的是同一个说法（包 A 的 CR-A3）。

        **发布前那道授权复核已摘除**（逐次询问取消，用户 2026-09-23）。原先它比的是 `privacy_epoch`——
        那个代数在 `model_replies` / `pet_messages` 变化时同样会 +1，留着就会因为一个**无关的**设置变动
        把已经画好、已经计过费的照片丢掉。领取围栏（`StaleClaim`）与导演自己的版本闸照旧。
        """
        rendered, no_retry = self._render(task, suffix=f"-{claim.claim_generation}", attempt=claim.claim_generation)
        if rendered is None and no_retry is not None:
            with queue.fenced(claim, complete=False) as conn:
                self._commit(task, None, conn)
            queue.fail_claim(claim, f"image {no_retry}", retryable=False)
            return
        with queue.fenced(claim) as conn:
            self._commit(task, rendered, conn)

    def _render(self, task: WebTask, *, suffix: str, attempt: int) -> tuple:
        """调供应商生图并落盘。返回 ((相对路径, 图片, 是否用了参考照) 或 None, 不该重试的原因 或 None)。

        suffix 让每次领取写不同的文件名：旧领取晚到的图不会覆盖已提交记录指向的文件；attempt 是这次领取的代数，用于额度预占编号。
        **结算按实际发出了几次调用**：没有主人照片时要先画一张证件照当参考，一次预占两个单位；
        证件照发出去了、正图没成，只能按 1 次结算，不能把本地预占整笔释放（包 A 的 CR-A1）。
        """
        from ..web_providers import ImageUnavailable

        payload = task.payload
        # 重新执行时（自动重试，或主人点了"重画"）先问上一次（`paid_result.resume`）：
        #   - **已付费成功、只是没写进去**（提交时抛异常、丢了租约）→ 凭小票认领那张图，**不预占、不发送**。
        #     自动重试与重画**都这样**：重画只对 failed 的任务开放，那张图主人从没见过，认领它就是主人要的那张；
        #   - 可能已经发出、结果没确认（超时、崩在调用中途），或付过钱的结果找不回来 → **自动重试**不重发，等主人点"重画"。
        #     重画会清掉 last_error：没有可认领的图时，那是主人明确要的一次新的付费尝试，这一条不拦它。
        # 认领按**上一次的领取代数**找：落盘文件名的后缀 `-{代数}` 与预占编号末尾的代数同源。第一次执行没有上一次，不查。
        resumed = paid_result.resume(
            self.storage, f"illustration:{task.task_id}:", self.root,
            f"illustrations/{payload['user_id']}/{payload['illustration_id']}-{{attempt}}"
        ) if task.last_error or task.attempts > 1 else None
        if resumed is not None and resumed.image is not None:
            logger.info("illustration reclaimed paid result task=%s attempt=%s", task.task_id, resumed.attempt)
            return (resumed.rel, resumed.image, bool(resumed.extra.get("used_reference"))), None
        if resumed is not None and task.last_error:
            logger.info("illustration not resent task=%s previous=%s", task.task_id, resumed.blocked)
            return None, UNCONFIRMED_REASON
        character = self.character_of(payload["pet_id"])
        if character is None or not self.available():
            return None, "not_configured"
        species, name, personality = character
        reference = self.reference_photo_of(payload["pet_id"])
        journal = payload.get("style") == "travel_journal"
        if journal:
            # 旅行手账（TRV-03／TRV-05）：提示词是 P 编好的简报；参考照换过就不发，无肖像版不给参考、也不补画证件照
            reference, refused = reference_for_brief(payload, reference)
            if refused is not None:
                return None, refused
        # 照片导演的预检必须在**预占之前**：目标场景 hold 要做到 0 次预占、0 次发送。
        # 放到编译提示词那一步就晚了——那时已经占掉一次额度，hold 会留下一笔空预占。
        directed = bool(payload.get("scene_key")) and payload.get("style") == "selfie"
        if directed:
            ready = self._director_ready(payload, species, reference)
            # 目标场景缺任何必需项（含身份参考）都在**预占之前**hold：0 次预占、0 次发送。
            # 不先花钱画一张证件照再把自己补成 ready——那等于用一次付费调用换一个"看起来齐了"。
            if not isinstance(ready, Readiness) or not ready.ready:
                reason = ready if isinstance(ready, str) else (ready.reason if ready is not None else "inputs_missing")
                missing = ready.missing_required if isinstance(ready, Readiness) else ()
                logger.info("photo director hold task=%s reason=%s missing=%s", task.task_id, reason, missing)
                return None, bridge.hold(reason or "inputs_missing", missing)
        # 发出付费调用之前先原子预占（同一次尝试重放不会重复预占）；没拿到额度就如实显示“没画成”，不偷偷调用
        # 预占按“这次领取的代数”编号：同一次领取重放不会重复付费，被接管后的新一次领取是新的操作
        permit = self.reserve(f"illustration:{task.task_id}:{attempt}", payload["pet_id"], 1 if reference is not None or journal else 2) if self.reserve else None
        if permit is not None and getattr(permit, "status", None) != "reserved":
            logger.info("illustration budget denied task=%s reason=%s", task.task_id, getattr(permit, "reason", "unknown"))
            return None, "budget_denied"
        sent = 0  # 已经真的发出去、可能已计费的调用次数
        # **不要**预置成 "owner_original"：那会在执行阶段把一张来源不明（或本来就是我们生成的）基准照
        # 改称主人原图，覆盖掉 reference_origin_of 读到的真实来源。只有这次真的生成了才标 original_companion。
        portrait_origin = None
        if reference is None and self.portrait_saver is not None and not journal:
            try:
                portrait = self.illustrator.render(build_portrait_prompt(species=species, name=name, personality=personality), None, size="2048x2048")
            except ImageUnavailable as exc:
                sent += 0 if exc.reason in NOT_SENT_REASONS else 1
                self._settle_calls(permit, exc.reason, sent)
                if exc.reason in NO_RETRY_REASONS:
                    return None, exc.reason
                raise
            sent += 1
            self.portrait_saver(payload["pet_id"], portrait.image_bytes, portrait.mime_type)
            reference = (portrait.image_bytes, portrait.mime_type)
            portrait_origin = "original_companion"
        size = "2048x2048"
        if directed:
            # 证件照补上之后再预检一次：这时参考照一定有了，缺别的就是真的缺。
            inputs = self._director_inputs(payload, species, reference, origin=portrait_origin)
            ready = bridge.check(*inputs) if isinstance(inputs, tuple) else inputs
            if not isinstance(ready, Readiness) or not ready.ready:
                reason = ready if isinstance(ready, str) else (getattr(ready, "reason", None) or "inputs_missing")
                missing = ready.missing_required if isinstance(ready, Readiness) else ()
                logger.info("photo director hold task=%s reason=%s missing=%s sent=%s", task.task_id, reason, missing, sent)
                self._settle_calls(permit, "succeeded", sent)  # 证件照已经发出去了，按实结算，不整笔释放
                return None, bridge.hold(reason, missing)
            try:
                prompt, size, dropped = bridge.compile_call(*inputs)
            except bridge.DeliveryRefused as refused:
                # 丢了参考图/角色/顺序：**发之前就拒**，不发一张看不出缺了什么的照片
                logger.warning("photo director delivery refused task=%s dropped=%s", task.task_id, refused)
                self._settle_calls(permit, "succeeded", sent)
                return None, bridge.hold(f"delivery_would_drop:{refused}")
        elif payload.get("style") == "selfie":
            prompt = build_selfie_prompt(species=species, name=name, place=payload.get("place", ""), city=payload.get("city", ""),
                                         scene=payload.get("scene", ""), with_reference=reference is not None)
        elif journal:
            prompt, size = payload["brief_prompt"], payload["brief_size"]  # P 编好的简报：站名、数字不在里面；不请求 background
        elif payload.get("style") == "journal":
            prompt = build_journal_prompt(species=species, name=name, title=payload.get("title", ""), lines=payload.get("lines", []),
                                          city=payload.get("city", ""), with_reference=reference is not None)
            size = "1440x2560"
        else:
            # 冒险插画：**不用载荷里的 story，也不用叮嘱**（CR-IMAGE-MEMORY-PURPOSE-2026-09-24 的 A 半）。
            # 有冒险键就按模板**不带叮嘱**重渲——场景描述保留，"带着你准备的…"那一句不出现；
            # 没有键的是按旧规则排进来的在途任务，它载荷里那段 story 可能夹着只授权过私聊的叮嘱，
            # 所以**一个字都不读**，只用标题。不借 `privacy_epoch` 判断任何东西：无关设置改动不该挡住合法的照片。
            template = ADVENTURES.get(payload.get("adventure_key") or "")
            story = render_story(template, name, None) if template is not None else ""
            prompt = build_prompt(species=species, name=name, personality=personality, title=payload.get("title", ""), story=story,
                                  with_reference=reference is not None)
        try:
            image = self.illustrator.render(prompt, reference, size=size)
        except ImageUnavailable as exc:
            sent += 0 if exc.reason in NOT_SENT_REASONS else 1
            self._settle_calls(permit, exc.reason, sent)
            if exc.reason in NO_RETRY_REASONS:
                return None, exc.reason  # 不重试：如实显示“没画成”，主人可稍后重画
            raise  # 供应商错误（确定没成功）：交给任务重试
        sent += 1
        self._settle_calls(permit, "succeeded", sent)
        ext = EXT.get(image.mime_type, "png")
        folder = self.root / "illustrations" / payload["user_id"]
        folder.mkdir(parents=True, exist_ok=True)
        rel = f"illustrations/{payload['user_id']}/{payload['illustration_id']}{suffix}.{ext}"
        (self.root / rel).write_bytes(image.image_bytes)
        # 小票：提交若失败，自动重试凭它认领这张已付费的图（证件照那一次也已算在这次预占里），不再付第二次
        paid_result.write_receipt(self.root, rel.rsplit(".", 1)[0], rel, image, used_reference=reference is not None)
        return (rel, image, reference is not None), None

    def _director_inputs(self, payload: dict, species: str, reference, origin: str | None = None):
        """凑齐照片导演的输入；参考照还没有、或必需事实缺项时返回 None（调用方据此 hold）。

        `origin` 只有两个合法来源：本次尝试刚画出来的基准照（`original_companion`），
        或装配注入的 `reference_origin_of`。**都没有就返回 None → hold**，不给来源不明的旧图冒名。
        """
        pet_id, user_id = payload["pet_id"], payload["user_id"]
        origin = origin or self.reference_origin_of(pet_id)  # 来源不明就是 None，下面会 hold
        can_access = self.can_view_pet(user_id, pet_id) if self.can_view_pet is not None else True
        with self.storage.connect() as own:  # 执行这一刻的真实代数
            current = versions_in(own, pet_id)
        # 事件代数必须**执行这一刻重新读**。没接这个读口就回读 payload，两边永远相等——那是伪装的围栏，
        # 比没有更坏（看起来有一道闸，其实永远不触发）。所以没接线就 hold，原因码单列，一眼能看出是接线缺失。
        revision_now = self.event_revision_of(payload["source_key"]) if self.event_revision_of is not None else None
        gap = bridge.input_gap(payload, reference=reference, origin=origin, current=current, current_revision=revision_now)
        if gap is not None:
            return gap  # 返回**具体缺什么**，调用方直接拿它当 hold 原因
        return bridge.photo_inputs(payload, species=species, reference=reference, origin=origin,
                                   can_access=can_access, current=current, current_revision=revision_now)

    def _director_ready(self, payload: dict, species: str, reference):
        """预占之前的预检：输入凑不齐返回 None，凑齐了返回 `Readiness`。"""
        inputs = self._director_inputs(payload, species, reference)
        return bridge.check(*inputs) if isinstance(inputs, tuple) else inputs

    def _settle_calls(self, permit, reason: str, sent: int) -> None:
        """按实际发出的次数结算：一次都没发出才整笔释放本地预占；超时记 unknown（本地按“可能已计费”保守计入，不代表真实费用）。"""
        if sent == 0:
            self._settle(permit, "not_sent")
            return
        outcome = "succeeded" if reason == "succeeded" else ("unknown" if reason in UNKNOWN_REASONS else "failed")
        self._settle(permit, outcome, actual_units=sent)

    def _settle(self, permit, outcome: str, actual_units: int | None = None) -> None:
        if permit is not None and self.settle is not None and getattr(permit, "status", None) == "reserved":
            self.settle(permit, outcome, actual_units)

    def _unconfirmed_attempt(self, task_id: str, conn=None) -> str | None:
        """**最近一次**尝试是不是可能已经发出、结果没确认：它的额度预占停在 reserved / unknown / expired 就算。

        只看最近一次是有意的：更早的 unknown 记录要保留（不回写、不删除），但不能挡住"主人重画之后那次明确失败"的正常重试。
        没有预占记录时返回 None。库里还没有额度表（迁移 0050 之前）也返回 None，维持原来的重试行为；
        但**读取出错**（锁死、损坏）按"不确定"处理——读不到账本就不敢再发一次。
        """
        prefix = f"illustration:{task_id}:"
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        # 按 operation_id 末尾的领取代数取最近一次；代数不是数字时 CAST 得 0，排在最前面，不会被误判成最近
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
                return None  # 迁移 0050 之前的库：没有额度表，无从判断
            logger.warning("illustration budget lookup failed task=%s: %s", task_id, type(exc).__name__)
            return "ledger_unreadable"  # 读不到账本：当作结果不明，不自动重发
        return row["status"] if row is not None and row["status"] in UNCONFIRMED_RESERVATION_STATUSES else None

    def outcome_of(self, task_id: str, conn=None) -> str | None:
        """给展示层分辨用：'failed'（明确没画成）、'unknown'（可能已经发出、结果未确认）、None（还没结束或已出图）。

        API 上用哪个字段、哪个取值仍归集成窗口（app/schemas/web/** 与路由），这里只提供依据。
        """
        sql = "SELECT status FROM web_illustrations WHERE task_id = ?"
        if conn is not None:
            row = conn.execute(sql, (task_id,)).fetchone()
        else:
            with self.storage.connect() as own:
                row = own.execute(sql, (task_id,)).fetchone()
        if row is None or row["status"] != "failed":
            return None
        return "unknown" if self._unconfirmed_attempt(task_id, conn) else "failed"

    def _commit(self, task: WebTask, rendered: tuple | None, conn) -> None:
        if rendered is None:
            self._finish_failed(task.task_id, conn)
            return
        rel, image, used_reference = rendered
        conn.execute("UPDATE web_illustrations SET status = 'ready', rel_path = ?, content_type = ?, provider = ?, model = ?, used_reference_photo = ?, updated_at = ? "
                     "WHERE illustration_id = ?", (rel, image.mime_type, image.provider, image.model, int(used_reference), iso(utcnow()), task.payload["illustration_id"]))
        self.on_ready(task.task_id, self.url(task.payload["illustration_id"]), conn)

    def _finish_failed(self, task_id: str, conn=None) -> None:
        """插画进终态。**没画成**与**结果不明**走不同回调：后者可能已经被受理，展示层要如实说"还没确认"，不能写成"没画成"。"""
        execute_in(self.storage, conn, "UPDATE web_illustrations SET status = 'failed', updated_at = ? WHERE task_id = ?", (iso(utcnow()), task_id))
        unknown = self.on_unknown is not None and self.outcome_of(task_id, conn) == "unknown"
        (self.on_unknown if unknown else self.on_failed)(task_id, conn)

    def run_pending(self, worker_id: str = "web-illustrations", limit: int = 5) -> int:
        """处理到期任务（后台线程循环调用；测试里直接调用）。返回处理个数。"""
        handled = 0
        for _ in range(limit):
            task = run_once(self.tasks, {KIND: self}, worker_id)
            if task is None:
                break
            handled += 1
            # superseded＝领取后 precheck 发现主人已经关掉“生成照片”：任务不再执行，
            # **展示状态也要跟着落定**，否则消息与插画会永远停在“正在画”（撤权边界的第一个场景）。
            if task.status in ("failed", "superseded"):
                self._finish_failed(task.task_id)
        return handled

    def file_for(self, viewer_user_id: str, illustration_id: str) -> tuple[Path, str] | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_illustrations WHERE illustration_id = ?", (illustration_id,)).fetchone()
        if row is None or row["status"] != "ready" or not row["rel_path"]:
            return None
        allowed = self.can_view_pet(viewer_user_id, row["pet_id"]) if self.can_view_pet is not None else row["user_id"] == viewer_user_id
        if not allowed:
            return None
        path = (self.root / row["rel_path"]).resolve()
        try:
            path.relative_to(self.root.resolve())
        except ValueError:
            return None
        return (path, row["content_type"] or "image/png") if path.is_file() else None


class IllustrationWorker:
    """进程内后台线程：只在生图供应商可用时由应用启动；单实例部署（与 SQLite 单实例一致）。"""

    def __init__(self, service: IllustrationService, interval_seconds: float = 3.0) -> None:
        self.service = service
        self.interval = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="web-illustration-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.service.run_pending()
            except Exception:  # noqa: BLE001 - 单个任务异常不应停掉 worker
                logger.exception("illustration worker iteration failed")
            self._stop.wait(self.interval)
