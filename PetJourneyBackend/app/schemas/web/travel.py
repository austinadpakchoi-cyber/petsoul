"""旅行心愿与自动手账的对外契约（TRV-00 §23）。

**纯读为主**：`GET /travel/wish` 与 `GET /travel/plans/{plan_id}` 只读，
**绝不触发研究、生图或出行**（沿用 A 的 `WishView` docstring 那条）。

**为什么全部带 `Travel` 前缀**：`app/schemas/web/**` 与 `web_journey` / `web_travel` / `web_agent`
三个领域包之间，跨层同名的类**目前是零**——这是仓里既有的纪律。而领域层已经占了三个最顺手的名字：

    A  web_travel/model.py:105    WishView       →  这里叫 TravelWish
    B  web_agent/wish_policy.py   PlanState      →  这里叫 TravelPlan
    B  web_agent/wish_policy.py   WishCandidate  →  这里叫 TravelWishCandidate

不加前缀就会造出本批第五处「同名不同物」（前四处见合同 §12 与 §22.4）。

**注意不要和旧攻略混**：`schemas/web/journey.py` 已有 `TravelGuide` / `TravelGuideStop`，
那是旧的攻略（§6 兼容），与这里的 `Travel*` 不是一套东西，但会同时出现在前端的 import 里。

**三个枚举是领域层清单的第二份**，由 `tests/test_web_travel_contract.py`（I）与
`tests/test_web_travel_enum_contract.py`（Q）**两份互不复用的双向用例**锁住：
实现多一个码红、契约多一个码也红。**不要让 `web_travel` / `web_agent` import 本文件**——
那会让领域层依赖对外 schema、依赖方向倒过来、撞 `dependency_gate`（合同 §0.2）。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from .common import WebModel
from .social import PhotoStatus

__all__ = [
    "TravelWaitingReason", "TravelWishStatus", "TravelResearchStatus",
    "TravelStopRole", "TravelFactVerdict", "TravelJournalPhase", "TravelIdentityMode",
    "TravelWishCandidate", "TravelWish",
    "TravelSource", "TravelFact", "TravelStop", "TravelOwnerTip", "TravelJourneySummary",
    "TravelPlanRevision", "TravelPlan", "TravelJournal",
]


class TravelWaitingReason(str, Enum):
    """还差什么才能出发（可同时多条）。合同 §5.2 全集，**页面给每个码配人话**。

    `missing_funds` **不等于** `quota_denied`：前者是宠物自己的星币不够，
    后者是平台调用额度不够——**不是同一件事，也不该显示成同一句话**。
    """

    missing_funds = "missing_funds"
    quota_denied = "quota_denied"
    research_pending = "research_pending"
    research_unknown = "research_unknown"  # **不等于**搜不到：可能已发出、结果没确认，不自动重发
    research_failed = "research_failed"
    fact_stale = "fact_stale"
    plan_stale = "plan_stale"  # **本批无生产者**（§20.1）：写入方是 A，本批恒为 False
    fact_unverified = "fact_unverified"  # 没有可用来源：假 source_id／只有模型自述／没查到
    fact_conflicting = "fact_conflicting"  # 关键事实互相矛盾，得有人判哪条对
    weather_unsuitable = "weather_unsuitable"
    commitment_active = "commitment_active"
    maintenance = "maintenance"


class TravelWishStatus(str, Enum):
    """心愿的业务主状态。与研究状态、手账图状态是**三个独立字段**，页面分别显示、不合并（§5.1）。"""

    active = "active"
    ready = "ready"
    linked = "linked"
    completed = "completed"
    cancelled = "cancelled"


class TravelResearchStatus(str, Enum):
    """研究任务状态。**与心愿主状态分开保存**——不能用一个业务状态盖住「已可能发出」。

    `unknown` ＝ 请求可能已经发出并计费、结果没确认。**不得显示成「没查到」，不得自动重发**；
    旧 operation 结清之前不换号重发。这与 `PhotoStatus.unknown` 是同一套口径。

    策略侧另有一个 `none`（「还没登记」，`web_agent/wish_policy.py` 的哨兵），
    **那是策略内部的，不会被存下来、也不在这个契约里**——见 `test_web_travel_contract.py`
    里那条单独钉住它的正向断言。
    """

    queued = "queued"
    running = "running"
    ready = "ready"
    failed = "failed"
    unknown = "unknown"


class TravelWishCandidate(WebModel):
    """TA 想去的一个地方。**「有心愿」不等于「可以出发」**（合同 §3）。

    **这里没有 `offer_id`、没有 `valid_until`、没有任何能喂给 `depart` 的字段**，
    而且 `executable` 是**字面常假**、不是可变字段——**靠类型上根本没有那个字段，
    就不会有人拿它去出发**（§0.3）。要出发必须经 offers 那条既有的路。
    """

    destination_key: str
    title: str
    executable: bool = False
    blocked_by: list[TravelWaitingReason] = []


class TravelWish(WebModel):
    """当前活动心愿（一只宠物同时只有一个 active 或 ready 的）。对应 A 的 `WishView`。

    `waiting_reasons` **按写入方分两份存**（B 生活侧、A 研究侧，互不冲掉），
    这里给的是并集、顺序固定——同一组原因每次读出来一样。
    """

    wish_id: str
    pet_id: str
    wish_revision: int
    status: TravelWishStatus
    destination_key: str
    destination_name: str
    city: str
    owner_reason: str
    funds_goal: int | None = None
    waiting_reasons: list[TravelWaitingReason] = []
    research_state: TravelResearchStatus | None = None
    research_round: int = 0
    plan_id: str | None = None
    plan_revision: int | None = None
    journey_id: str | None = None  # 尚未成行时为空——**不预建假旅程**（§2）
    reconsider_after: datetime | None = None  # **只是给页面看的缓存值**，冷却闸不读它（§17）
    last_considered_at: datetime | None = None  # 按宠物的「上次考虑」；冷却闸读它＋策略间隔
    plan_stale: bool = False  # A 判、B 只读；**本批恒为 False**（§20.1 写明无生产者）
    target_coins: int | None = None  # missing_funds 时页面说「还差多少」——缺什么就说什么
    current_coins: int | None = None  # 钱包快照，快照时刻就是 last_considered_at
    candidates: list[TravelWishCandidate] = []


class TravelStopRole(str, Enum):
    """主目的地 vs 顺路建议。**只有 `main` 的关键事实决定能不能出发**，顺路建议不决定（合同 §18.4）。"""

    main = "main"
    suggested = "suggested"


class TravelFactVerdict(str, Enum):
    """一条事实的核验结论。**`unverified` 与 `rejected` 不折叠**：前者是查不到可用来源，
    后者是引用了不存在的 `source_id`——后者说明上游产出有问题，不是外部世界没资料。
    """

    verified = "verified"
    unverified = "unverified"
    stale = "stale"
    conflicting = "conflicting"
    rejected = "rejected"


class TravelJournalPhase(str, Enum):
    """手账的两页：出发前的计划页、回来后的回忆页。**回忆页只收真实到访事件**（A 的口径）。"""

    plan = "plan"
    memory = "memory"


class TravelIdentityMode(str, Enum):
    """这页手账里 TA 的样子从哪来：用证件照，还是不画 TA。"""

    photo = "photo"
    none = "none"


class TravelSource(WebModel):
    """一条来源。`url` 可空——只有机构名没有链接时也是合法来源。"""

    source_id: str
    url: str | None = None
    publisher: str | None = None
    retrieved_at: datetime | None = None
    published_at: datetime | None = None


class TravelFact(WebModel):
    """一条已核验（或已被判否）的事实。

    **时间字段一律可空、不伪造**（A 的口径）：拿不到发布时间就是 `None`，不拿抓取时间顶。
    `blocks_departure` 只对关键类别成立——顺路建议的事实不挡出行（§18.4）。
    """

    fact_id: str  # "tf-" ＋ 20 位十六进制
    category: str  # destination_identity / route / opening / weather / notice / ticket_price / …
    subject: str  # 这条事实说的是**哪个地方**
    value: Any = None  # JSON；价格类是 {amount, currency, estimated}，被判 rejected 时为 null
    source_ids: list[str] = []
    verification: str | None = None  # **核验方法**（map / weather_api / search…），不是结论
    conclusion: str | None = None
    verdict: TravelFactVerdict
    blocks_departure: bool = False
    retrieved_at: datetime | None = None
    published_at: datetime | None = None
    observed_at: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class TravelStop(WebModel):
    """计划里的一个地点。

    **`lat`/`lng` 是 WGS-84**（合同 §8、§28.1）：高德给的 GCJ-02 由 TRV-04 适配器在落库前转好，
    A 原样存。**前端照常用 `coords.ts` 换算一次**——不要因为数据来自高德就跳过换算，那会偏移翻倍。

    **`station_id`（`st-0`、`st-1`…）只在一版计划之内有效**，跨版本别当键（A 评估后不换稳定 id：
    按内容造「稳定」编号遇到同名站、改名会各自出错，只是换了一种不稳定）。
    跨版本对应同一个地点用 `name` ＋ `role`。
    """

    station_id: str | None = None  # 手账版式里的 st-i；计划阶段可空
    name: str
    role: TravelStopRole
    why: str | None = None
    tip: str | None = None
    fact_ids: list[str] = []
    verified: bool = False
    lat: float | None = None
    lng: float | None = None
    nav_url: str | None = None  # 核实过的地点才给：打开地图导航。**后端给，前端不要自己拼**
                                # ——照 `schemas/web/journey.py:213` 既有形态（高德，WGS-84）
    visited_event_ids: list[str] = []  # 计划阶段恒为空；回忆页才有


class TravelOwnerTip(WebModel):
    """给主人的一条提醒，**和支持它的事实一一对应**——没有 `fact_ids` 的提醒不该出现（§18.4）。"""

    text: str
    fact_ids: list[str] = []


class TravelJourneySummary(WebModel):
    """计划关联的那趟真实行程里，跟钱有关的部分。

    **字段来源不同，由路由层 join**：`journey_id` 在 A 的计划表，
    `fare` / `fare_waived` 在 C 的 `web_journeys`（`fee` 列 ＋ m1701 新增的 `fare_waived`）。
    **A 不去读 C 的表。**

    **`fare` 永远是这趟的标价，不随用没用券变**；实付与否只看 `fare_waived`。三种情况各自唯一：

        fare_waived            →  用了借车券，实付 0，**省下 fare**
        not fare_waived, fare>0 →  实付 fare
        fare == 0              →  本来就不花钱（散步、打工）

    **没有哪个字段的含义需要靠另一个字段翻译**——这一条是硬的（C 核出，2026-09-24 改）。
    本字段初版叫 `fare_paid`，且规定「`fare_waived` 为真时给被抵掉的金额」，
    那让**同一个数在两种情况下意思相反**：把几趟的 `fare_paid` 相加算月支出时，
    **每一趟用券的都会被多算一次**，而字段叫 paid，没人会去怀疑它。
    那正是 m1701 在存储层刚消掉的歧义被搬到了 DTO 层——而且更难发现：
    「两种情况长得一样」至少会让人愣一下，「同一个数意思相反」读起来完全通顺。

    **一条可钉的不变量**（C 给）：`fare_waived` 为真 ⇒ `fare > 0`。
    因为 `waivable = dest.fee > 0 and waiver_available(...)`，「免费出门又用了券」产生不出来。
    """

    journey_id: str
    fare: int = 0
    fare_waived: bool = False


class TravelJournal(WebModel):
    """一页手账（`web_travel_journals` 的一行，主键 `(journal_id, journal_revision)`）。

    **图的状态不是数据库列**（§22.2）：走 A 的 `image_in`，取值 `None`（没图：被拒或没接插画）
    或 `PhotoStatus` 四态。**`failed` 与 `unknown` 不折叠**——`unknown` 是「可能已经画了并计费、
    结果没拿回来」，页面要写「还没确认」并给重画入口，**不能写成「没画成」**。
    只有 `failed` / `unknown` 才给 `redraw_ticket`。
    """

    journal_id: str  # "tj-<plan_id>-<phase>"
    journal_revision: int
    plan_id: str
    plan_revision: int
    phase: TravelJournalPhase
    title: str | None = None
    summary: str | None = None
    stations: list[TravelStop] = []
    owner_tips: list[TravelOwnerTip] = []
    rain_alternative: str | None = None
    sources: list[TravelSource] = []
    identity_mode: TravelIdentityMode = TravelIdentityMode.none
    identity_note: str | None = None
    template_revision: str | None = None  # "journal-t0"：TRV-07 落地前的**明示占位**
    image_status: PhotoStatus | None = None
    image_url: str | None = None
    image_refused: str | None = None  # P 的拒绝码；被拒就没有图，但手账照样有文字（§9）
    redraw_ticket: str | None = None  # 只有 failed / unknown 才给
    event_ids: list[str] = []  # 回忆页只收真实的 "<旅程>:visit_started"
    created_at: datetime
    updated_at: datetime | None = None


class TravelPlanRevision(WebModel):
    """一版计划（`web_travel_plans` 的一行，主键 `(plan_id, plan_revision)`）。**旧版都留着。**

    `valid_from` / `valid_until` 取**带窗口的已核验事实的交集**；没有窗口就是 `None`，
    此时「资料有效期」这条不适用，**不臆断**（C 的 `_assert_facts_fresh` 同一口径）。
    """

    plan_id: str
    plan_revision: int
    wish_id: str
    wish_revision_at_build: int
    pet_id: str
    destination_key: str
    operation_id: str | None = None  # 产出它的那次研究尝试
    title: str
    summary: str
    rain_alternative: str | None = None
    stops: list[TravelStop] = []
    owner_tips: list[TravelOwnerTip] = []
    preconditions: list[str] = []  # fact_id
    sources: list[TravelSource] = []  # 只含已核验事实引用到的来源
    facts: list[TravelFact] = []
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    journey: TravelJourneySummary | None = None  # C 关联真旅程之后才有
    journals: list[TravelJournal] = []  # 这一版计划的手账（计划页 plan、回忆页 memory）
    created_at: datetime


class TravelPlan(WebModel):
    """一个心愿的计划全集。`current_revision` 指最新发布的那一版。"""

    plan_id: str
    wish_id: str
    current_revision: int
    revisions: list[TravelPlanRevision] = []
