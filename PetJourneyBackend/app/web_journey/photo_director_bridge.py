"""把插画任务的 payload 翻译成照片导演（包 P）的输入，再把导演的产物翻译回一次生图调用。

为什么单独一个文件：`illustrations.py` 卡在架构门禁的 30 个定义上限；也为了把"翻译"和"执行"分开——
这里只做映射与判断，**不排队、不预占、不发调用、不写库**。

三条硬规矩（COORD-A-DIRECTOR-NOW）：
  1. **缺必需项就 hold**：0 次图片预占、0 次发送，**绝不回落旧模板**——回落会把"没拍成"伪装成"拍成了"。
  2. **不杜撰**：时区、拍摄时刻、家庭、地点、已核验事实，缺哪个就 hold 哪个，不猜、不填默认值凑数。
  3. **只允许显式丢失 `negative_prompt`**：方舟 `/images/generations` 没有这个参数，所以不发；
     但要如实记账，其余任何语义丢失（参考图、角色、顺序）都视为异常。
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ..web_photo_director import (
    CURRENT_WEB_SINK,
    IdentityReference,
    MediaReference,
    PhotoAccess,
    PhotoContext,
    PhotoDirector,
    PhotoVersions,
    SceneFact,
    SceneFacts,
    plan_delivery,
    project_photo_dna,
    readiness,
)

DIRECTOR = PhotoDirector()  # 零注入＝纯规则导演：一次文本模型调用都不发
# 参考照的来源标记：主人原照 / 我们自己先画的那张基准证件照
# 与 `web_photo_director.validation.ORIGIN_SOURCE` **逐值对齐**：少一个值就会在这一层先拦掉，
# 那一类宠物白白 hold，而导演本来认它（I 报的 real_archive 漂移）。
ORIGIN_SOURCE = {"owner_original": "owner_original", "original_companion": "generated_canonical",
                 "real_archive": "archive_original"}
# 这次拍照的来路：世界自己发生的到店事件 / 主人按下的拍照命令。
# **不能一律记成 world_event**——主人选的虚构题材（flight_adventure）记成世界事件，
# 等于断言"世界上真的发生过一次飞行"；导演会以 world_event_cannot_be_fictional 拒掉。
EVENT_ORIGINS = ("world_event", "owner_directed")
# payload 里必须由登记方（C 经 B）给出的事实；缺任何一个都 hold，不猜
REQUIRED_PAYLOAD = ("household_id", "place_id", "place_timezone", "captured_at", "revision", "versions")
ALLOWED_DROP = ("negative_prompt",)


class DeliveryRefused(Exception):
    """交付会丢掉不该丢的语义（参考图/角色/顺序）：宁可不出图，也不发一张看不出缺了什么的照片。"""


def hold(reason: str, missing: tuple = ()) -> str:
    """统一的 hold 原因串。任务会以它进终态、**不自动重试**——缺的是事实或授权，重试不会让它变有。

    把 `missing_required` 的第一项也带上：只给大类的话，"物种不支持"和"参考照版本对不上"
    在主人那边长得一模一样（都是 `hold_validation_failed`），运维分不开。
    """
    return f"director_hold:{reason}:{missing[0]}" if missing else f"director_hold:{reason}"


def local_capture_time(payload: dict) -> datetime | None:
    """把登记时存下的拍摄时刻换算成**该地点的当地墙上时间**；缺时区或缺时刻一律返回 None（交给调用方 hold）。

    导演直接拿 `.hour` 当本地小时挑光线，所以这里必须是当地时间：
    家里 22:10 那张要画成夜景，用宿主机时区会画成大白天（P 在 8 张真图上验过）。
    """
    raw, zone = payload.get("captured_at"), payload.get("place_timezone")
    if not raw or not zone:
        return None
    try:
        moment = datetime.fromisoformat(raw)
        if moment.tzinfo is None:
            # 不带偏移就是来源不明：**不猜 UTC、也不用宿主机时区**，交给调用方 hold。
            # （登记走 utils.iso() 时一定带偏移，所以这一支是防御性的；真正会缺的是 place_timezone。）
            return None
        return moment.astimezone(ZoneInfo(zone))
    except (ValueError, KeyError):
        return None


def scene_facts(payload: dict) -> tuple:
    """payload 里的已核验事实是 JSON 字典（经过任务表一来一回），这里还原成导演的 `SceneFact`。

    只认 `verified is True` 的条目——没核验过的事实等于没有，不给导演当依据。
    """
    restored = []
    for item in payload.get("scene_facts") or ():
        if isinstance(item, SceneFact):
            restored.append(item)
            continue
        if not isinstance(item, dict) or item.get("verified") is not True:
            continue
        restored.append(SceneFact(fact_id=item["fact_id"], token=item["token"], pet_id=item["pet_id"],
                                  household_id=item["household_id"], event_id=item["event_id"], verified=True))
    return tuple(restored)


def input_gap(payload: dict, *, reference, origin, current, current_revision) -> str | None:
    """凑不齐导演输入时，**具体缺的是哪一样**；齐了返回 None。

    每一项都单列原因码：运维要能一眼分开"登记方忘了声明来路"（接线问题）与"事实不齐"（数据问题），
    混成一个 `inputs_missing` 就只能靠猜。
    """
    if reference is None:
        return "identity_reference_missing"
    if origin not in ORIGIN_SOURCE:
        return "reference_origin_unknown"  # 来源不明：不冒名 owner_original
    if current is None:
        return "runtime_versions_unreadable"
    if current_revision is None:
        return "event_revision_unwired"  # 没有"执行时重读代数"的读口：那道闸会变成自比，宁可 hold
    if payload.get("event_origin") not in EVENT_ORIGINS:
        # 缺这个键意味着"不知道这次拍照的来路"。**不知道不能自动变成"世界上真的发生过"**——
        # 两个登记方现在都显式传，所以它是必填（P 的 world_event_cannot_be_fictional 依赖它）。
        return "event_origin_missing"
    for key in REQUIRED_PAYLOAD:
        if payload.get(key) in (None, "", ()):
            return f"payload_missing:{key}"
    if local_capture_time(payload) is None:
        return "captured_at_not_localised"
    return None


def photo_inputs(payload: dict, *, species: str, reference: tuple[bytes, str] | None, origin: str | None,
                 can_access: bool, generated_photos: bool, current, current_revision: int | None = None) -> tuple[PhotoContext, PhotoAccess] | None:
    """构造导演的输入；**必需事实缺任何一项就返回 None**（调用方据此 hold，0 预占 0 发送）。

    参考照的 `sha256` **由实收的 bytes 现算**，不信任外部传来的摘要——这样"指令里锁的那张脸"
    和"真正发出去的那张图"绑在同一份字节上。`reference_id` 与 identity 版本也都由这份摘要派生，跨重试稳定。

    版本代数**不是自比的假零**：上下文用**登记那一刻**存进 payload 的快照，`PhotoAccess` 用
    **执行这一刻**读到的 `current`（`runtime_epochs.versions_in`）。两者不一致时导演自己会拒——
    这正是"登记之后、出图之前授权或 DNA 变了"的那道围栏。A 自己那两道撤权保护照旧，不被它替代。
    """
    if input_gap(payload, reference=reference, origin=origin, current=current, current_revision=current_revision) is not None:
        return None  # 缺什么由 input_gap 说，这里只负责不猜
    captured_at = local_capture_time(payload)
    image_bytes, mime_type = reference
    digest = hashlib.sha256(image_bytes).hexdigest()
    pet_id, household_id = payload["pet_id"], payload["household_id"]
    snapshot = payload["versions"]  # 登记那一刻的真实代数
    identity_version = int(digest[:8], 16)  # 由实际参考字节稳定派生：换了参考照，这个版本就变
    versions = PhotoVersions(identity=identity_version, dna=int(snapshot["dna"]),
                             privacy=int(snapshot["privacy"]), activity=int(snapshot["activity"]))
    identity = IdentityReference(pet_id=pet_id, household_id=household_id, species=species, origin=origin,
                                 reference_id=f"ref-{digest[:16]}", sha256=digest, version=identity_version,
                                 appearance_tags=())
    media = MediaReference(reference_id=identity.reference_id, sha256=digest, role="pet_identity",
                           source=ORIGIN_SOURCE[origin], pet_id=pet_id, household_id=household_id,
                           mime_type=mime_type, ready=True, authorized=True)
    scene = SceneFacts(
        event_id=payload["source_key"], revision=int(payload.get("revision", 0)), scene=payload["scene_key"],
        captured_at=captured_at, city=payload.get("city", ""), place_id=payload["place_id"],
        place_label=payload.get("place", ""), committed=True, origin=payload["event_origin"],
        narrative=payload.get("narrative", "daily_life"), facts=scene_facts(payload))
    context = PhotoContext(
        pet_id=pet_id, household_id=household_id, versions=versions, identity=identity,
        # 空 DNA 投影是合法输入：导演会走保守构图，而不是编一个性格出来
        dna=project_photo_dna({}, allowed_fields=frozenset(), version=versions.dna, projection_id="none"),
        scene=scene, references=(media,))
    # 执行这一刻的真实代数（identity 仍由参考字节派生，换照片才变）
    now_versions = PhotoVersions(identity=identity_version, dna=int(current.dna_version),
                                 privacy=int(current.privacy_epoch), activity=int(current.activity_epoch))
    # 事件代数同理：上下文用登记那一刻采到的，`PhotoAccess` 用**执行这一刻**重新读到的。
    # 两边都回读 payload 的话这道闸永远不触发——那是伪装的围栏，所以 `current_revision` 是必需的。
    access = PhotoAccess(pet_id=pet_id, household_id=household_id, versions=now_versions,
                         event_revision=int(current_revision), can_access=can_access,
                         generated_photos=generated_photos, photo_dna=generated_photos,
                         reference_use=generated_photos, text_director=False, companion_photos=False)
    return context, access


def check(context: PhotoContext, access: PhotoAccess):
    """预检：返回 `Readiness`（`ready` / `reason` / `missing_required` / `optional_absent`）。"""
    return readiness(context, access)


def compile_call(context: PhotoContext, access: PhotoAccess) -> tuple[str, str, tuple[str, ...]]:
    """规则导演编译出这次要发的提示词与尺寸；返回 (prompt, size, 被入口丢掉的语义项)。

    `strict=False` 是**有意的**：现网入口不支持负面词，用 strict=True 会直接抛。
    但丢什么必须记下来——调用方要断言只丢了 `negative_prompt`，其余一概视为异常。
    """
    photo = DIRECTOR.direct(context, access)
    plan = plan_delivery(photo, CURRENT_WEB_SINK, strict=False)
    dropped = tuple(plan.dropped)
    if dropped not in ((), ALLOWED_DROP):
        # 只允许丢负面词（方舟没有这个参数，而且它是独立字段、不进正向）。
        # 丢了参考图、角色或顺序就说明入口能力与导演产物对不上——**在 render 之前拒绝**，不是记个 warning 继续发。
        raise DeliveryRefused(",".join(dropped))
    return photo.prompt, photo.size, dropped
