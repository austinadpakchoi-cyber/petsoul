"""旅行心愿（TRV-03）的状态、原因码与只读视图。

方案 §9、§10 的语义必须分开，这里一个码只表达一件事：
  - `missing_funds`（宠物游戏金币不够）≠ `quota_denied`（平台调用额度不够）；
  - `research_unknown`（请求可能已发出、结果没确认）≠ `fact_unverified`（查了，没有可用来源）；
  - `fact_stale`（资料过期）≠ 地名不存在；
  - 手账图 `unknown` ≠ 确认失败（沿用现有四态）。

等待原因**按写入方分两份**：B 写生活侧（钱、承诺、维护态），A 写研究侧。B 更新时只替换它那一份，
不会把 A 的研究原因冲掉，反之亦然。心愿是否 `ready` 由两份的并集现算。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---- 心愿业务主状态（方案 §9：active → ready → linked → completed / cancelled）----
ACTIVE, READY, LINKED, COMPLETED, CANCELLED = "active", "ready", "linked", "completed", "cancelled"
OPEN_STATES = (ACTIVE, READY)
WISH_STATES = (ACTIVE, READY, LINKED, COMPLETED, CANCELLED)

# ---- 等待原因：生活侧（B 写）----
MISSING_FUNDS = "missing_funds"
COMMITMENT_ACTIVE = "commitment_active"
MAINTENANCE = "maintenance"
LIFE_REASONS = frozenset({MISSING_FUNDS, COMMITMENT_ACTIVE, MAINTENANCE})

# ---- 等待原因：研究侧（A 写）----
RESEARCH_PENDING = "research_pending"  # 研究还没做完（排队或进行中）
RESEARCH_UNKNOWN = "research_unknown"  # 请求可能已发出、结果没确认：不自动重发，旧 operation 结清前不换号重发
RESEARCH_FAILED = "research_failed"  # 确定没拿到结果
QUOTA_DENIED = "quota_denied"  # 平台调用额度不够（不是宠物的钱）
FACT_UNVERIFIED = "fact_unverified"  # 关键事实没有可用来源（假来源、只有模型自述、没查到）——TRV-00 5.2 待补登
FACT_STALE = "fact_stale"  # 关键事实过期或不覆盖出行时间
FACT_CONFLICTING = "fact_conflicting"  # 关键事实互相矛盾（合同 5.2：统一用 P 编译器那套形容词）
PLAN_STALE = "plan_stale"  # 这版计划按的是旧版心愿（B 提、I 裁单列）。写入方待 B／I 定：按合同 §2 的修订号语义，
# `wish_revision` 每次状态变更都 +1，拿它比会一直判过时；定下来之前 B 写它会被明确拒绝，不会让心愿悄悄卡住
WEATHER_UNSUITABLE = "weather_unsuitable"  # 已核实的天气不适合按计划出门
RESEARCH_REASONS = frozenset({RESEARCH_PENDING, RESEARCH_UNKNOWN, RESEARCH_FAILED, QUOTA_DENIED,
                              FACT_UNVERIFIED, FACT_STALE, FACT_CONFLICTING, WEATHER_UNSUITABLE, PLAN_STALE})
ALL_REASONS = LIFE_REASONS | RESEARCH_REASONS

# ---- 研究任务状态（与心愿主状态分开保存，不能用一个业务状态盖住"已可能发出"）----
R_QUEUED, R_RUNNING, R_READY, R_FAILED, R_UNKNOWN = "queued", "running", "ready", "failed", "unknown"

# ---- 研究回执状态（一行一次发送尝试；operation_id 与预占同号）----
INTENT = "intent"  # 已持久记下发送意图与预占，随后在事务外发送
ANSWERED = "answered"  # 响应已落盘，还没发布成计划
PUBLISHED = "published"  # 已发布成计划修订
NOT_SENT = "not_sent"  # 确定没发出（账本已释放），可以开新的一代
UNKNOWN = "unknown"  # 可能已发出、结果没确认
FAILED = "failed"  # 发出了、确定没有可用结果
DISCARDED = "discarded"  # 响应到了，但心愿已取消或换了轮次：不发布
RECEIPT_STATES = (INTENT, ANSWERED, PUBLISHED, NOT_SENT, UNKNOWN, FAILED, DISCARDED)
MAYBE_SENT = (INTENT, UNKNOWN)

# ---- 手账 ----
PHASE_PLAN, PHASE_MEMORY = "plan", "memory"
IMAGE_STATES = ("processing", "ready", "failed", "unknown")  # 与 schemas.web.social.PhotoStatus 同口径

# ---- 站点在计划里的角色（方案 §6：一个真实主目的地，附属的只是"顺路建议"）----
ROLE_PRIMARY, ROLE_SUGGESTION = "main", "suggested"  # TRV-00 第 8 节（统一到 P 编译器的叫法）

MAX_CANDIDATES = 3
MAX_INTEREST_TAGS = 8


class VersionConflict(Exception):
    """带版本条件的命令没有命中：调用方看到的心愿／计划版本已经过时。调用方整体回滚。"""


class WishRejected(ValueError):
    """命令参数不合法（候选超过 3 个、选中项越界、兴趣标签不在白名单等）。"""


@dataclass(frozen=True, slots=True)
class WishRef:
    wish_id: str
    wish_revision: int
    created: bool
    status: str


@dataclass(frozen=True, slots=True)
class PlanRef:
    """给 C 在出发事务里复核用：只读，不含私有档案。"""

    plan_id: str
    plan_revision: int
    wish_id: str
    wish_revision: int
    pet_id: str
    destination_key: str
    valid_from: str | None
    valid_until: str | None
    preconditions: tuple[str, ...]  # 出发时必须仍然有效的关键事实（fact_id）

    @property
    def valid_window(self) -> tuple[str | None, str | None]:
        """合同 4.2 的名字：(valid_from, valid_until)。**按字段名取，不要按位置解**（本类比合同多一个 pet_id）。"""
        return self.valid_from, self.valid_until


@dataclass(frozen=True, slots=True)
class WishView:
    """纯读视图（GET 只读这个，绝不触发研究、生图或出行）。"""

    wish_id: str
    pet_id: str
    wish_revision: int
    status: str
    destination_key: str
    destination_name: str
    city: str
    owner_reason: str
    funds_goal: int | None
    waiting_reasons: tuple[str, ...]
    research_state: str | None
    research_round: int
    plan_id: str | None
    plan_revision: int | None
    journey_id: str | None
    reconsider_after: str | None  # TRV-00 5.4：不叫 next_review_at（那是心跳的列）；只是给页面看的缓存值
    last_considered_at: str | None  # 按宠物的「上次考虑」（没有心愿也有）：冷却闸读它＋策略间隔（合同 17.1）
    # 这版计划是否按旧版心愿内容做的（A 判，B 只读）。**本批恒为 False**：propose 之后没有任何命令能改心愿内容
    # （换方向＝取消后新建；重研究开新一轮并挂 research_pending）。有了改内容的路，由 A 在那一刻判它
    plan_stale: bool = False
    target_coins: int | None = None  # missing_funds 时页面说缺多少（游戏金币）
    current_coins: int | None = None
    candidates: tuple[dict, ...] = field(default=())


def waiting_union(life: frozenset[str] | set[str], research: frozenset[str] | set[str]) -> tuple[str, ...]:
    """两份等待原因的并集，按固定顺序输出（同一组原因每次读出来一样）。"""
    merged = set(life) | set(research)
    return tuple(sorted(merged))


def status_for(current: str, waiting: tuple[str, ...], has_plan: bool) -> str:
    """只在 active／ready 之间现算；已关联、已完成、已取消的不因等待原因变化而复活。"""
    if current not in OPEN_STATES:
        return current
    return READY if has_plan and not waiting else ACTIVE
