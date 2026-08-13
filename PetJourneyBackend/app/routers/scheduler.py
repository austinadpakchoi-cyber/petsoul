"""后台调度器端点。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_scheduler
from ..schemas import SchedulerConfig, SchedulerTickResult

router = APIRouter()


@router.get("/api/v1/scheduler/config", response_model=SchedulerConfig)
def scheduler_config(scheduler=Depends(get_scheduler)) -> SchedulerConfig:
    return scheduler.config()


@router.post("/api/v1/scheduler/tick", response_model=SchedulerTickResult)
def scheduler_tick(scheduler=Depends(get_scheduler)) -> SchedulerTickResult:
    return scheduler.tick()
