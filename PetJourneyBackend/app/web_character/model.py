"""世界角色的状态、原因码与对外资产结构。

状态分两层，**别把它们混成一个枚举**：

  - 库里落的是 `queued / running / ready / failed` 四态（迁移 1600 的 CHECK）；
  - `absent`（还没有任何一次任务）与 `unknown`（可能已经发出、结果未确认）是**运行期派生**的，
    不进库。`unknown` 尤其不能折进 `failed`——那会让展示层说成"没生成"，
    而主人看到"没生成"就会再点一次，等于**再付一次费**。与插画链路 `outcome_of` 同口径。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from . import validate

KIND = "pet_character"
# 批次二的五个姿态走**另一种任务**：参考、提示词、发布方式都不同（见 `poses.py`），同一个 handler 分不开。
POSE_KIND = "pet_character_pose"
# 中性全身姿态：每一套的第一张，也是其余姿态的参考。取值跟 `schemas/web/character.py::CharacterPose` 对齐，
# 契约那份是对外枚举，这份是库里存的字符串，**两边必须是同一个词**，不做映射（少一层就少一处出错）。
POSE_NEUTRAL = "neutral_full"

QUEUED, RUNNING, READY, FAILED = "queued", "running", "ready", "failed"
ABSENT = "absent"
UNKNOWN = "unknown"

# ---- 还没排队的原因（`view()` 读时现算，不落库）----
NO_REFERENCE = "no_reference_photo"  # 没有主人原照：不是这只宠物，不画
SPECIES_UNSUPPORTED = "species_unsupported"  # 物种不在封闭词表（含 other）：不猜骨架
PROVIDER_MISSING = "provider_unavailable"  # 没配生图供应商
# 这只宠物不属于任何家庭：生成出来的角色不属于任何人，也没人有权读它
#（三条路由都走 `require_pet`，无家即无人可授权）。
# **这不是授权闸。** 用户 2026-09-23 决定取消逐次询问（计划文档 63 行「不另设家庭生图许可」），
# 原先那道 `generated_photos_in` 顺带承担了归属判断，摘授权时不能把它一起摘掉，所以单列出来。
NO_HOUSEHOLD = "pet_has_no_household"

# **`consent_missing` / `consent_revoked` 已删除。** 取消逐次询问之后它们不可能再产生，
# 留在码表里就是让前端为到不了的分支写文案。对外契约 `CharacterReason` 也同步删了。
# 取消的是**询问**，不是保护：额度、费用、幂等、`unknown` 不自动重试、越权读挡下，一条都没动。

# ---- 执行期的 hold / 失败原因 ----
GENERATED_REFERENCE = "generated_reference_only"  # 只有我们自己画的基准照，不能当身份源
REFERENCE_CHANGED = "reference_changed"  # 排队期间主人换了照片：这一版作废，不发布
BUDGET_DENIED = "budget_denied"
NOT_CONFIGURED = "not_configured"
UNCONFIRMED = "unknown_result"  # 上一次可能已经发出、结果没确认：不自动重发
# 校验判出"不透明"，而适配器**本来就没请求透明底**：该改的是请求参数（或核实中转支不支持），
# 不是提示词。与"请求了透明、拿回来还是不透明"分开记——两者处置完全不同（P 规范 4.2 第 6 条）。
TRANSPARENCY_NOT_REQUESTED = "transparency_not_requested"
ATTEMPTS_EXHAUSTED = "attempts_exhausted"  # 重试次数用完了。**不写具体是哪一次为什么**——那要靠猜
# 「调整形象」被拒：不是失败，是"这次不用再排了"。**曾经是个硬编码字面量**，
# 于是契约与实现之间那条双向不变量漏了它——那条不变量比的是**常量表**，看不见字面量。
# 提成常量是补第一层；第二层在 `routers/web/character.py::_reason`，送出去那一刻再看一眼。
ALREADY_QUEUED = "already_queued"

# 供应商那一侧的判定口径（`web_providers/images.py::failure_reason` 的产出分类）。
# **判定函数只有一份**，这里只是按用途给它的取值分组；与插画链路 `illustrations.py` 里那两组同义。
# 放在 model 而不是 service，是因为 `NO_RETRY_REASONS` 要用到它们，而 service 反过来 import model。
NOT_SENT_REASONS = frozenset({"daily_cap", "not_configured", "rejected", "provider_error"})
# 结果不明：timeout＝发出去没等到响应；unconfirmed＝响应已回、生成已受理，之后解析/取图才失败。
# 两种都**可能已经计费**，所以保守计入，且**不自动重试**。
UNKNOWN_REASONS = frozenset({"timeout", "unconfirmed"})

# 校验不过的那些原因。**从 `validate` 取，不在这里重抄一份词表**：
# 同一个概念有两份定义时谁也不报错，行为会静悄悄漂开（`web_composition.py:380` 记过这个教训）。
INVALID_IMAGE_REASONS = frozenset({
    validate.NOT_PNG, validate.UNDECODABLE, validate.INTERLACED, validate.PALETTE, validate.BIT_DEPTH,
    validate.TOO_LARGE, validate.NO_ALPHA_CHANNEL, validate.OPAQUE, validate.EMPTY, validate.CUT_OFF,
    validate.TOO_SMALL, validate.TOO_BIG, validate.MULTIPLE, validate.CHECKERBOARD,
})

# 证件照（CR-6C2B-IDPHOTO）自己的校验原因：透明路线照 P 证件照规范 §4.2（胸口到底、头顶留空、头部没被裁），
# 不透明备选路线另有三条（太小、不是竖幅、整片单色）。**从 `validate` 取，不在这里重抄**；
# 透明、棋盘格、单一主体、解不开这些与角色共用的码，已经在上面那组里。
ID_PHOTO_INVALID_REASONS = frozenset({
    validate.PHOTO_NOT_TO_BOTTOM, validate.PHOTO_HEADROOM_OFF, validate.PHOTO_HEAD_CUT_OFF,
    validate.PHOTO_TOO_SMALL, validate.PHOTO_WRONG_SHAPE, validate.PHOTO_BLANK,
})

# 这几类不排自动重试：重发也是同样的结果，或者可能已经计费。
# **校验不过也在里面**：那一张图已经画出来、钱也已经按实结算过了，
# 后台再画一次就是再花一次钱去碰运气——方案第 54 行「不在后台无限重画凑合格结果」。
# 要再来一次只能由主人显式点「调整形象」。
#
# **`UNKNOWN_REASONS`（timeout / unconfirmed）也在里面，这一条是改过的。**
# 第一版只放了 `UNCONFIRMED`（"恢复回来发现上次可能已发出"那个派生码），没放供应商给的原始码，
# 于是超时会被**排回去等 60 秒**，靠下一轮的"恢复不重发"闸短路。行为最终是对的（0 发送 0 计费），
# 但那是**两道闸配合**才对：谁动了第二道闸，超时立刻变成二次付费，而这一边一个字都没改，从这里看不出来。
# 而且「排回去」本身就是 CR 说的「unknown **自动重试**」，不该发生。现在第一道闸自己就拦得住。
#
# 反过来说，**唯一会自动重试的是 `provider_error`**（连不上、被限流）：它确定没受理，换个时间可能就成了。
NO_RETRY_REASONS = frozenset({
    NOT_CONFIGURED, UNCONFIRMED, ATTEMPTS_EXHAUSTED,
    REFERENCE_CHANGED, GENERATED_REFERENCE, NO_REFERENCE, SPECIES_UNSUPPORTED, BUDGET_DENIED,
    NO_HOUSEHOLD, PROVIDER_MISSING, TRANSPARENCY_NOT_REQUESTED,
}) | INVALID_IMAGE_REASONS | ID_PHOTO_INVALID_REASONS | UNKNOWN_REASONS | (NOT_SENT_REASONS - {"provider_error"})

# **实现能发出的全部原因码，只有这一份。** 对外契约 `schemas/web/character.py::CharacterReason`
# 与它逐个比对（`test_web_character_validate.py::CharacterReasonContractTests`），两个方向都查。
#
# 为什么单独列而不是写成 `NO_RETRY_REASONS | {ALREADY_QUEUED}`：那两件事只是**现在**碰巧重合。
# "要不要自动重试"是任务策略，"前端要不要有文案"是对外词表；哪天出现一个可重试又要展示的原因，
# 按重试集去推词表就会漏掉它。下面那条 `assert` 把"现在重合"这件事钉住，但不让它变成定义。
#
# `provider_error` **不在里面**：它会往外抛、由任务重试，落到 `reason` 上的是 `ATTEMPTS_EXHAUSTED`。
ALL_REASONS = frozenset({
    NO_REFERENCE, NO_HOUSEHOLD, SPECIES_UNSUPPORTED, PROVIDER_MISSING,
    GENERATED_REFERENCE, REFERENCE_CHANGED, BUDGET_DENIED, NOT_CONFIGURED,
    UNCONFIRMED, TRANSPARENCY_NOT_REQUESTED, ATTEMPTS_EXHAUSTED, ALREADY_QUEUED,
}) | INVALID_IMAGE_REASONS | ID_PHOTO_INVALID_REASONS | UNKNOWN_REASONS | (NOT_SENT_REASONS - {"provider_error"})

# 不重试的每一个原因都会被展示出去，所以它必须是词表的子集。反过来不成立（`ALREADY_QUEUED` 就不是失败）。
assert NO_RETRY_REASONS <= ALL_REASONS


@dataclass(frozen=True, slots=True)
class CharacterAsset:
    """一份角色资产。`url` 是受权限保护的读取地址，不是公开文件路径。"""

    asset_id: str
    set_id: str
    pose: str
    state: str
    reason: str | None
    url: str | None
    content_type: str | None
    width: int | None
    height: int | None
    content_box: tuple[int, int, int, int] | None  # 不透明内容外接框，闭区间像素
    anchor: tuple[float, float] | None  # 落地点：外接框底边中点，相对宽高的比例
    opaque_ratio: float | None
    has_alpha: bool
    content_sha256: str | None  # 图片字节的 SHA-256：前端据此证明拿到的就是这一版
    reference_version: int  # 这一版依据的是这只宠物的第几张参考照；换了照片这个数就变
    style_version: str
    revision: int
    task_id: str
    created_at: str


@dataclass(frozen=True, slots=True)
class PoseProgress:
    """active 那一套里**一个额外姿态**的进度。状态口径与中性姿态相同（`unknown` 不折进 `failed`）。"""

    pose: str
    state: str
    reason: str | None
    task_id: str


@dataclass(frozen=True, slots=True)
class CharacterView:
    """纯读结果。`active` 是**已生效**那一套的中性姿态，`candidate` 是本次在建/最近一次的中性姿态。

    两者分开的意义：换参考重做时旧形象一直有效，新版本校验通过才原子切过去；
    在建那一版失败了也不会让家园忽然没有角色。

    `extras` 是 active 那一套里**已就绪**的其余姿态，`poses` 是那一套里每个额外姿态的进度。
    **两者都只取 active 那一套**：缺的姿态只能回落到同一套的中性姿态，绝不回落到旧套的那张（规范 §6-4）。
    """

    state: str
    reason: str | None
    active: CharacterAsset | None
    candidate: CharacterAsset | None
    published_at: str | None = None  # active 那一套是什么时候切过去的
    blocked_reason: str | None = None  # 现在发不起新一轮的原因（没原照/物种不支持/没有家/没供应商）
    extras: tuple[CharacterAsset, ...] = ()
    poses: tuple[PoseProgress, ...] = ()


def mark_ready_in(conn, asset_id: str, rendered: tuple, reference_digest: str | None, now: str) -> str:
    """把一行落成 `ready`，写进校验实测的尺寸、边界、锚点。返回图片字节的 SHA-256。

    中性姿态和其余姿态**共用这一处写法**，与下面的 `asset_of`（读）对称：这些列名只在这两处出现。
    `reference_digest` 是**这一张依据的那张参考**的摘要——中性姿态是主人原照，其余姿态是同一套的中性姿态。
    """
    rel, image, verdict = rendered
    digest = hashlib.sha256(image.image_bytes).hexdigest()
    box, anchor = verdict.content_box, verdict.anchor
    conn.execute(
        "UPDATE web_pet_characters SET state = 'ready', reason = NULL, rel_path = ?, content_type = ?, provider = ?, "
        "model = ?, sha256 = ?, width = ?, height = ?, content_left = ?, content_top = ?, content_right = ?, "
        "content_bottom = ?, anchor_x = ?, anchor_y = ?, opaque_ratio = ?, has_alpha = 1, reference_digest = ?, "
        "updated_at = ? WHERE asset_id = ?",
        (rel, image.mime_type, image.provider, image.model, digest, verdict.width, verdict.height,
         box[0], box[1], box[2], box[3], anchor[0], anchor[1], verdict.opaque_ratio, reference_digest, now, asset_id))
    return digest


def asset_of(row, url: str | None) -> CharacterAsset:
    """把一行 `web_pet_characters` 变成对外资产。只在这里读列名，别处不要再拆行。"""
    box = None
    if row["content_left"] is not None:
        box = (row["content_left"], row["content_top"], row["content_right"], row["content_bottom"])
    anchor = (row["anchor_x"], row["anchor_y"]) if row["anchor_x"] is not None else None
    return CharacterAsset(
        asset_id=row["asset_id"], set_id=row["set_id"], pose=row["pose"], state=row["state"], reason=row["reason"],
        url=url, content_type=row["content_type"], width=row["width"], height=row["height"],
        content_box=box, anchor=anchor, opaque_ratio=row["opaque_ratio"], has_alpha=bool(row["has_alpha"]),
        content_sha256=row["sha256"], reference_version=int(row["reference_version"]),
        style_version=row["style_version"], revision=int(row["revision"]),
        task_id=row["task_id"], created_at=row["created_at"],
    )
