"""TRV-03 消费的外部端口（调用方视角）。实现不在这里：ResearchPort 归 I（TRV-04），ArtBrief 编译归 P（TRV-05）。

字段照 `docs/coordination/travel-wish/TRV-00-contract-v1.md`（4.3、11.3、11.4）；合同里没写、A 这边需要的两个
（`ResearchFact.key`／`subject`、`ResearchResult.draft`）已报 I 补登。

**失败必须分清两类**（合同 4.3）：
  - `ResearchNotSent`：确定没发出（连接前就被拒、参数校验失败）→ 账本释放，可以开新的一代；
  - `ResearchUnknown`：可能已发出（超时、连接中断、拿到响应前崩溃）→ 不重发，挂 `research_unknown`，
    旧 operation 结清前不换号重发。
  端口抛出的其他任何异常，调用方一律按 `ResearchUnknown` 处理（保守：宁可等对账，不重复付费）。
端口内部**不重试、不自动换 Pro**；额度预占与结算由调用方（A）做，I 不对同一个 operation 再扣一次。

**「检索真的执行过」⟺ `tool_executions >= 1` 且 `tool_execution_ids` 非空**（合同 11.3，写死）。
回答正文里出现「我搜索了」「据某某网站」一律不算；这样的结果里的事实不落为已核验、不进计划。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class ResearchNotSent(Exception):
    """确定没有发出。"""


class ResearchUnknown(Exception):
    """可能已经发出、结果没确认。"""


@dataclass(frozen=True, slots=True)
class ResearchRequest:
    """只带公开信息：目的地、城市、日期窗口、白名单兴趣标签。
    **不带**私聊、住址、照片、家庭资料、主人叮嘱原文、给主人的理由（方案 §11.1；T11）。"""

    operation_id: str
    wish_id: str
    wish_revision: int
    destination_key: str
    destination_name: str
    city: str
    window_start: str | None = None
    window_end: str | None = None
    interests: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResearchSource:
    source_id: str
    url: str | None = None
    publisher: str | None = None
    retrieved_at: str | None = None  # 抓取时间：不刷新材料本身的年代
    published_at: str | None = None


@dataclass(frozen=True, slots=True)
class ResearchFact:
    """一条待核事实（合同 11.4）。`key` 在本次结果内唯一，草稿用它引用；落库时换成稳定的 fact_id。"""

    key: str
    category: str  # 见 facts.CATEGORIES
    subject: str  # 说的是哪个地方
    value: Any
    source_ids: tuple[str, ...] = ()
    observed_at: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    verification: str = "search"  # 端口给的核验方法：search／map／weather_api／official_page
    conclusion: str | None = None  # 端口自己的结论：只记录，程序另核，不照单全收
    blocks_departure: bool = False  # 端口认为这条影响能不能去；程序按类别再判一次


@dataclass(frozen=True, slots=True)
class DraftStop:
    name: str
    role: str  # primary／suggestion（合同第 8 节）
    why: str = ""
    tip: str = ""
    fact_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResearchDraft:
    """模型按 TA 的口吻起草的计划：程序核对后才发布，站点、提醒都要由已核验事实支持。"""

    title: str
    summary: str
    stops: tuple[DraftStop, ...]
    owner_tips: tuple[str, ...] = ()
    tip_fact_keys: tuple[tuple[str, ...], ...] = ()  # 与 owner_tips 一一对应
    rain_alternative: str | None = None


@dataclass(frozen=True, slots=True)
class ResearchResult:
    requested_model: str
    effective_model: str | None
    provider_request_id: str | None
    usage: dict = field(default_factory=dict)  # 原样保留，供对账
    search_uses: int | None = None
    tool_executions: int = 0  # 真实工具执行块的条数（server_tool_use／web_search_tool_result）
    tool_execution_ids: tuple[str, ...] = ()
    cost_amount: float | None = None  # 未核就是 None，不写 0
    cost_currency: str | None = None
    sources: tuple[ResearchSource, ...] = ()
    facts: tuple[ResearchFact, ...] = ()
    draft: ResearchDraft | None = None

    @property
    def searched(self) -> bool:
        """合同 11.3 的判据，写死：执行块条数 ≥ 1 且执行标识非空。"""
        return self.tool_executions >= 1 and bool(self.tool_execution_ids)


class ResearchPort(Protocol):
    def research(self, request: ResearchRequest) -> ResearchResult:
        """发一次研究请求。不重试、不换模型；失败按上面两类抛出。"""
