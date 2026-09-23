"""平行交通：交通段详情。主界面是 /journey 地图；这里不提供舱室/独立交通场景路由。"""

from __future__ import annotations

from fastapi import Depends, Request

from ...schemas.web.common import Capability, CapabilityStatus
from ...schemas.web.transport import JourneyLeg
from ...utils import utcnow
from ...web_transport.timetable import load_timetable
from ...web_platform import WebAPIError, WebPrincipal, require_principal
from ...web_providers.readiness import amap_ready
from ._shared import cap, web_of, web_router

router = web_router("transport")


def capabilities(settings) -> list[Capability]:
    table = load_timetable("turbojet_hk_macau_outer")
    fresh = table.fresh(utcnow().date())
    return [
        cap("transport.legs", "transport", CapabilityStatus.available, "门到门分段；动物世界承运编号按参考班次稳定映射，可追溯"),
        cap("transport.verified_timetable", "transport", CapabilityStatus.available if fresh else CapabilityStatus.not_configured,
            f"{table.operator} 上环 ⇄ 澳门外港：官网船期 {table.effective_from.isoformat()} 起生效，{table.source['fetched_at'][:10]} 抓取核验，"
            f"{table.recheck_by.isoformat()} 前复核" + ("" if fresh else "（已过复核期限：需要重新核对官网，期间不再作为已核验班次使用）")),
        cap("transport.live_status", "transport", CapabilityStatus.disabled, "实时动态不在首版"),
        cap("transport.routed_estimate", "transport", CapabilityStatus.available if amap_ready(settings) else CapabilityStatus.not_configured,
            "去码头、澳门城内与附近活动按高德路线估时（一般路况，记录取回时间与有效期）" if amap_ready(settings) else "道路预计车程需地图供应商密钥；没有时远行不成立"),
    ]


@router.get("/journey/legs/{leg_id}", response_model=JourneyLeg)
def journey_leg(leg_id: str, request: Request, principal: WebPrincipal = Depends(require_principal)) -> JourneyLeg:
    web = web_of(request)
    leg = web.journeys.repo.leg(leg_id)
    journey = web.journeys.repo.get(leg.journey_id) if leg else None
    if leg is None or journey is None or not web.pets.is_member(principal.user_id, journey.pet_id):  # 这只宠物的家人才能看
        raise WebAPIError.not_found("这段交通")
    return web.snapshots.leg_dto(leg, journey.itinerary_version, utcnow())
