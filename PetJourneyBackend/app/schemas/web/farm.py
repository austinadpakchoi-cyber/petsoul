"""农场与串门契约：邻居列表、访客看到的菜园、作物目录。数值是可配置的首发值，不是冻结的经济设计。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from .common import DataOrigin, WebModel
from .home import GuardState, PlotSummary
from .pets import PetPresence, PetSpecies


class CropInfo(WebModel):
    crop_key: str
    label: str
    grow_seconds: int
    yield_units: int
    unit_value: int = Field(description="每单位折算的 travel_coin")
    steal_total: int = Field(description="每一批作物全体访客合计最多可偷的单位数")
    requires_seed: bool = Field(default=False, description="稀有作物：需要旅行带回的种子，种下时消耗一颗")


class FarmWatch(str, Enum):
    """菜园此刻被谁看着：主人巡院（偷不到）/ 宠物在家醒着（多半会被发现）/ 宠物在打盹（可能被发现）/ 没人看着。"""

    owner_patrol = "owner_patrol"
    pet_awake = "pet_awake"
    pet_resting = "pet_resting"
    nobody = "nobody"


class NeighborPetBrief(WebModel):
    pet_id: str
    name: str
    species: PetSpecies
    avatar_url: str | None = None


class NeighborHomeSummary(WebModel):
    home_id: str
    pet: NeighborPetBrief
    presence: PetPresence
    guarded: bool = Field(description="有人看着菜园（主人巡院或宠物在家）；宠物在家时仍可能偷到，只是几率低")
    stealable_plots: int
    watch: FarmWatch | None = Field(default=None, description="谁在看着菜园", json_schema_extra={"x-additive": True})
    data_origin: DataOrigin


class VisitorPlot(WebModel):
    plot: PlotSummary
    taken_by_me: bool = False


class NeighborHomeView(WebModel):
    home_id: str
    pet: NeighborPetBrief
    presence: PetPresence
    guarded: bool
    plots: list[VisitorPlot] = Field(default_factory=list)
    watch: FarmWatch | None = Field(default=None, description="谁在看着菜园", json_schema_extra={"x-additive": True})
    server_time: datetime
    data_origin: DataOrigin


class StealRequest(WebModel):
    """需 Idempotency-Key；同一批作物每位访客最多偷一次，全体合计不超过 steal_total。"""

    home_id: str
    plot_id: str
    cycle_id: str


class StealResult(WebModel):
    """偷到的是物资（进自己的仓库），不是直接的游戏币。"""

    home_id: str
    plot: PlotSummary
    gained_item_key: str
    gained_units: int
    message: str


class PatrolResult(WebModel):
    guard: GuardState
    message: str


__all__ = [
    "CropInfo",
    "FarmWatch",
    "NeighborPetBrief",
    "NeighborHomeSummary",
    "VisitorPlot",
    "NeighborHomeView",
    "StealRequest",
    "StealResult",
    "PatrolResult",
]
