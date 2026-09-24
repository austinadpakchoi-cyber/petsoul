"""世界角色资产（CR-PLAYER-CHARACTER-01）：主人上传的原照 → TA 在世界里的专属形象。

**三类图片各司其职，不要混**：

* 主人上传的**原照片**——身份参考与档案，`pets.photo_url`，**永不被角色覆盖**；
* **世界角色**（本文件）——透明全身、跨场景复用，家、庭院、屋内都用它；
* **旅行/生活照片**——自拍与明信片，走已有的照片导演链路（`social.PhotoStatus`）。

把原照裁圆贴到场景上不是角色；用 fixture 演示猫冒充真实用户的宠物也不是。

## 为什么 active 与 candidate 要分开

角色是**自动生效**的：生成并通过发布校验后直接显示，主人不必点确认。
但"自动生效"不等于"边生成边替换"——换参考或重做时，**已生效的旧版本要一直在**，
直到新版本通过校验才原子切换。所以：

    active     当前正在显示的那一套，随时可读，可能为 None（从没成功过）
    candidate  本次在建的，有自己的状态与失败原因，**不影响 active 的可读性**

过期任务不得覆盖新形象——`revision` 与 `reference_version` 就是用来挡这个的。

## 状态六态，与 `social.PhotoStatus` 的关系

照片是一次性产物，四态够用；角色是**有生命周期的资产**，要区分"从来没有过"
和"这次没画成"，所以多两态：

    absent   从没有过任务（新宠物、或排不上——原因看 `blocked_reason`）
    queued   已排队，还没轮到
    running  正在画
    ready    画好并已发布
    failed   **确定**没画成，可以重来
    unknown  **结果没确认**：请求可能已发出并计费，响应没拿回来

两处取名与 A 的提案对齐过，结论一个采纳一个不采纳，理由都在这里：

* `running`（采纳 A 的，我原写 `generating`）——内部 `web_tasks.status` 就是
  `'queued'`/`'running'`，对外用同一个词让实现少一层映射、少一处出错；
  `school.py` 已有对外 `running` 的先例。
* `absent`（不采纳 A 的 `none`）——`none` 在 JSON 与 TypeScript 里都与 `null`
  只差一层含义，前端拿到 `status: "none"` 和 `status: null` 很容易写成同一个分支。
  **这一态恰恰要和"字段为空"区分开**：它表示「查过了，确实还没有任务」。

`unknown` 的处理与照片一致且更严：**不得写成"没生成"，不得自动再次付费**。
它需要一次显式的查清或用户发起的重做，不能由后台自己补发。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from .common import WebModel


class CharacterStatus(str, Enum):
    """见模块 docstring。`unknown` 绝不能被折叠进 `absent` 或 `failed`。"""

    absent = "absent"
    queued = "queued"
    running = "running"
    ready = "ready"
    failed = "failed"
    unknown = "unknown"


class CharacterReason(str, Enum):
    """`blocked_reason` 与 `candidate.reason` 的**当前完整码表**。

    **为什么要放进契约**：这些码是对外可见的——前端必须把它们翻成人话给主人看。
    先前它们只定义在 `web_character/model.py` 与 `validate.py` 里，
    前端只能**手抄一份**，再靠「加了新码记得告诉我一声」维持同步。
    手抄加口头通知是最脆弱的同步方式：漏通知一次，玩家就会在页面上看到一个原始码。

    **字段类型仍是 `str` 而不是这个枚举**，是有意的：实现若返回表外的新码，
    应当让前端显示泛化说法，而不是让整个响应 500。这个枚举是**给前端穷举用的参考表**，
    不是校验闸。实现侧应当引用它而不是另抄一份——A 自己在 `NO_RETRY_REASONS` 上
    就是这么做的（从 `validate` 取常量，不重抄词表）。

    **`consent_missing` / `consent_revoked` 已删除**（2026-09-23）。用户决定取消逐次询问
    （计划文档「上传处说明照片会用于准备专属形象；按图片服务的新策略自动处理，不另设家庭生图许可」），
    这两个码不可能再产生，留着就是让前端为到不了的分支写文案。
    **取消的是「询问」，不是保护**：额度、费用、幂等、`unknown` 不自动重试、越权读挡下，一条都没动；
    归属判断单列成 `pet_has_no_household`（原先由那道许可顺带承担，不能跟着一起摘掉）。
    发现要删的是那条跨层双向不变量——它在实现侧摘掉授权后**当场红**，这正是它该做的事。

    分三组，前端的处置完全不同：
    """

    # ---- 一、排队前就挡住了：多半是主人可以自己解决的 ----
    no_reference_photo = "no_reference_photo"
    species_unsupported = "species_unsupported"
    provider_unavailable = "provider_unavailable"
    not_configured = "not_configured"
    # 这只宠物不属于任何家庭：角色不属于任何人，也没人有权读它（三条路由都走 `require_pet`）。
    # **这不是授权码。** 原先那道家庭生图许可顺带承担了归属判断，摘授权时不能把它一起摘掉。
    pet_has_no_household = "pet_has_no_household"

    # ---- 二、执行期：已经开始做了，中途停下 ----
    generated_reference_only = "generated_reference_only"
    reference_changed = "reference_changed"
    budget_denied = "budget_denied"
    unknown_result = "unknown_result"
    transparency_not_requested = "transparency_not_requested"
    attempts_exhausted = "attempts_exhausted"

    # ---- 二之二、供应商当场给的说法：原样落进 `reason`，不翻译成别的码 ----
    # A 补：这四个是 `web_providers/images.py::failure_reason` 的产出，
    # `_render` 里 `return None, exc.reason` 直接落库，所以它们**确实会到前端**。
    # 一次跨层不变量用例（`test_web_character_validate.py::CharacterReasonContractTests`）
    # 在契约与实现之间双向比对时抓出来的——不是谁疏忽，是**两份码表没有机制保证一直对得上**。
    # `provider_error` **不在这里**：那一类会往外抛、由任务重试，用完次数落的是 `attempts_exhausted`。
    daily_cap = "daily_cap"
    rejected = "rejected"
    timeout = "timeout"
    unconfirmed = "unconfirmed"

    # ---- 二之三、`regenerate` 专有：不是失败，是"这次不用再排了" ----
    # 6c2b 在真实接口上撞到的：`service.py` 原先直接返回字面量 `"already_queued"`，
    # 而那条双向不变量的实现侧读的是**常量表**，字面量不在表里 → 双方都看不见它。
    # **不变量挡得住"两份常量表不同步"，挡不住"有人直接写字面量"。**
    # A 已把它提成 `model.ALREADY_QUEUED`，并在 `routers/web/character.py::_reason` 加了一道
    # 送出前的留痕——字面量绕得过常量表，绕不过那一道。
    already_queued = "already_queued"

    # ---- 三、图像校验没过：画出来了但不能用 ----
    not_png = "not_png"
    undecodable = "undecodable"
    interlaced_unsupported = "interlaced_unsupported"
    palette_unsupported = "palette_unsupported"
    bit_depth_unsupported = "bit_depth_unsupported"
    no_alpha_channel = "no_alpha_channel"
    opaque_background = "opaque_background"
    # 不透明，而且背景是灰白相间的方格：alpha 在上游有过、被传输压平了 ⇒ **改响应格式／端点**。
    # 与 `opaque_background`（参数被忽略 ⇒ 改参数或报能力缺失）分开记，两者处置完全不同。
    # 2026-09-23 本链路开始按调用请求透明底后，这一支才变为可达，检测器随之落地。
    checkerboard_drawn = "checkerboard_drawn"
    empty_subject = "empty_subject"
    multiple_subjects = "multiple_subjects"
    subject_cut_off = "subject_cut_off"
    subject_too_large = "subject_too_large"
    subject_too_small = "subject_too_small"
    too_large_to_check = "too_large_to_check"

    # ---- 四、证件照校验没过（CR-6C2B-IDPHOTO；只出现在 `id_photo.reason` 上）----
    # 透明路线照 P《宠物证件照导演规范》§4.2；透明、棋盘格、单一主体、解不开这些与角色共用上面的码
    photo_not_to_bottom = "photo_not_to_bottom"  # 胸口没到底边：拍成了全身或半身
    photo_headroom_off = "photo_headroom_off"  # 头顶留空不在 3%–20%
    photo_head_cut_off = "photo_head_cut_off"  # 头部贴到左右边：做头像时会被裁掉
    # 不透明备选路线（适配器不请求透明时）
    photo_too_small = "photo_too_small"
    photo_wrong_shape = "photo_wrong_shape"
    photo_blank = "photo_blank"


class CharacterPose(str, Enum):
    """中性全身是每一套的第一张；其余五个是批次二（P 规范 §6-5），以**同一套已生效的中性姿态**为参考生成。

    猫、狗、鸟不能硬套同一种骨架——姿态名描述的是**意图**，具体骨架由角色导演按物种定。
    **精灵里只有姿态**：晒太阳的光斑、吃东西的食盆、睡觉的毯子和窝都由场景层画，回应抚摸只表达回应、不代表任何业务结果。

    批次二**自动生成的开关默认关**（用户 2026-09-24 决定，不新增付费调用），所以短期内真实数据里只有 `neutral_full`。

    早先留的占位 `resting` **已删除**（2026-09-24）：它从不产出，前端屋内已改用 `sleeping`（6c2b 登记后删），
    后台词表里对应的那一条同一次改动一起删（adm1 精确释放）。**同名的 `TravelActivityKind.resting`（车上休息）不是它**。
    """

    neutral_full = "neutral_full"
    sleeping = "sleeping"
    sunbathing = "sunbathing"
    eating = "eating"
    walking = "walking"
    petted = "petted"


class ContentBox(WebModel):
    """非透明内容在画布里的实际边界（像素，左上原点）。

    PNG 有 alpha 不等于主体占满画布。渲染要按这个框对齐，否则角色会"浮在半空"
    或被裁断。**这四个数必须来自对实际 alpha 通道的测量，不能照抄画布尺寸。**
    """

    left: int = Field(ge=0)
    top: int = Field(ge=0)
    right: int = Field(ge=0)
    bottom: int = Field(ge=0)


class GroundAnchor(WebModel):
    """落地点：角色"脚踩在哪里"，相对画布的归一化坐标。

    场景把这个点对到地面线上，角色才会站在地上而不是飘着。
    首版由角色导演给出估计值；**估计值也要如实标成估计**，见 `measured`。
    """

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    measured: bool = Field(default=False, description="True＝从图像实测；False＝导演给的估计值")


class CharacterAsset(WebModel):
    """一张姿态图。URL **受权限保护**，不是公开静态资源。"""

    asset_id: str
    pose: CharacterPose
    url: str = Field(description="受权限保护的读取地址；越权读会被挡下，不是 CDN 直链")
    content_sha256: str = Field(description="图片字节的 SHA-256；用于证明前端拿到的就是这一版")
    content_type: str = Field(description="实际的图片 MIME，例如 image/png")
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    content_box: ContentBox
    anchor: GroundAnchor
    opaque_ratio: float = Field(
        ge=0.0, le=1.0,
        description="不透明像素占整张画布的比例。`has_alpha` 只说通道在不在，这个说主体有多大——"
                    "接近 1 基本就是一张不透明的方图（背景没抠掉），接近 0 则可能主体被裁没了。")
    has_alpha: bool = Field(
        description="实际验证过的 alpha 通道可用性。**不得因为返回的是 PNG 就填 True**——"
                    "PNG 可以完全不透明，当前 GPT 适配器也没有请求或验收透明背景。")


class CharacterSet(WebModel):
    """一套已发布的角色资产。同一 `character_set_id` 内各姿态外貌必须一致。

    `assets` 是这一套里**已就绪**的那几张：中性站姿一定在，其余姿态画好一张多一张。
    **缺的姿态只能回落到同一套的中性站姿，绝不回落到旧套的那张**（P 规范 §6-4 唯一不可放松的不变量）——
    所以前端只在这一个列表里找，找不到就用 `neutral_full`。
    """

    character_set_id: str
    pet_id: str
    revision: int = Field(ge=1, description="同一只宠物的第几套；过期任务不得覆盖更高的 revision")
    reference_version: int = Field(
        description="生成时所用身份参考（原照）的版本。**换参考后旧结果不得发布**，靠这个比。")
    style_version: str = Field(description="画风版本；换风格要能解释形象为何变了")
    assets: list[CharacterAsset]
    published_at: datetime


class CharacterCandidate(WebModel):
    """本次在建的那一套。它失败不影响 `active` 继续显示。"""

    status: CharacterStatus
    pose: CharacterPose
    reference_version: int
    style_version: str
    queued_at: datetime
    reason: str | None = Field(
        default=None,
        description="未获授权、额度不足、供应商失败等**如实写原因**；"
                    "不要把 unknown 的原因写成「没生成」。")
    task_id: str | None = Field(default=None, description="对应的后台任务；没有任务时为 null")


class CharacterPoseProgress(WebModel):
    """active 那一套里**一个额外姿态**的进度（批次二）。中性站姿不在这里——它的状态就是 `CharacterState.status`。

    `status` 与中性站姿同一口径：`unknown` 是"可能已经发出、结果没确认"，**不得说成没生成**。
    这里失败了不影响这一套里已经就绪的任何一张，前端对这个姿态照旧退回中性站姿。
    """

    pose: CharacterPose
    status: CharacterStatus
    reason: str | None = Field(default=None, description="没画成或作废的原因，码表同 `CharacterReason`")
    task_id: str | None = Field(default=None, description="对应的后台任务")


class IdPhotoSource(str, Enum):
    """证件照从哪来。"""

    generated = "generated"  # 以主人原照／领养档案照为参考画的（每只 1 次付费）
    companion_portrait = "companion_portrait"  # 没有照片的宠物：复用插画链路那张基准证件照，不另付费


class CharacterIdPhoto(WebModel):
    """每只宠物一张证件照（CR-6C2B-IDPHOTO）：护照、居民证、驾照等全部证件都用它。**不透明**，所以不是一种姿态。

    用户 2026-09-24 定：新宠物自动生成、默认开；存量不批量补（主人换照片或点重画时才生成）。
    前端取图：`id_photo?.status === "ready" ? id_photo.url : photo_url`；地图头像优先 `avatar_url`，没有就退回原来的图。
    """

    status: CharacterStatus = Field(description="与角色同一口径；`unknown` 是可能已经发出、结果没确认，不得说成没画成")
    source: IdPhotoSource | None = Field(default=None, description="`absent` 时为 null")
    url: str | None = Field(default=None, description="证件用图（竖幅 3:4、浅蓝纯底）的受保护地址；没有生效的证件照时为 null")
    avatar_url: str | None = Field(
        default=None,
        description="地图头像：从证件照上方正方形缩成的 **256×256** 小图。**没有就是 null，不拿别的图冒充**"
                    "（没照片的宠物那张基准照不是裁好的头像，也是 null）")
    width: int | None = None
    height: int | None = None
    content_sha256: str | None = Field(default=None, description="证件用图字节的 SHA-256")
    reference_version: int | None = Field(default=None, description="依据的是这只宠物的第几张参考照；换了照片才重画")
    revision: int | None = None
    reason: str | None = Field(default=None, description="没画成或作废的原因，码表同 `CharacterReason`")
    task_id: str | None = None


class CharacterState(WebModel):
    """`GET /pets/{pet_id}/character` 的响应。**纯读，绝不触发生成。**

    前端据此渲染：`active` 有就显示角色；没有就按 `status` 显示"正在准备 TA 的形象"
    或对应失败态。**没有任务时不许显示假进度**（`status == absent` 就是没有任务）。
    """

    pet_id: str
    status: CharacterStatus = Field(description="综合状态：有 candidate 时取它的，否则由 active 是否存在决定")
    active: CharacterSet | None = Field(default=None, description="当前生效的一套；从未成功过时为 null")
    candidate: CharacterCandidate | None = Field(default=None, description="本次在建的；空闲时为 null")
    can_regenerate: bool = Field(
        description="是否允许发起「调整形象」。授权缺失、额度用尽、已有在建任务时为 False，"
                    "**原因在 candidate.reason 或 blocked_reason 里给**。")
    blocked_reason: str | None = Field(
        default=None, description="can_regenerate 为 False 且没有 candidate 时，这里说明为什么")
    # `x-additive`：前端类型里是**可选**属性——前端手写的 `CharacterState` 字面量（用例、占位）不因多了这个字段而编译失败
    poses: list[CharacterPoseProgress] = Field(
        default_factory=list,
        description="active 那一套里其余姿态的进度（批次二）。自动生成的开关默认关，关着时为空数组；"
                    "已就绪的那几张同时出现在 `active.assets` 里",
        json_schema_extra={"x-additive": True})
    id_photo: CharacterIdPhoto | None = Field(
        default=None, description="证件照（与形象不同，不透明、有底色）。没有时前端退回 `photo_url`",
        json_schema_extra={"x-additive": True})


class CharacterRegenerateCommand(WebModel):
    """「调整形象」——**可选**操作。正常路径由上传成功自动触发，用户不必点这个。

    **幂等键走 `Idempotency-Key` 请求头，不在这个请求体里。** 我初版在这里放过一个
    `idempotency_key` 字段，是错的：全仓其它写命令的 DTO 都没有它，平台的
    `require_idempotency_key` 读的是请求头。两个来源并存会多出一个「不一致时听谁的」
    问题，而那个问题没有好答案。A 在实现时发现并回执，字段已删。
    """

    pose: CharacterPose = Field(
        default=CharacterPose.neutral_full,
        description="**目前一律按整套重做**：先重画中性站姿，其余姿态（开关开着时）随新的一套重新生成——"
                    "只重画某一个姿态会让它和同套的站姿不再是同一张参考（P 规范 §6-4）。本字段暂不区分取值")
    note: str | None = Field(default=None, max_length=200, description="主人想调整的地方，可空")


class CharacterRegenerateResult(WebModel):
    """发起结果。`accepted=False` 时 `reason` 必须能解释为什么没排上。"""

    accepted: bool
    status: CharacterStatus
    task_id: str | None = None
    reason: str | None = None


# 本包 `__init__.py` 明写：新增模型必须进 `__all__`，否则 `gen_web_contract.py` 扫不到，
# 前端 `generated.ts` 里就不会有这些类型——路由表有、DTO 没有，比两样都没有更难发现。
__all__ = [
    "CharacterStatus",
    "CharacterReason",
    "CharacterPose",
    "ContentBox",
    "GroundAnchor",
    "CharacterAsset",
    "CharacterSet",
    "CharacterCandidate",
    "CharacterPoseProgress",
    "IdPhotoSource",
    "CharacterIdPhoto",
    "CharacterState",
    "CharacterRegenerateCommand",
    "CharacterRegenerateResult",
]
