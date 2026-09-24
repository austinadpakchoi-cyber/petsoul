"""宠物 / 专属领养契约：私有画像与公开简介分离；领养来源字段必留。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from .common import DataOrigin, WebModel
from .social import PhotoStatus


class PetSpecies(str, Enum):
    dog = "dog"
    cat = "cat"
    parrot = "parrot"
    rabbit = "rabbit"
    hamster = "hamster"
    bird = "bird"
    other = "other"


class PetOrigin(str, Enum):
    own_pet = "own_pet"
    adopted_original = "adopted_original"
    adopted_real_archive = "adopted_real_archive"


class PetPresence(str, Enum):
    """宠物唯一位置：同一时刻只能处于一种状态（不能既在家守菜又在店里）。"""

    not_activated = "not_activated"
    at_home = "at_home"
    in_transit = "in_transit"
    at_destination = "at_destination"
    visiting = "visiting"
    returning = "returning"
    unknown = "unknown"


class ProfileVisibility(str, Enum):
    public = "public"
    followers = "followers"
    private = "private"


class PetPrivateSummary(WebModel):
    """只发给归属主人。owner_title 只在主人确认后出现，缺省不代表主人说过。"""

    pet_id: str
    home_id: str | None = None
    name: str
    species: PetSpecies
    photo_url: str | None = None
    origin: PetOrigin
    owner_title: str | None = None
    presence: PetPresence
    photo_generated: bool = Field(default=False, description="照片是生成的写实证件照（没有主人上传的照片时）；页面应标注“AI 生成”",
                                  json_schema_extra={"x-additive": True})


class PetPublicProfile(WebModel):
    """公开主页投影：不含主人私密资料、接待原文或饮食限制。计数来自已执行动作。"""

    pet_id: str
    display_name: str
    species: PetSpecies
    avatar_url: str | None = None
    bio: str | None = None
    origin_label: str | None = None
    visibility: ProfileVisibility
    follower_count: int = 0
    post_count: int = 0
    viewer_follows: bool = Field(default=False, description="当前查看者的宠物是否已关注 TA")
    is_own: bool = Field(default=False, description="是否是查看者自己的宠物")
    data_origin: DataOrigin


class AdoptionAvailability(str, Enum):
    available = "available"
    reserved = "reserved"
    adopted = "adopted"


class AdoptionCandidate(WebModel):
    """领养卡：先讲名字/性格/梦想；真实背景可展开；来源未知保持未知。"""

    candidate_id: str
    name: str
    species: PetSpecies
    personality: str
    dream: str
    origin: PetOrigin
    source_note: str | None = Field(default=None, description="来源说明；未知则为 null，不编造")
    background_available: bool = False
    availability: AdoptionAvailability
    data_origin: DataOrigin
    pet_id: str | None = Field(default=None, description="已经在星球上生活的待领养居民的稳定 pet_id（领养后不变）；可用它看 TA 的公开生活",
                               json_schema_extra={"x-additive": True})
    residence: str | None = Field(default=None, description="领养前住在哪（星球居民驿站·片区；世界规则提供食宿，不编造人类主人）",
                                  json_schema_extra={"x-additive": True})
    living_since: datetime | None = Field(default=None, description="从什么时候开始在星球上公开生活", json_schema_extra={"x-additive": True})


class AdoptRequest(WebModel):
    """需 Idempotency-Key；服务端原子占用，两个家庭抢同一候选最多一个成功（409 ADOPTION_TAKEN）。"""

    candidate_id: str
    household_id: str | None = Field(default=None, description="领养进已有的家庭（需要是这个家庭的管理员）；不给则新建家庭",
                                     json_schema_extra={"x-additive": True})


class AdoptResult(WebModel):
    pet_id: str
    candidate_id: str
    adopted_at: datetime


class PetDNA(WebModel):
    """宠物 DNA：主人描述、确认的性格与习惯。模型扮演宠物时读取；私密字段只用于私信，不进公开动态。"""

    owner_title: str | None = Field(default=None, max_length=12, description="TA 怎么称呼主人")
    nicknames: list[str] = Field(default_factory=list, max_length=5, description="主人叫 TA 的小名")
    personality: str | None = Field(default=None, max_length=80, description="性格")
    voice_style: str | None = Field(default=None, max_length=40, description="说话的样子，例如“慢吞吞、爱撒娇”")
    catchphrase: str | None = Field(default=None, max_length=40, description="口头禅或常发出的声音")
    favorite_foods: list[str] = Field(default_factory=list, max_length=8)
    favorite_places: list[str] = Field(default_factory=list, max_length=8)
    hobbies: list[str] = Field(default_factory=list, max_length=8)
    habits: list[str] = Field(default_factory=list, max_length=8, description="小习惯")
    fears: list[str] = Field(default_factory=list, max_length=6, description="害怕的东西")
    shared_memories: list[str] = Field(default_factory=list, max_length=8, description="和主人之间的小暗号、趣事；只在私信里使用")


class BehaviorPolarity(str, Enum):
    positive = "positive"
    negative = "negative"
    averse = "averse"
    uncertain = "uncertain"


class BehaviorTraitStatus(str, Enum):
    applied = "applied"
    negated = "negated"
    outweighed = "outweighed"
    uncertain = "uncertain"


class PetRhythm(str, Enum):
    regular = "regular"
    night_owl = "night_owl"
    early_bird = "early_bird"
    sleepy = "sleepy"


class PetSociability(str, Enum):
    social = "social"
    steady = "steady"
    homebody = "homebody"


class BehaviorEvidence(WebModel):
    """一条原话出处：DNA 哪一栏、原话中的哪一小句（原样，不改写）、被怎样理解。"""

    field: str = Field(description="personality / voice_style / catchphrase / habits / hobbies / favorite_places / favorite_foods / fears / dream / note（接待叮嘱）")
    field_label: str = Field(description="栏目中文名，例如“性格”“小习惯”“接待时的叮嘱”")
    phrase: str = Field(description="原话中的那一小句")
    polarity: BehaviorPolarity = Field(description="positive 肯定 / negative 被否定 / averse 讨厌或害怕 / uncertain 说不准")
    note: str | None = Field(default=None, description="为什么这样理解，例如“‘不’否定了这个说法”“‘偶尔’：说法不确定，暂不归类”")
    implied: bool = Field(default=False, description="由别的说法反推（例如“不爱热闹”→ 偏安静），单独不足以归类")


class BehaviorTrait(WebModel):
    key: str = Field(description="night_owl / early_bird / sleepy / social / homebody / curious / diligent / playful")
    label: str
    status: BehaviorTraitStatus = Field(description="applied 用上了 / negated 明确说不是 / outweighed 被更明确的相反说法盖过 / uncertain 说不准，暂不归类")
    evidence: list[BehaviorEvidence] = Field(default_factory=list)


class BehaviorPreference(WebModel):
    key: str = Field(description="job:<岗位> / route:local:stroll / route:local:cafe / route:local:city_trip / route:long")
    label: str
    weight: float = Field(description="选择时的倍数：>1 更愿意，<1 不太愿意，1 照常")
    evidence: list[BehaviorEvidence] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list, description="来自性格的调整，例如“恋家：更爱在附近走走”")


class PetBehavior(WebModel):
    """由 DNA 原话整理出的行为倾向（服务端确定性规则，不调用模型）；只给主人看。
    作息、出门次数、路线与工作倾向、话多话少、学东西快慢都按这一份；每条结论都能追溯到原话。"""

    rules_version: str
    rhythm: PetRhythm
    sleep_start: str = Field(description="入睡时间（TA 所在地当地时间，HH:MM）")
    wake: str = Field(description="起床时间（HH:MM）")
    sociability: PetSociability
    curious: bool
    outings_per_day: int = Field(description="一天最多自己出门几次")
    chattiness: int = Field(description="一天主动找主人说话的次数")
    learn_rate: float = Field(description="学东西的快慢（驾考陪练与自学的倍数）")
    summary: list[str] = Field(default_factory=list, description="一句话结论，例如“不爱熬夜：按平常作息（23:30 睡，07:30 起）”")
    traits: list[BehaviorTrait] = Field(default_factory=list, description="提到过的性格与作息特征（含被否定、被盖过和说不准的）")
    preferences: list[BehaviorPreference] = Field(default_factory=list, description="工作与路线倾向")
    unclassified: list[str] = Field(default_factory=list, description="提到了但说不准或前后矛盾、没有归类的原话")
    sources: list[str] = Field(default_factory=list, description="这次用到了哪些栏目")


class PetDNAView(WebModel):
    pet_id: str
    dna: PetDNA
    confirmed: bool = Field(description="主人是否已保存确认；未确认时为系统整理的草稿")
    draft_sources: list[str] = Field(default_factory=list, description="草稿来源：adoption_profile / owner_bio / reception_notes")
    updated_at: datetime | None = None
    private_fields: list[str] = Field(default_factory=lambda: ["shared_memories"], description="只用于私信、不进公开内容的字段")
    behavior: PetBehavior | None = Field(default=None, description="由这份 DNA 整理出的行为倾向与原话出处（0.2.5 追加）", json_schema_extra={"x-additive": True})
    version: int | None = Field(default=None, description="全家共用那部分 DNA 的版本号；保存时带 ?expected_version= 可防止无声覆盖家人的修改（冲突 409）",
                                json_schema_extra={"x-additive": True})
    personal_fields: list[str] = Field(default_factory=lambda: ["owner_title", "shared_memories"],
                                       description="每位家人各自的一份（TA 怎么称呼你、你们之间的小暗号），别的家人看不到也不会被覆盖",
                                       json_schema_extra={"x-additive": True})
    updated_by_you: bool | None = Field(default=None, description="共用部分最后一次是不是你改的", json_schema_extra={"x-additive": True})


class PhotoScene(str, Enum):
    """主人主动发起拍照时能选的场景。

    **只有这三个**：`cafe` 不在其中——到咖啡馆拍照由行程里的到访活动触发，那条路不变。
    这三个的共同点是**现有事件模型里没有对应的触发时刻**：在家时没有行程也没有到访，
    途中要到店之后才有到访，而虚构飞行按设计本来就不该由真实行程推导出来。
    """

    home = "home"
    train = "train"
    flight_adventure = "flight_adventure"


class PhotoNarrative(str, Enum):
    """这张照片讲的是哪一种故事。**虚构的必须由主人显式选**，不会自动升级。"""

    daily_life = "daily_life"
    fictional_adventure = "fictional_adventure"


class PhotoRequestCommand(WebModel):
    """主人说「给我拍一张」。"""

    scene: PhotoScene
    narrative: PhotoNarrative = Field(default=PhotoNarrative.daily_life,
                                      description="flight_adventure 必须显式传 fictional_adventure；其余场景只接受 daily_life")


class PhotoRequestResult(WebModel):
    """受理结果。**不代表照片已经画好**，也不代表一定画得出来。

    重发同一个 `Idempotency-Key` 会原样拿回**第一次**的受理结果（同一个 `request_id` 与 `task_id`），
    **不要拿它当状态轮询**——要看画得怎么样，去读 `GET /pets/{pet_id}/photo-requests`。
    """

    request_id: str = Field(description="这次摄影请求的稳定标识，用它去只读查询里找结果、或发起重画")
    task_id: str | None = Field(
        default=None,
        description="排上队的生图任务。为空的情况只有一种：这个环境没配生图供应商、或主人没开「生成照片」，"
                    "于是命令受理了但没有排队。重复请求**不会**让它为空——那会原样返回第一次的任务号。")
    scene: PhotoScene
    narrative: PhotoNarrative
    fictional: bool = Field(description="真值表示这是主人选的虚构主题：不会写成真实出行、不扣旅费、不发勋章")
    captured_at: datetime = Field(description="按 TA **此刻所在城市**换算的拍摄时刻；途中用当前所在地，不是出发地")
    place: str = Field(description="这一刻 TA 在哪（家 / 车上 / 虚构主题的场景），只作展示")
    city: str


class PhotoRequestView(WebModel):
    """主人主动拍的那些照片，现在各是什么样。**纯读**：读它不会驱动任何任务，也不会发起任何调用。"""

    request_id: str
    task_id: str | None = None
    scene: PhotoScene
    narrative: PhotoNarrative
    fictional: bool
    captured_at: datetime
    place: str
    city: str
    photo_status: PhotoStatus = Field(
        description="processing＝还在画；ready＝画好了；failed＝确定没画成；"
                    "**unknown＝结果还没确认**（可能已经发出、甚至已经计费），页面要显示成「还没确认」并给重画入口，不能写成「没画成」")
    image_url: str | None = Field(default=None, description="画好了才有；其余状态一律为空")
    can_retry: bool = Field(description="能不能点「重画」：failed 与 unknown 可以，processing / ready 不行")

__all__ = [
    "PetSpecies",
    "PetOrigin",
    "PetPresence",
    "ProfileVisibility",
    "PetPrivateSummary",
    "PetPublicProfile",
    "AdoptionAvailability",
    "AdoptionCandidate",
    "AdoptRequest",
    "AdoptResult",
    "PetDNA",
    "BehaviorPolarity",
    "BehaviorTraitStatus",
    "PetRhythm",
    "PetSociability",
    "BehaviorEvidence",
    "BehaviorTrait",
    "BehaviorPreference",
    "PetBehavior",
    "PetDNAView",
    "PhotoScene",
    "PhotoNarrative",
    "PhotoRequestCommand",
    "PhotoRequestResult",
    "PhotoRequestView",
]
