"""旅行心愿 → 联网攻略 → 自动手账（TRV-03，A 持有）。

装配入口：组合根（I）调 `install_travel(...)`，拿回服务对象；A 不改 `web_composition.py`（合同第 7 节、工作单 TRV-09）。
  - `wishes`：心愿命令端口（B → A 的 propose／update_waiting／read／cancel；C → A 的 ready_plan_in／link_journey_in）；
  - `journals`：手账（计划页随研究发布；回忆页是世界事件 sink：`journals.on_world_event`，请把它登记进世界事件的 sink 列表）；
    GET `/travel/plans/{plan_id}` 用 `journals.plan_view_in(conn, pet_id, plan_id, plan_revision=None)`：纯读、冻结视图，路由不直接读表；
  - `research`：研究任务（任务类型 `travel_research`）。哪个后台慢通道来调 `research.run_pending()` 由 I 定；
    **GET 路由只调读接口，绝不调 run_pending**（方案 §13：读接口零外发）。

没有接研究端口（I 的 TRV-04 适配器）时，`research.run_pending()` 什么都不做，心愿停在 `research_pending`——
不造一个"没查到"，也不回退到旧指南那条模型写攻略的路。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .journal import TravelJournalService
from .research import TravelResearchService
from .service import RESEARCH_KIND, TravelWishService
from .views import PlanRevisionView, PlanView

__all__ = ["PlanRevisionView", "PlanView", "RESEARCH_KIND", "TravelJournalService", "TravelResearchService", "TravelServices", "TravelWishService",
           "install_travel"]


@dataclass(frozen=True, slots=True)
class TravelServices:
    wishes: TravelWishService
    research: TravelResearchService
    journals: TravelJournalService


def install_travel(storage, tasks, *, ledger=None, research_port=None, paused_in: Callable | None = None,
                   interest_whitelist: frozenset[str] | None = None, settings=None, illustrations=None,
                   identity_of: Callable | None = None, mood_of: Callable | None = None,
                   visit_of: Callable | None = None) -> TravelServices:
    """`paused_in(conn, pet_id) -> bool` 请接 `RuntimeStore.paused(pet_id, conn=conn)`（合同 4.5，不再读一次那一列）。
    额度：`settings.web_travel_research_per_pet_daily`（默认 2）、`settings.web_travel_research_daily_cap`（默认 0＝不限）；
    config 里没有这两个字段时用默认值（字段由 config 的持有人加）。
    **`research_port` 与 `ledger` 必须成对**：研究是付费调用，接了端口没接额度账本就当场报错（I 核出的 fail-open 耦合），不等到第一次发送。"""
    if research_port is not None and ledger is None:
        raise ValueError("install_travel: research_port 必须和 ledger 一起接——研究是付费调用，没有额度账本就不许发")
    wishes = TravelWishService(storage, tasks)
    if paused_in is not None:
        wishes.paused_in = paused_in
    wishes.interest_whitelist = interest_whitelist
    research = TravelResearchService(storage, tasks, wishes, ledger=ledger)
    research.port = research_port
    research.per_pet_daily = int(getattr(settings, "web_travel_research_per_pet_daily", 2) or 0)
    research.global_daily = int(getattr(settings, "web_travel_research_daily_cap", 0) or 0)
    journals = TravelJournalService(storage, illustrations)  # illustrations 为空时只出文字手账，不画图
    if identity_of is not None:  # (conn, pet_id) -> JournalIdentity | None：只认主人原照／档案真照（P 的编译器把关）
        journals.identity_of = identity_of
    if mood_of is not None:
        journals.mood_of = mood_of
    if visit_of is not None:  # (journey_id) -> 这趟旅程真实的到访（开始过的才算）：回忆页只按它盖章
        journals.visit_of = visit_of
    journals.complete_wish_in = wishes.complete_in  # 旅程结束：关联的心愿落定为 completed
    research.journals = journals
    return TravelServices(wishes=wishes, research=research, journals=journals)
