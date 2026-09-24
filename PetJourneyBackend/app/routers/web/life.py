"""TA 的生活：打工记录与生活时间线（只读汇总已经发生的记录）。?pet_id= 指明是哪只（只照顾一只时可省略）；全家看到同一份。"""

from __future__ import annotations

from fastapi import Depends, Request

from ...schemas.web.common import Capability, CapabilityStatus
from ...schemas.web.journey import JobRecord, TimelineItem
from ...utils import utcnow
from ...web_agent.timeline import job_records, timeline
from ...web_journey.local import JOBS
from ...web_platform import WebPrincipal, require_principal
from ._shared import cap, require_pet, web_router

router = web_router("life")


def capabilities(settings) -> list[Capability]:
    return [
        cap("life.jobs", "life", CapabilityStatus.available, "打工：岗位、地点、开始与结束时间、状态；干完活工钱按旅程只入账一次"),
        cap("life.timeline", "life", CapabilityStatus.available, "生活时间线：旅行、打工、证件、纪念章、驾考、朋友、明信片与收藏"),
    ]


@router.get("/jobs", response_model=list[JobRecord])
def jobs(request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> list[JobRecord]:
    home = require_pet(request, principal, pet_id, activated=True)
    return [JobRecord.model_validate(j) for j in job_records(request.app.state.storage, principal.user_id, home.pet_id, utcnow(), JOBS)]


@router.get("/timeline", response_model=list[TimelineItem])
def life_timeline(request: Request, pet_id: str | None = None, principal: WebPrincipal = Depends(require_principal)) -> list[TimelineItem]:
    home = require_pet(request, principal, pet_id, activated=True)
    return [TimelineItem.model_validate(i) for i in timeline(request.app.state.storage, principal.user_id, home.pet_id)]
