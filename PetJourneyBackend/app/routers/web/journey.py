"""旅途：出发站、出发、地图快照（交通段/车辆/音符电视入口/到达上下文）、到访与店内活动、改选寻味推荐。

不存在“舱室”路由：一起听看是 /journey 地图上的面板，媒体会话见 companion_media.py。

0.4.0 家庭：旅程属于宠物；?pet_id= 指明是哪只（只照顾一只时可省略）。看旅程、到访与攻略要是这只宠物的家人；
替 TA 出发（花 TA 账户里的钱）需要“可花费”权限（管理员；共同照顾者在家庭允许时）；给建议只要“照顾”权限，由 TA 自己决定。
"""

from __future__ import annotations

from fastapi import Depends, Query, Request
from fastapi.responses import FileResponse

from ...schemas.web.common import Capability, CapabilityStatus, WebErrorCode
from ...schemas.web.journey import (
    DepartRequest,
    DestinationOption,
    JourneySuggestion,
    Place,
    PlaceProvider,
    PlannedLegPreview,
    ReferenceFare,
    SuggestRequest,
    TravelGuide,
    TripPlanPreview,
    Visit,
    VisitActionRequest,
    VisitChoiceRequest,
)
from ...schemas.web.common import CoordSystem, DataOrigin, LatLng
from ...schemas.web.transport import (
    BasemapProvider,
    BasemapUnavailableReason,
    BasemapView,
    JourneyMapSnapshot,
    LegKind,
    LegTimeSource,
    TimeBasis,
    TransportMode,
    TransportNode,
)
from ...utils import parse_dt, utcnow
from ...web_journey import JourneyError
from ...web_platform import WebAPIError, WebPrincipal, require_csrf, require_idempotency_key, require_principal
from ...web_providers.basemap import ATTRIBUTION as BASEMAP_ATTRIBUTION
from ...web_providers.readiness import amap_ready, google_state, image_ready
from ...web_household import Action
from ._shared import cap, idempotent, redraw, require_pet, web_of, web_router

router = web_router("journey")

CODES = {
    "insufficient_funds": (WebErrorCode.insufficient_funds, 409),
    "already_traveling": (WebErrorCode.already_traveling, 409),
    "version_conflict": (WebErrorCode.version_conflict, 409),
    "not_found": (WebErrorCode.not_found, 404),
    "unknown_destination": (WebErrorCode.not_found, 404),
    "stale_recommendation": (WebErrorCode.itinerary_changed, 409),
    "no_license": (WebErrorCode.forbidden, 403),
    "pet_asleep": (WebErrorCode.conflict, 409),
}


def capabilities(settings) -> list[Capability]:
    return [
        cap("journey.map", "journey", CapabilityStatus.available if settings.web_demo_catalog or amap_ready(settings) else CapabilityStatus.not_configured,
            "演示环境：演示线路，按真实经过时间推进" if settings.web_demo_catalog else
            "真实交通：港澳一日行（官网船期 + 高德接驳，从开船时间反推出门）与家附近的活动；按真实经过时间推进；GET /journey/plan 先看计划"),
        cap("journey.visit", "journey", CapabilityStatus.available,
            "目的地为真实地点（高德，带来源与取回时间），店内为原创场景" if amap_ready(settings) else
            ("示例咖啡馆模板（演示环境）；店内为原创场景" if settings.web_demo_catalog else "地图不可用：附近活动去星球内的地方（明确标注），远行不成立")),
        cap("adventure.events", "adventure", CapabilityStatus.available, "三个事件模板（咖啡馆小侦探/海上小水手/小小飞行员），规则结算绑定勋章"),
        cap("pet.travel_guide", "journey", CapabilityStatus.available,
            "进城或出远门时 TA 写一日小攻略；站点用高德核对（海外待 Google），开启生成照片时附写实手账图" if amap_ready(settings) else "进城或出远门时 TA 写一日小攻略；地图未配置时站点标“未核实”"),
        cap("pet.autonomy", "journey", CapabilityStatus.available,
            "TA 自己决定出不出门、去哪（白天，按 DNA 的节奏与银行卡余额）；主人的建议会被认真考虑；可打工赚钱"),
        cap("adventure.hero_image", "adventure", CapabilityStatus.available if image_ready(settings) else CapabilityStatus.not_configured,
            "主人在设置里开启后，冒险事件由生图服务（火山方舟 Seedream）画一张插画" if image_ready(settings) else "生图供应商未配置；以文字故事与原创徽章呈现"),
        cap("map.amap", "map", CapabilityStatus.available if amap_ready(settings) else CapabilityStatus.not_configured,
            "服务端真实地点（港澳咖啡店）与步行/驾车估时" if amap_ready(settings) else "高德 key 未配置"),
        cap("map.basemap", "map", CapabilityStatus.available if amap_ready(settings) else CapabilityStatus.not_configured,
            "港澳范围的旅途地图使用高德静态底图（服务端代理，缓存 24 小时）；其他地区仍为示意地图" if amap_ready(settings) else "未配置地图供应商；旅途地图为示意图"),
        cap("map.google", "map", CapabilityStatus.available if google_state(settings)[0] else CapabilityStatus.not_configured, google_state(settings)[1]),
        cap("map.street_rank_list", "map", CapabilityStatus.disabled, "高德扫街榜接口尚未确认"),
    ]


def translate(exc: JourneyError) -> WebAPIError:
    code, status = CODES.get(exc.reason, (WebErrorCode.conflict, 409))
    return WebAPIError(code, exc.message, status, details={"reason": exc.reason, **exc.details})


@router.get("/map/basemap", response_model=BasemapView)
def basemap(request: Request,
            south: float = Query(ge=-85, le=85), west: float = Query(ge=-180, le=180),
            north: float = Query(ge=-85, le=85), east: float = Query(ge=-180, le=180),
            width: int = Query(ge=64, le=4096, description="容器宽度（CSS 像素）"), height: int = Query(ge=64, le=4096, description="容器高度（CSS 像素）"),
            principal: WebPrincipal = Depends(require_principal)) -> BasemapView:
    """旅途地图的真实底图。只在高德服务区提供；不可用时返回 available=false 和原因，由前端退回示意地图，不当作错误。"""
    if south > north or west > east:
        raise WebAPIError(WebErrorCode.validation_failed, "地图范围不正确。", 422, details={"reason": "invalid_bounds"})
    service = web_of(request).providers.basemap
    if service is None:
        return BasemapView(available=False, reason=BasemapUnavailableReason.not_configured)
    result = service.view(principal.user_id, south, west, north, east, width, height)
    if not result.available or result.plan is None:
        return BasemapView(available=False, reason=BasemapUnavailableReason(result.reason or "upstream_error"))
    plan = result.plan
    lat, lng = plan.center
    return BasemapView(available=True, provider=BasemapProvider.amap, image_url=f"/api/v1/web/media/basemaps/{plan.basemap_id}",
                       center=LatLng(lat=lat, lng=lng), zoom=plan.zoom, width=plan.width, height=plan.height,
                       attribution=BASEMAP_ATTRIBUTION, expires_at=result.expires_at)


@router.get("/media/basemaps/{basemap_id}")
def basemap_image(basemap_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> FileResponse:
    """底图图片：原样返回（含供应商标志与审图号）。登录用户可读，不含任何个人数据。"""
    service = web_of(request).providers.basemap
    found = service.file_for(basemap_id) if service is not None else None
    if found is None:
        raise WebAPIError.not_found("这张底图")
    path, content_type = found
    return FileResponse(path, media_type=content_type, headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})


@router.get("/journey/destinations", response_model=list[DestinationOption])
def destinations(request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> list[DestinationOption]:
    home = require_pet(request, principal, pet_id, activated=True)
    return web_of(request).journeys.destinations(principal.user_id, home.pet_id, home.home_id)


@router.post("/journey/suggest", response_model=JourneySuggestion, dependencies=[Depends(require_csrf)])
def suggest(body: SuggestRequest, request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> JourneySuggestion:
    """家人给 TA 的出门建议：TA 会认真考虑（建议的地方更可能去），但由 TA 自己决定去不去、什么时候去。"""
    web = web_of(request)
    home = require_pet(request, principal, pet_id, activated=True, action=Action.care)
    now = utcnow()
    made = web.life.suggest(principal.user_id, home.pet_id, home.home_id, body.destination_key, now)
    if made is None:
        raise WebAPIError.not_found("这个地方")
    note = f"好呀，我会想想要不要去{made['title']}～" if made["affordable"] else f"{made['title']}听起来不错，等我攒够钱再去～"
    web.communicator.post_pet_note(principal.user_id, home.pet_id, note, dedupe_key=f"suggest:{made['suggestion_id']}", now=now)
    return JourneySuggestion.model_validate({k: v for k, v in made.items() if k != "affordable"})


@router.get("/guides", response_model=list[TravelGuide])
def guides(request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> list[TravelGuide]:
    """TA 的攻略手账（最近在前；全家同一份）。站点 verified=true 的有真实地址，家人可以照着走。"""
    home = require_pet(request, principal, pet_id, activated=True)
    return [TravelGuide.model_validate(g) for g in web_of(request).guides.list(principal.user_id, home.pet_id)]


@router.post("/guides/{pet_id}/{guide_id}/retry-image", response_model=list[TravelGuide], dependencies=[Depends(require_csrf)])
def retry_guide_image(pet_id: str, guide_id: str, request: Request,
                      principal: WebPrincipal = Depends(require_principal)) -> list[TravelGuide]:
    """手账图没画成（或结果没确认）时由家人重画：重新排队，不重复写攻略（CR-A10）。

    和通讯器的 `retry-photo` 同构：路由这层看家庭成员与 care 权限，服务那层看归属与展示状态。
    连点两次的第二次拿不到任务号，不会再发起一次付费尝试。
    """
    require_pet(request, principal, pet_id, activated=True, action=Action.care)
    web = web_of(request)
    redraw(web, web.guides.image_retrying(pet_id, guide_id), web.guides.image_state_for(pet_id, guide_id), "可以重画的手账图")
    return [TravelGuide.model_validate(g) for g in web.guides.list(principal.user_id, pet_id)]


@router.get("/guides/{guide_id}", response_model=TravelGuide)
def guide(guide_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> TravelGuide:
    web = web_of(request)
    found = web.guides.get(principal.user_id, guide_id)
    journey = web.journeys.repo.get(found["journey_id"]) if found else None
    if found is None or journey is None or not web.pets.is_member(principal.user_id, journey.pet_id):
        raise WebAPIError.not_found("这份攻略")
    return TravelGuide.model_validate(found)


@router.get("/journey/plan", response_model=TripPlanPreview)
def journey_plan(destination_key: str, request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> TripPlanPreview:
    """出发前看一眼这趟会怎么走（真实交通：从开船时间反推出门；每段带来源、参考班次与现实参考票价）。
    不扣钱、不生成行程、不分配动物世界编号；现实资料拿不到时 409 transport_unavailable（不会退回演示线路）。"""
    web = web_of(request)
    home = require_pet(request, principal, pet_id, activated=True)
    try:
        resolved, timeline, references = web.journeys.preview(home.pet_id, home.home_id, destination_key)
    except JourneyError as exc:
        raise translate(exc) from exc
    return plan_preview(web, resolved, timeline, references)


BASIS_OF = {"verified_timetable": "verified_timetable", "operator_rule": "verified_timetable", "routed_estimate": "routed_estimate", "world_rule": "routed_estimate"}
NODE_KEYS = ("node_id", "name", "kind", "timezone", "lat", "lng", "verified")


def plan_preview(web, resolved, timeline, references) -> TripPlanPreview:
    dest = resolved.final
    legs = []
    for planned, ref in zip(timeline.legs, references):
        plan = planned.plan
        kind = ref.get("kind")
        fare = ref.get("fare")
        reference_fare = None
        if fare:
            reference_fare = ReferenceFare(currency=fare["currency"], amount=fare["amount"], fare_class=fare["class"], band=fare["band"],
                                           effective_from=fare["effective_from"], note=fare["holiday_note"] + "；现实票价，与星币旅费无关",
                                           source_url=fare["source_url"])
        legs.append(PlannedLegPreview(
            sequence=planned.sequence, direction=planned.direction, kind=LegKind(plan.kind), mode=TransportMode(plan.mode),
            origin=TransportNode(**{k: plan.origin.get(k) for k in NODE_KEYS}), destination=TransportNode(**{k: plan.destination.get(k) for k in NODE_KEYS}),
            departs_at=planned.starts_at, arrives_at=planned.ends_at, time_basis=TimeBasis(BASIS_OF.get(kind, "demo_fixture")),
            time_source=LegTimeSource(kind) if kind in LegTimeSource._value2member_map_ else None, source_label=ref.get("source_label") or "",
            reference_id=ref.get("reference_id"), world_carrier=plan.carrier, reference_fare=reference_fare,
        ))
    place = web.journeys.visit_place(dest, resolved.real_place, resolved.basis, utcnow())
    venue = Place(provider=PlaceProvider(place["provider"]), place_id=place["place_id"], name=place["name"], address=place.get("address"),
                  lat=place["lat"], lng=place["lng"], coord_system=CoordSystem(place["coord_system"]), category=place.get("category"),
                  source_updated_at=parse_dt(place["source_updated_at"]) if place.get("source_updated_at") else None,
                  attribution=place.get("attribution"), data_origin=DataOrigin.fixture if place["provider"] == "fixture" else DataOrigin.live)
    notes = ["这是计划，不是已经发生的事；TA 自己决定去不去、什么时候去（家人可以提建议）。"]
    if resolved.trip is not None:
        notes.append("船班来自运营方官网的已核验船期（现实参考，不是订票）；打车时间是地图的一般路况估算。")
        notes.append("星币旅费是星球上的开销，现实票价只是参考，两者没有换算关系。")
    leave = timeline.legs[0].starts_at if timeline.legs else utcnow()
    return TripPlanPreview(destination_key=dest.key, title=dest.title, city=dest.city, fee=dest.fee, leave_home_at=leave, returns_home_at=timeline.completes_at,
                           stay_minutes=dest.venue.stay_minutes, venue=venue, legs=legs, notes=notes,
                           data_origin=DataOrigin.fixture if resolved.basis == "demo_fixture" else DataOrigin.live)


@router.get("/journey/suggestions", response_model=list[JourneySuggestion])
def suggestions(request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> list[JourneySuggestion]:
    """你给 TA 的建议（每位家人各自的建议各自看；TA 考虑时会把全家的建议都算上）。"""
    home = require_pet(request, principal, pet_id, activated=True)
    return [JourneySuggestion.model_validate(s) for s in web_of(request).life.recent_suggestions(principal.user_id, home.pet_id)]


@router.post("/journey/depart", response_model=JourneyMapSnapshot, dependencies=[Depends(require_csrf)])
def depart(body: DepartRequest, request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal),
           idempotency_key: str = Depends(require_idempotency_key)) -> JourneyMapSnapshot:
    """替 TA 出发（旅费从 TA 自己的星球账户扣）：需要“可花费”权限。"""
    web = web_of(request)
    home = require_pet(request, principal, pet_id, activated=True, action=Action.spend)

    def handler() -> JourneyMapSnapshot:
        try:
            journey = web.journeys.depart(principal.user_id, home.pet_id, home.home_id, body.destination_key, operation_key=idempotency_key)
        except JourneyError as exc:
            raise translate(exc) from exc
        return web.snapshots.map_snapshot(journey, web.journeys.repo.legs(journey.journey_id), web.journeys.repo.visit_for_journey(journey.journey_id))

    return idempotent(request, principal, "journey.depart", idempotency_key, {**body.model_dump(), "pet_id": home.pet_id}, JourneyMapSnapshot, handler)


@router.get("/journey/map", response_model=JourneyMapSnapshot)
def journey_map(request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> JourneyMapSnapshot:
    """当前旅程；在家时返回最近一次旅程（lifecycle=completed）；从未出发返回 404。"""
    web = web_of(request)
    home = require_pet(request, principal, pet_id, activated=True)
    # 只读：不补齐到期事件（结算由任务进程或命令完成）；还没结算到的部分用 catching_up 标出来
    journey = web.journeys.repo.active_for_pet(home.pet_id) or web.journeys.repo.latest_for_pet(home.pet_id)
    if journey is None:
        raise WebAPIError(WebErrorCode.not_found, "TA 还没出过门。", 404, details={"reason": "no_journey"})
    snapshot = web.snapshots.map_snapshot(journey, web.journeys.repo.legs(journey.journey_id), web.journeys.repo.visit_for_journey(journey.journey_id))
    return snapshot.model_copy(update={"catching_up": web.journeys.catching_up(home.pet_id)})


@router.get("/visits/{visit_id}", response_model=Visit)
def get_visit(visit_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> Visit:
    web = web_of(request)
    try:
        visit, journey = web.journeys.visit_for_user(principal.user_id, visit_id, settle=False)
    except JourneyError as exc:
        raise translate(exc) from exc
    return web.snapshots.visit_dto(visit, web.journeys.visit_state(visit, journey, utcnow()))


@router.post("/visits/{visit_id}/actions", response_model=Visit, dependencies=[Depends(require_csrf)])
def visit_action(visit_id: str, body: VisitActionRequest, request: Request, principal: WebPrincipal = Depends(require_principal),
                 idempotency_key: str = Depends(require_idempotency_key)) -> Visit:
    web = web_of(request)

    def handler() -> Visit:
        try:
            visit = web.journeys.act(principal.user_id, visit_id, body.activity_id)
            journey = web.journeys.repo.get(visit.journey_id)
        except JourneyError as exc:
            raise translate(exc) from exc
        return web.snapshots.visit_dto(visit, web.journeys.visit_state(visit, journey, utcnow()))

    return idempotent(request, principal, f"visit.action:{visit_id}", idempotency_key, body.model_dump(), Visit, handler)


@router.post("/visits/{visit_id}/choice", response_model=JourneyMapSnapshot, dependencies=[Depends(require_csrf)])
def visit_choice(visit_id: str, body: VisitChoiceRequest, request: Request, principal: WebPrincipal = Depends(require_principal),
                 idempotency_key: str = Depends(require_idempotency_key)) -> JourneyMapSnapshot:
    """到店前改去寻味推荐的分店：行程版本 +1，旧推荐待复核。推荐 ID 本身不产生到访。"""
    web = web_of(request)

    def handler() -> JourneyMapSnapshot:
        try:
            journey = web.journeys.choose_recommendation(principal.user_id, visit_id, body.recommendation_id, body.expected_itinerary_version)
        except JourneyError as exc:
            raise translate(exc) from exc
        return web.snapshots.map_snapshot(journey, web.journeys.repo.legs(journey.journey_id), web.journeys.repo.visit_for_journey(journey.journey_id))

    return idempotent(request, principal, f"visit.choice:{visit_id}", idempotency_key, body.model_dump(), JourneyMapSnapshot, handler)
