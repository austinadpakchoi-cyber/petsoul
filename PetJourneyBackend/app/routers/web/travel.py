"""旅行心愿与计划（TRV-00 合同 §7 路由矩阵、§23.4；I 持有路由与 DTO 组装，A 持有只读视图）。

- `GET /travel/wish`：按当前宠物读「活动心愿与最新计划指针」，给地图面板与攻略列表；**没有心愿回 200＋null**（合同 §23.4）。
- `GET /travel/plans/{plan_id}`：一个心愿的计划全集（每一版都给）；不是这只宠物的计划与不存在一样，一律 404。
  先挂过占位（手账视图缺 4 个字段），A 2026-09-24 补齐后换成实现。

纯读：只调 A 的视图（`wishes.read` / `plan_view_in`），不读 A 的表、不推进世界、不调供应商。
**唯一的 join**：计划关联的真实行程的标价与是否用券，读 C 的 `journeys.repo.get`（合同写明由路由层 join，A 不读 C 的表）。
站点导航链接沿用旧攻略的 `with_links`（核实过、有坐标才给；后端给，前端不自己拼）。
`pet_id` 省略时沿用 `require_pet` 的既有惯例（合同 §29.5）：能照顾的宠物恰好一只才默认它，否则 409 `pet_required`；
别人家的宠物由 `require_pet` 挡下，和「不存在」一样读不到。
"""

from __future__ import annotations

from fastapi import Depends, Request

from ...schemas.web.common import Capability, CapabilityStatus, WebErrorCode
from ...schemas.web.social import PhotoStatus
from ...schemas.web.travel import (TravelFact, TravelFactVerdict, TravelIdentityMode, TravelJournal, TravelJournalPhase,
                                   TravelJourneySummary, TravelOwnerTip, TravelPlan, TravelPlanRevision, TravelResearchStatus,
                                   TravelSource, TravelStop, TravelStopRole, TravelWaitingReason, TravelWish, TravelWishCandidate,
                                   TravelWishStatus)
from ...utils import parse_dt
from ...web_journey.guides import with_links
from ...web_platform import WebAPIError, WebPrincipal, require_principal
from ...web_travel.views import plan_view_in
from ._shared import cap, require_pet, web_of, web_router

router = web_router("travel")


def capabilities(settings) -> list[Capability]:
    return [
        cap("travel.wish", "travel", CapabilityStatus.available, "心愿只读：地图面板与攻略列表；没有心愿时为 null"),
        cap("travel.plan", "travel", CapabilityStatus.available, "计划只读：每一版的站点、提醒、来源、事实与手账；别人家的与不存在一样 404"),
    ]


def _wish(view) -> TravelWish:
    """A 的 `WishView` → 对外 DTO。候选只给名字与挡住它的原因，`executable` 字面常假（合同 §3）。"""
    return TravelWish(
        wish_id=view.wish_id, pet_id=view.pet_id, wish_revision=view.wish_revision, status=TravelWishStatus(view.status),
        destination_key=view.destination_key, destination_name=view.destination_name, city=view.city, owner_reason=view.owner_reason,
        funds_goal=view.funds_goal, waiting_reasons=[TravelWaitingReason(code) for code in view.waiting_reasons],
        research_state=TravelResearchStatus(view.research_state) if view.research_state else None, research_round=view.research_round,
        plan_id=view.plan_id, plan_revision=view.plan_revision, journey_id=view.journey_id,
        reconsider_after=parse_dt(view.reconsider_after) if view.reconsider_after else None,
        last_considered_at=parse_dt(view.last_considered_at) if view.last_considered_at else None,
        plan_stale=view.plan_stale, target_coins=view.target_coins, current_coins=view.current_coins,
        candidates=[TravelWishCandidate(destination_key=c["destination_key"], title=c["name"],
                                        blocked_by=[TravelWaitingReason(code) for code in c.get("blocked_by", [])])
                    for c in view.candidates],
    )


@router.get("/travel/wish", response_model=TravelWish | None)
def read_wish(request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> TravelWish | None:
    """这只宠物此刻的活动心愿；没有就是 null（不是 404：「没有心愿」是正常状态）。"""
    home = require_pet(request, principal, pet_id)
    view = web_of(request).travel.wishes.read(home.pet_id)
    return None if view is None else _wish(view)


def _dt(value):
    return parse_dt(value) if value else None


def _source(item) -> TravelSource:
    """计划层来源是视图的 dataclass，手账版式里的来源是 dict：两种都按同一组字段取。"""
    get = item.get if isinstance(item, dict) else (lambda key: getattr(item, key, None))
    return TravelSource(source_id=get("source_id"), url=get("url"), publisher=get("publisher"),
                        retrieved_at=_dt(get("retrieved_at")), published_at=_dt(get("published_at")))


def _stop(stop, station_id: str | None = None, visited: tuple = ()) -> TravelStop:
    links = with_links({"name": stop.name, "verified": stop.verified, "lat": stop.lat, "lng": stop.lng})
    return TravelStop(station_id=station_id, name=stop.name, role=TravelStopRole(stop.role), why=stop.why or None, tip=stop.tip or None,
                      fact_ids=list(stop.fact_ids), verified=stop.verified, lat=stop.lat, lng=stop.lng, nav_url=links["nav_url"],
                      visited_event_ids=list(visited or stop.visited_event_ids))


def _journal(journal, plan_id: str, stops) -> TravelJournal:
    """一页手账。版式里的站点 `st-i` 与这一版计划的第 i 个站点同源（A 建页时按计划站点顺序编号），
    缘由、小贴士、是否核实、导航链接取自那一站；版式里没有的就不编。"""
    layout, image = journal.layout, journal.image
    stations = []
    for index, station in enumerate(layout.get("stations", [])):
        source = stops[index] if index < len(stops) else None
        if source is not None:
            stations.append(_stop(source, station.get("station_id"), tuple(station.get("visited_event_ids", []))))
        else:
            stations.append(TravelStop(station_id=station.get("station_id"), name=station["name"], role=TravelStopRole(station["role"]),
                                       fact_ids=list(station.get("fact_ids", [])), lat=station.get("lat"), lng=station.get("lng"),
                                       visited_event_ids=list(station.get("visited_event_ids", []))))
    status = image.status if image is not None else None
    return TravelJournal(
        journal_id=journal.journal_id, journal_revision=journal.journal_revision, plan_id=layout.get("plan_id", plan_id),
        plan_revision=journal.plan_revision, phase=TravelJournalPhase(journal.phase), title=layout.get("title"), summary=layout.get("summary"),
        stations=stations, owner_tips=[TravelOwnerTip(text=t["text"], fact_ids=list(t.get("fact_ids", []))) for t in layout.get("tips", [])],
        rain_alternative=layout.get("rain_alternative"), sources=[_source(s) for s in layout.get("sources", [])],
        identity_mode=TravelIdentityMode(journal.identity_mode), identity_note=journal.identity_note, template_revision=journal.template_revision,
        image_status=PhotoStatus(status) if status else None, image_url=image.url if image is not None else None,
        image_refused=layout.get("image_refused"),
        redraw_ticket=image.ticket if status in (PhotoStatus.failed.value, PhotoStatus.unknown.value) else None,
        event_ids=list(journal.event_ids), created_at=parse_dt(journal.created_at), updated_at=_dt(journal.updated_at))


def _revision(web, pet_id: str, revision) -> TravelPlanRevision:
    journey = None
    if revision.journey_id:
        record = web.journeys.repo.get(revision.journey_id)
        if record is not None:  # `fee` 永远是标价；实付与否只看 fare_waived（合同 §30）
            journey = TravelJourneySummary(journey_id=record.journey_id, fare=record.fee, fare_waived=record.fare_waived)
    return TravelPlanRevision(
        plan_id=revision.plan_id, plan_revision=revision.plan_revision, wish_id=revision.wish_id,
        wish_revision_at_build=revision.wish_revision_at_build, pet_id=pet_id, destination_key=revision.destination_key,
        title=revision.title, summary=revision.summary, rain_alternative=revision.rain_alternative,
        stops=[_stop(stop) for stop in revision.stops],
        owner_tips=[TravelOwnerTip(text=tip.text, fact_ids=list(tip.fact_ids)) for tip in revision.tips],
        preconditions=list(revision.preconditions), sources=[_source(s) for s in revision.sources],
        facts=[TravelFact(fact_id=f.fact_id, category=f.category, subject=f.subject, value=f.value, source_ids=list(f.source_ids),
                          verification=f.verification, conclusion=f.conclusion, verdict=TravelFactVerdict(f.verdict),
                          blocks_departure=f.blocks_departure, retrieved_at=_dt(f.retrieved_at), published_at=_dt(f.published_at),
                          observed_at=_dt(f.observed_at), valid_from=_dt(f.valid_from), valid_until=_dt(f.valid_until))
               for f in revision.facts],
        valid_from=_dt(revision.valid_from), valid_until=_dt(revision.valid_until), journey=journey,
        journals=[_journal(j, revision.plan_id, revision.stops) for j in revision.journals], created_at=parse_dt(revision.created_at))


@router.get("/travel/plans/{plan_id}", response_model=TravelPlan)
def read_plan(plan_id: str, request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> TravelPlan:
    """一个心愿的计划全集：每一版都给（旧版都留着），`current_revision` 指最新发布的那一版。
    不是这只宠物的计划、不存在的计划、还没发布过的心愿，都回同一个 404——与「不存在」不可区分（合同 §7）。"""
    home = require_pet(request, principal, pet_id)
    web = web_of(request)
    image_in = web.travel.journals.image_in
    with request.app.state.storage.connect() as conn:
        current = plan_view_in(conn, home.pet_id, plan_id, image_in=image_in)
        if current is None:
            raise WebAPIError(WebErrorCode.not_found, "没有这份计划。", 404, details={"reason": "plan_not_found"})
        views = [current if number == current.current_revision else plan_view_in(conn, home.pet_id, plan_id, number, image_in=image_in)
                 for number in current.revisions]
    return TravelPlan(plan_id=plan_id, wish_id=current.wish_id, current_revision=current.current_revision,
                      revisions=[_revision(web, home.pet_id, view.revision) for view in views if view is not None])
