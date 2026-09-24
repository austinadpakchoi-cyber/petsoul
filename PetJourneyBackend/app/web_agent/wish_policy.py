"""TA 自己惦记一个地方：什么时候值得重新想、还差什么、够不够去问一次可执行机会（包 B，TRV-01）。

**纯策略**：不读库、不调服务、不联网、不调模型、不写任何东西。同样的输入永远得到同样的结论。
事实由集成层一次读齐传进来（`WishFacts`），结论交回集成层去调 A 的端口——
**心愿的持久化只有 A 一个写入方**（TRV-00 §4.1），这里不碰任何一张表、也不建第二张心愿表。

单独一个文件而不是并进 `brain_wiring.py`：那个组合根已经顶在门禁上限，而"值不值得重新想"
本来也该能单独验——它是整条链里最容易被做成"每次 tick、每次刷新都想一遍"的一环。

## 两个轴不能混

- **要不要往下走**（`SkipReason`）：维护态、同一事件重放、冷却未到、正在旅途、有效承诺。
  说的是"这一次评估该不该动作"。
- **还差什么**（`WaitingReason`）：缺钱、资料没到、天气不合适……说的是"心愿自身在等什么"，
  写进心愿、给页面看。取值是 TRV-00 §5.2 的**封闭全集**，由 `tests/test_web_wish_policy.py`
  双向锁住（实现多一个红、合同多一个也红）。

一次评估可以"往下走了、但还在等钱"，也可以"跳过、心愿的等待原因一个字都不动"。
混成一套就会把"这一轮没轮到"说成"它在等钱"——运维和玩家都会被误导。

`WaitingReason` 与心跳的 `SilenceReason` **也是两个轴**（TRV-00 §5.3），同样不合并：
那一套分的是"正常安静 vs 故障安静"，给运维看的。

## 冷却是自己的常量，**不复用心跳的旋钮**

方案 §9 要求"无新有效事件时至少 24 小时"。心跳的 `idle_review_interval` 是 **15 分钟**、
`max_review_interval` 是 **6 小时**——差两个数量级。接到那两个旋钮上，心愿会每 15 分钟
被重新考虑一次（TRV-00 §5.5 明写不得复用）。所以这里有自己的 `reconsider_interval`。

**新的有效事件不受冷却限制**：工资到账、主人建议、行程变化都该让 TA 立刻重新想一想。
冷却挡的是"什么新事都没发生，却因为页面刷新或者又一次心跳而再想一遍"。

**闸读的是"过去那个事实"，不是"算好的截止时刻"**（TRV-00 §17，起因是 Q 4d18 的实测）。

先前这里读的是集成层传进来的 `reconsider_after`。那样 `MIN_RECONSIDER_INTERVAL` 就只守着
`evaluate()` 的**输出**，而闸读的是那个值在库里存取一轮之后传回来的样子——
**守卫和它要守的那一行之间，隔着一个别人可以插手的地方**。集成层从别处写一个 15 分钟进来
（心跳旋钮、迁移默认值、仓储默认值、手滑），冷却就变成 15 分钟，这里一行都不会响。

而且那种错**分辨不出来**：`now + 15 分钟`，与"24 小时的冷却在 23 小时 45 分之前设下"，
从一个裸时刻上看一模一样。所以修法不是在读侧加夹逼，是**换读哪个值**：
现在读 `last_considered_at`（上次考虑的时刻），截止时刻由**这里的 `reconsider_interval` 现算**。
集成层还能写错的只剩一条关于过去的事实——**那是数据错误，可以被发现；悄悄改了策略不行。**

**所以 `reconsider_after` 不再是输入**：`WishFacts` 里根本没有这个字段，
策略**在类型上就读不到**一个别人算好的截止时刻（同 `WishCandidate.executable` 那一招）。
它只作为 `WishDecision` 的**输出**存在，给页面显示、给 A 存一份缓存。

**读侧不做补偿**（§17 的硬约束）：不要在这里加 `max(reconsider_after, now + 24h)` 那类夹逼。
那会让一个数据问题看起来像已经解决，而实际只是被盖住了。

## 冷却与重放**只挡"重新想"，不挡"已经想好的那个"**

这是有意为之，不是漏了：`COOLING_DOWN` / `TRIGGER_REPLAYED` / `QUOTA_DENIED` 只在
**还没有活动心愿**时生效——它们挡的是要花模型调用的那一步。已经成立、已经不缺东西的心愿，
任何一轮都可以交接出去。

反过来做就会踩上一个刚修过的坑：一次读到旧事实的评估，把本该醒来的那次机会吞掉，
于是 TA 明明钱够了却要再等一整轮。**"少做一次"在这里不是安全的默认值。**

## 已有心愿不再问一次大脑

首批每宠一个活动心愿。已经有活动心愿时，这里只做两件事：把等待原因核新、够了就交接。
**不重新问大脑换个地方**——换方向或取消要走显式命令（方案 §9），不能由一次自动评估悄悄改掉
TA 已经说出口的愿望。

## 不可执行的东西，类型上就不给能执行的字段

`WishCandidate.executable` 是**只读属性、恒为 False**；没有 `offer_id`、没有 `valid_until`、
没有任何能喂给 depart 的字段（TRV-00 §0.3）。要出发必须经 C 现有的 offers 规则，
**这里不去改那套过滤让没钱也能走**。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from ..web_runtime.clock_policy import ensure_utc

WISH_POLICY_VERSION = "travel-wish-2026.1"
MIN_RECONSIDER_INTERVAL = timedelta(hours=24)  # 方案 §9 的"至少 24 小时"：可以往上调，不能往下


class WishStatus(str, Enum):
    """业务主状态（TRV-00 §5.1）。研究任务与手账图各有自己的状态，不由这一个字段代表。"""

    ACTIVE = "active"
    READY = "ready"
    LINKED = "linked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


OPEN_STATUSES = frozenset({WishStatus.ACTIVE.value, WishStatus.READY.value})
# 已出发、已收尾、已取消的心愿不自动复活（方案 §9）：要换方向得用显式命令带版本条件
CLOSED_STATUSES = frozenset({WishStatus.LINKED.value, WishStatus.COMPLETED.value, WishStatus.CANCELLED.value})


class WaitingReason(str, Enum):
    """心愿在等什么。**封闭全集**，与 TRV-00 §5.2 一一对应。

    几处语义必须分开（方案 §10 点名）：
    `missing_funds` 是游戏金币不够，**不等于**平台额度不够（那是 `quota_denied`）；
    `research_unknown` 是结果不明，**不等于**搜不到（那是 `research_failed`）；
    `fact_stale` 是资料过期，**不等于**地名不存在。

    `plan_stale` 与 `research_pending` 也分开，因为**页面要说的话不一样**：
    pending 是研究**正在跑**，用户等着就行；`plan_stale` 是研究**做完了但计划按的是旧版心愿**，
    需要重新发起一轮。并成一个码会让"什么都没在跑"的状态显示成"正在查资料"。
    与 `fact_stale` 也不同：那是**某一条事实**过期（比如旧天气），这是**整份计划**基于旧版心愿。

    事实出问题也分三种，因为**页面该说的话和该给的按钮都不一样**：
    `fact_stale` 过期（再取一次就行）、`fact_unverified` **没有可用来源**（假 source_id／
    只有模型自述／没查到，得重查）、`fact_conflicting` 互相矛盾（得有人判哪条对）。
    名字用形容词式是跟 P 的编译器（`web_photo_director/journal_brief.py`）统一的，合同 §5.2 已收。

    **这一套里只有三条是 B 写的**（见下面的 `LIFE_SIDE`）：其余都是 A 写的，**B 只读、只透传**。
    存储上就是两列、两个写入方、互不覆盖（`m1700_travel_wish.py:9`）。
    """

    MISSING_FUNDS = "missing_funds"
    QUOTA_DENIED = "quota_denied"
    RESEARCH_PENDING = "research_pending"
    RESEARCH_UNKNOWN = "research_unknown"
    RESEARCH_FAILED = "research_failed"
    FACT_STALE = "fact_stale"
    PLAN_STALE = "plan_stale"
    FACT_UNVERIFIED = "fact_unverified"
    FACT_CONFLICTING = "fact_conflicting"
    WEATHER_UNSUITABLE = "weather_unsuitable"
    COMMITMENT_ACTIVE = "commitment_active"
    MAINTENANCE = "maintenance"


# **B 只写这三条**，其余等待原因由 A 写（存储上是 `life_waiting_json` / `research_waiting_json`
# 两列、两个写入方、互不覆盖——`m1700_travel_wish.py:9`）。`update_waiting` 收到别的码会 `WishRejected`。
#
# 这个集合与 `app/web_travel/model.py` 的 `LIFE_REASONS` **必须逐字一致**，
# 由 `tests/test_web_wish_wiring.py` 的双向用例锁住：**这里多一条红、那边多一条也红**。
# 不 import 过来是因为依赖方向——决策包不依赖 A 的持久化包。
LIFE_SIDE = frozenset({WaitingReason.MISSING_FUNDS.value, WaitingReason.COMMITMENT_ACTIVE.value, WaitingReason.MAINTENANCE.value})


class SkipReason(str, Enum):
    """这一次**为什么不动作**。与 `WaitingReason` 不是一个轴，不要合并显示。"""

    NOT_ACTIVATED = "not_activated"  # 还没入住：先等入住，不安排心愿
    MAINTENANCE = "maintenance"  # 运营暂停：不形成、不推进心愿（TRV-00 §4.5）
    WISH_CLOSED = "wish_closed"  # 已出发/已收尾/已取消，不自动复活
    ACTIVE_JOURNEY = "active_journey"  # 正在路上：这一趟走完再说
    COMMITMENT_ACTIVE = "commitment_active"  # 答应过的事还没兑现，先别惦记新地方
    TRIGGER_REPLAYED = "trigger_replayed"  # 同一个 trigger_event_id 已经处理过
    COOLING_DOWN = "cooling_down"  # 没有新的有效事件，且还没到可以重新想的时刻
    QUOTA_DENIED = "quota_denied"  # 今天的调用额度不够，不绕过额度去想
    UNCHANGED = "unchanged"  # 有活动心愿、等待原因跟上次一模一样：不写、不发


class WishAction(str, Enum):
    SKIP = "skip"  # 什么都不做：不写库、不请求大脑、零外发
    ASK_BRAIN = "ask_brain"  # 值得想一次：请大脑给少量候选与理由（也允许它选择留在家里）
    UPDATE_WAITING = "update_waiting"  # 等待原因真的变了：带 expected_revision 写回 A
    HAND_OFF = "hand_off"  # 不缺东西了：去请 C 的可执行机会（**仍由 C 的规则决定能不能走**）


@dataclass(frozen=True, slots=True)
class WishPolicy:
    """心愿参数。**与心跳的旋钮完全独立**，见模块开头那一节。"""

    reconsider_interval: timedelta = timedelta(hours=24)  # 无新有效事件时，两次"重新想"之间至少隔多久（方案 §9）
    max_candidates: int = 3  # 一次最多几个候选（方案 §8：首批最多三个，只研究选中的一个）
    version: str = WISH_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.reconsider_interval <= timedelta(0):
            raise ValueError("reconsider_interval 必须为正")
        if self.reconsider_interval < MIN_RECONSIDER_INTERVAL:
            # 下限就按方案 §9 的原话"**至少** 24 小时"写死：配置可以往上调，不能往下。
            # 心跳那两个旋钮（15 分钟、6 小时）都落在下限以下，所以这条**同时挡住"手滑接错旋钮"**——
            # 只写一条"不短于 1 小时"是挡不住 `max_review_interval=6 小时` 的，我的用例当场证明了这一点。
            raise ValueError(f"reconsider_interval 不能短于 {MIN_RECONSIDER_INTERVAL}：心愿冷却不是心跳复查间隔")
        if not 1 <= self.max_candidates <= 3:
            raise ValueError("max_candidates 只能是 1 到 3（方案 §8 首批上限）")


@dataclass(frozen=True, slots=True)
class WishTrigger:
    """一次**有效**触发。有效性由集成层按方案 §3 的来源表判定，这里只负责去重与冷却。"""

    event_id: str
    kind: str  # wage_settled / owner_suggestion / life_review / world_event / weather_changed …
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class WishState:
    """A 的 `read(pet_id)` 读回来的活动心愿。"""

    wish_id: str
    revision: int
    status: str
    destination_key: str
    title: str
    funds_goal: int
    # A 存着的等待原因**并集**（`WishView.waiting_reasons`）。策略用它做两件事：
    #   · 取出其中的生活侧三条，跟这一轮算出来的比——**变了才写**；
    #   · 其余（研究与资料那一半）**原样透传**给页面，并作为"还不能交接"的依据。
    # **不在这里重算研究侧**：那是 A 的列、A 的判断，重算一份迟早和它不一致，
    # 于是每一轮都判成"变了"、每一轮写一次。
    waiting: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WishFacts:
    """集成层一次读齐的事实。策略不自己去读，也不接受"稍后再补"的懒加载对象。"""

    pet_id: str
    activated: bool = True  # 已入住；待领养居民为 False
    maintenance: bool = False  # 取 `RuntimeStore.paused`（TRV-00 §4.5），**不要再读一次那一列**
    balance: int = 0  # 游戏金币余额，取 `WebEconomy.wallet(pet_id).balance`
    active_journey: bool = False
    commitments: tuple[str, ...] = ()  # 有效承诺：待回复、工钱、到家
    # 今天还有没有认知调用额度（`projector.budget_facts`）。**只影响"要不要再问一次大脑"**，
    # 所以它出现在 `SkipReason` 里而不是写进心愿——`quota_denied` 那个等待码归 A 写。
    quota_available: bool = True
    wish: WishState | None = None
    # 这一轮看到的触发事件。**「是不是新的」由它的 `occurred_at` 与 `last_considered_at` 比出来**，
    # 不另外传一份「已处理过的 id 集合」——那份集合**填不满**：
    # A 只能按 `(pet_id, trigger_event_id)` 查出「这个事件建出过心愿吗」，
    # 而大脑说「留在家、不形成心愿」的那一轮根本没有心愿行可查。
    # 集合缺了一条就会把重放当成新事件，**而那个方向是失败开放的**：同一个事件每个 tick 都问一次大脑。
    trigger: WishTrigger | None = None
    # 上一次**为这只宠物考虑过心愿**的时刻，None = 从没考虑过。截止时刻由 `policy.reconsider_interval`
    # 现算，**不接受传进来的截止时刻**（见模块开头那一节）。
    #
    # **必须是按宠物存的，不能只挂在心愿那一行上**：冷却要挡的恰恰是"考虑过、但没形成心愿"
    # （DS 可以选择留在家里）——那时根本没有心愿行可挂。只挂在心愿上，这种宠物每一轮都会再问一次大脑。
    last_considered_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class FundsGap:
    """缺钱要说清缺多少——缺什么页面就说什么（UI 第 3 条）。**这是游戏金币，不是平台额度。**"""

    target_coins: int
    current_coins: int

    @property
    def short_by(self) -> int:
        return max(0, self.target_coins - self.current_coins)


@dataclass(frozen=True, slots=True)
class WishCandidate:
    """给页面和 C 看的心愿。**类型上没有任何能喂给 depart 的字段**（TRV-00 §0.3）。"""

    wish_id: str
    wish_revision: int
    destination_key: str
    title: str
    blocked_by: tuple[str, ...] = ()

    @property
    def executable(self) -> bool:
        """**字面常假**，不是可变字段。有心愿不等于可以出发——那要经 C 现有的 offers 规则。"""
        return False


@dataclass(frozen=True, slots=True)
class WishDecision:
    """一次评估的结论。集成层照 `action` 动作，其余字段是给页面和日志看的。"""

    action: str
    # 这一刻的**全部**等待原因：B 算出来的生活侧三条 ＋ A 存着的研究侧那一半（原样透传）。
    # **永远按当前事实给出**，即使这次不写；页面可以直接显示。
    waiting: tuple[str, ...] = ()
    # **只有这三条是 B 能写的**，直接喂给 `update_waiting`——把整个 `waiting` 传过去会被
    # `WishRejected` 拒收（A 只收 `LIFE_REASONS`）。分成两个字段而不是让调用方自己过滤：
    # 过滤规则写在两处就会漂，而漂了之后拒收是运行期才发现。
    life_waiting: tuple[str, ...] = ()
    skip_reason: str | None = None
    funds: FundsGap | None = None
    candidate: WishCandidate | None = None
    expected_revision: int | None = None  # 这次读到的心愿版本；写回时带上，旧评估不许确认它没读到的新版本
    # **非空才算"这一次考虑过"**，集成层把它存成新的 `last_considered_at`（A 的 `considered_in`）。
    # 由策略给、不由集成层自己判：否则"哪些动作算考虑过"会在两边各写一份，迟早分叉。
    # 只有 `ask_brain` 会给值——刷新一次等待原因不是一次考虑，不该把冷却往后推。
    #
    # **接线时两条容易走反，写在这里给动手的人看：**
    # 1. **只在这个值非空那一轮调 `considered_in`，不是每一轮 tick 都调。** 每轮都调的话，
    #    上次考虑时刻永远被推到现在、冷却永远到不了期，而那张表只往后走、推错了退不回来。
    #    实测：15 分钟一跳跑 48 小时，每轮都调只得到 **1 次**机会（且此后永远没有），正确做法是 2 次。
    # 2. **拿到非空值就无条件记下，不要等大脑答完再按结果决定记不记。** 大脑说"留在家、不形成心愿"
    #    的那一轮**也是考虑过**——它就发生在这一轮 `ask_brain` 里，只是结局不同。
    #    **按动作取值（这个字段非空），不按结果描述（有没有形成心愿）**；按结果分会把同一轮的两种结局分到两边去。
    considered_at: datetime | None = None
    # **只是输出**：给页面显示、给 A 存一份缓存。闸不读它（见模块开头），`WishFacts` 里也没有这个字段。
    reconsider_after: datetime | None = None
    policy_version: str = WISH_POLICY_VERSION


def life_waiting_of(facts: WishFacts) -> tuple[str, ...]:
    """**B 这一侧**的等待原因——只有三条，见 `LIFE_SIDE`。顺序固定，便于断言与显示。

    研究与资料那一半（`research_*` / `fact_*` / `plan_stale` / `weather_unsuitable` / `quota_denied`）
    **不在这里算**：它们是 A 的列、A 的判断，这里只从 `wish.waiting` 原样透传。
    重算一份迟早会和 A 存的不一致，于是每一轮都判成「变了」、每一轮写一次。

    `missing_funds` 只在**有心愿**时才谈得上——没有心愿就没有资金目标可比。
    """
    reasons: list[str] = []
    if facts.maintenance:
        reasons.append(WaitingReason.MAINTENANCE.value)
    if facts.commitments:
        reasons.append(WaitingReason.COMMITMENT_ACTIVE.value)
    if facts.wish is not None and facts.balance < facts.wish.funds_goal:
        reasons.append(WaitingReason.MISSING_FUNDS.value)
    return tuple(reasons)


def _split(stored: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """把 A 存的并集拆回两侧：(生活侧, 研究侧)。拆分依据是 `LIFE_SIDE` 这个封闭集合。"""
    return tuple(r for r in stored if r in LIFE_SIDE), tuple(r for r in stored if r not in LIFE_SIDE)


def _hard_skip(facts: WishFacts) -> str | None:
    """挡住一切的闸：这些情况下连"已经想好的那个"都不推进。"""
    if not facts.activated:
        return SkipReason.NOT_ACTIVATED.value
    if facts.maintenance:
        return SkipReason.MAINTENANCE.value
    if facts.wish is not None and facts.wish.status not in OPEN_STATUSES:
        return SkipReason.WISH_CLOSED.value
    if facts.active_journey:
        return SkipReason.ACTIVE_JOURNEY.value
    if facts.commitments:
        return SkipReason.COMMITMENT_ACTIVE.value
    return None


def _think_skip(facts: WishFacts, policy: WishPolicy, now: datetime) -> str | None:
    """只挡"重新想一次"的闸。**只在还没有活动心愿时问这一段**——见模块开头那一节。

    **什么叫"新事件"：它发生在上一次考虑之后。** 更早发生的，上一次考虑时就已经看见它了，
    再投一次不是新消息——所以按 `trigger.occurred_at` 与 `last_considered_at` 比，
    **不另收一份「已处理过的 id 集合」**。理由见 `WishFacts.trigger`：那份集合填不满，而且缺一条就失败开放。

    **重放本身永远不构成"新的有效事件"**：同一个事件再投一次，跟什么都没发生是一回事。
    但它也不该把冷却到期后那次正常的重新考虑一并挡掉——所以冷却到了就照常想，
    只是原因记成"这一轮本来就该想了"，不是"因为你又投了一次"。

    `last_considered_at` 为空表示从没考虑过：**第一次总要给 TA 一次机会**，
    否则一只没有任何事件的宠物永远不会有心愿。但这条只对普通 tick 成立，重放不享受。
    """
    trigger = facts.trigger
    last = None if facts.last_considered_at is None else ensure_utc(facts.last_considered_at, "last_considered_at")
    # 截止时刻在这里**现算**，用的是本策略自己的间隔——不读任何传进来的截止时刻
    after = None if last is None else last + policy.reconsider_interval
    elapsed = after is not None and now >= after
    # 新事件 = 发生在上一次考虑**之后**。从没考虑过时，任何事件都是新的。
    fresh = trigger is not None and (last is None or ensure_utc(trigger.occurred_at, "occurred_at") > last)
    if trigger is not None and not fresh and not elapsed:
        return SkipReason.TRIGGER_REPLAYED.value
    if trigger is None and after is not None and now < after:
        return SkipReason.COOLING_DOWN.value
    if not facts.quota_available:
        return SkipReason.QUOTA_DENIED.value
    return None


def evaluate(facts: WishFacts, policy: WishPolicy, now: datetime) -> WishDecision:
    """这一次该不该动、还差什么、够不够交接。纯函数：同样的输入永远得到同样的结论。"""
    now = ensure_utc(now, "now")
    wish = facts.wish
    stored_life, research = _split(tuple(wish.waiting)) if wish is not None else ((), ())
    life = life_waiting_of(facts)
    waiting = life + research  # 生活侧在前、研究侧按 A 存的顺序在后：同一组事实每次读出来一样
    funds = FundsGap(wish.funds_goal, facts.balance) if wish is not None and facts.balance < wish.funds_goal else None
    candidate = WishCandidate(wish.wish_id, wish.revision, wish.destination_key, wish.title, waiting) if wish is not None else None
    revision = wish.revision if wish is not None else None

    def decide(action: str, *, skip: str | None = None, reconsider: datetime | None = None,
               considered: datetime | None = None) -> WishDecision:
        return WishDecision(action=action, waiting=waiting, life_waiting=life, skip_reason=skip, funds=funds,
                            candidate=candidate, expected_revision=revision, considered_at=considered,
                            reconsider_after=reconsider, policy_version=policy.version)

    blocked = _hard_skip(facts)
    if blocked is not None:
        return decide(WishAction.SKIP.value, skip=blocked)
    if wish is None:
        thinking = _think_skip(facts, policy, now)
        if thinking is not None:
            return decide(WishAction.SKIP.value, skip=thinking)
        # 这一次真的要花一次模型调用，所以它算"考虑过"：`considered` 给值，冷却从这一刻起算。
        return decide(WishAction.ASK_BRAIN.value, reconsider=now + policy.reconsider_interval, considered=now)
    if not waiting:
        return decide(WishAction.HAND_OFF.value)
    # **只比生活侧**：研究侧是 A 写的，它变没变不该由我来触发一次写。
    if life == stored_life:
        return decide(WishAction.SKIP.value, skip=SkipReason.UNCHANGED.value)
    return decide(WishAction.UPDATE_WAITING.value, reconsider=now + policy.reconsider_interval)
