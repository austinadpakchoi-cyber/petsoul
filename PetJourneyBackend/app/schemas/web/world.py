"""统一世界状态（CR-6C2B-MAP W1）：TA 和家里其他宠物此刻在哪、在做什么、还要多久。

**纯读契约**。三条硬规则写在类型里，不靠调用方自觉：

  · **计划 ≠ 正在做**：`phase` 和 `kind` 是两件事——去打工的路上是 `kind=job, phase=going`，
    **到了才是 `there`**。没有「正在打工」这个 kind＋phase 的捷径。
  · **坐标必须说明来路**：`position.basis` 强制回答「这个点是怎么算出来的」——
    家的片区中心、某个地点、路线上的插值，还是不知道。**没有无出处的坐标。**
  · **家的位置只给家里人**：`home` 对非家庭成员为 `None`，而 `precision_m` 如实反映模糊半径
    （家在入住时就落在片区中心附近约 900 米内，不对应门牌）。

`doing` 用现有的 moment 文字；**没有就是 None，不编**。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from .common import LatLng, WebModel

__all__ = [
    "WorldRelation", "WorldActivityKind", "WorldPhase", "WorldPositionBasis", "WorldPose",
    "WorldHome", "WorldJob", "WorldPlace", "WorldLeg", "WorldPosition",
    "WorldActivity", "WorldPetState", "WorldState",
]


class WorldRelation(str, Enum):
    mine = "mine"            # 请求者自己的宠物
    household = "household"  # 同一个家里其他成员的宠物


class WorldActivityKind(str, Enum):
    home = "home"
    stroll = "stroll"
    cafe = "cafe"
    city_trip = "city_trip"
    drive_trip = "drive_trip"
    job = "job"
    trip = "trip"  # 兜底：有旅程但归不进上面任何一类


class WorldPhase(str, Enum):
    home = "home"
    going = "going"
    there = "there"
    returning = "returning"
    unknown = "unknown"  # 有旅程但时间线读不出阶段；**不猜成 home**


class WorldPositionBasis(str, Enum):
    """这个坐标是怎么来的。**每个 position 都必须说**。"""

    home_area = "home_area"  # 家所在片区的模糊中心
    place = "place"          # 某个具体地点（店、打工点）的坐标
    route = "route"          # 路线几何上的点
    unknown = "unknown"


class WorldPose(str, Enum):
    """地图上该画成什么样子（6c2b 2026-09-24 请求：表情要对所有宠物通用，前端不从 `doing` 文字里猜）。

    **只给事实能确定的。** 四个与契约 `CharacterPose` 同名的姿态
    （`sleeping`／`eating`／`sunbathing`／`walking`）是为了以后能直接换成 TA 自己的姿态图。

    `eating` 与 `sunbathing` 现在**没有事实来源**，所以本批一次都不会产出——
    它们列在这里是为了前端可以先画好、后端有来源时直接开始给，**不是留着让人去猜**。
    """

    idle = "idle"              # 在家醒着，或作息未知（**未知不算睡着**）
    sleeping = "sleeping"      # 来自作息判定（`journeys.awake_at`），不是推测
    eating = "eating"          # 暂无事实来源
    sunbathing = "sunbathing"  # 暂无事实来源
    walking = "walking"        # 在路上，且这一段是走路
    riding = "riding"          # 在路上，且这一段是车/船/其它交通
    cafe = "cafe"              # 到了，在店里
    working = "working"        # 到了，在打工
    exploring = "exploring"    # 到了，其它（散步到了等）
    unknown = "unknown"        # 有旅程但阶段读不出来


class WorldHome(WebModel):
    """家的模糊中心。**只给家庭成员**；非成员整个字段为 None，不是坐标置零。"""

    center: LatLng
    precision_m: int  # 如实反映模糊半径，不写 0 也不写一个好看的小数
    label: str


class WorldJob(WebModel):
    title: str
    pay: int
    paid: bool  # 工资是否已结算入账（到店才算做、做完才结算）


class WorldPlace(WebModel):
    name: str
    lat: float
    lng: float
    attribution: str | None = None  # 地点资料来源；示意数据时为 None


class WorldLeg(WebModel):
    """只在 going / returning 出现。`route` 用**出发时已缓存**的几何，没有就 `[]`——读时不调地图。"""

    mode: str
    route: list[LatLng] = []
    departs_at: datetime | None = None
    arrives_at: datetime | None = None


class WorldPosition(WebModel):
    lat: float
    lng: float
    basis: WorldPositionBasis
    precision_m: int


class WorldActivity(WebModel):
    kind: WorldActivityKind
    phase: WorldPhase
    pose: WorldPose  # 地图上画成什么样；**只由事实推出，推不出就 idle／unknown**
    title: str
    doing: str | None = None       # 现有 moment 文字；没有就 None，**不编**
    place: WorldPlace | None = None
    since: datetime | None = None  # 这一阶段开始
    until: datetime | None = None  # 预计结束
    job: WorldJob | None = None
    journey_id: str | None = None
    visit_id: str | None = None


class WorldPetState(WebModel):
    pet_id: str
    name: str
    species: str
    avatar_url: str | None = None
    relation: WorldRelation
    home: WorldHome | None = None
    activity: WorldActivity
    leg: WorldLeg | None = None
    position: WorldPosition | None = None
    version: int = 1


class WorldState(WebModel):
    server_time: datetime
    coord_system: str = "wgs84"  # 契约坐标一律 WGS-84；画到高德上由前端换算 GCJ-02
    cache_seconds: int = 15
    pets: list[WorldPetState] = []
