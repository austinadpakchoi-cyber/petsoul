"""平行交通契约：现实参考与动物世界身份分离、门到门 JourneyLeg、地图车辆与活动入口。

时间一律保存完整 UTC；当地展示使用节点时区（IANA）。计划/预计/实际三组时间
分别可缺省——schema 不把实际时间默认为计划时间，也不把估算标成已核验。
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import Field

from .common import DataOrigin, LatLng, WebModel


class TransportMode(str, Enum):
    flight = "flight"
    train = "train"
    ferry = "ferry"
    drive = "drive"
    transit = "transit"
    taxi = "taxi"
    walk = "walk"


class TimeBasis(str, Enum):
    verified_timetable = "verified_timetable"
    live_status = "live_status"
    routed_estimate = "routed_estimate"
    demo_fixture = "demo_fixture"


class LegTimeSource(str, Enum):
    """0.4.0：一段交通时间的精确来源（time_basis 只保留四个大类以兼容旧客户端）。

    verified_timetable 已核验时刻表的班次；operator_rule 运营方规定（例如开船前 30 分钟登船）；routed_estimate 地图供应商的路线估算；
    world_rule 星球内的路程（世界规则估算，不是现实路线；time_basis 记为 routed_estimate＝“估算”）；demo_fixture 演示环境。"""

    verified_timetable = "verified_timetable"
    operator_rule = "operator_rule"
    routed_estimate = "routed_estimate"
    world_rule = "world_rule"
    demo_fixture = "demo_fixture"


class DataFreshness(str, Enum):
    verified = "verified"
    stale = "stale"
    unavailable = "unavailable"


class PositionBasis(str, Enum):
    simulated_route = "simulated_route"
    schematic = "schematic"
    live_vehicle = "live_vehicle"


class TravellerRole(str, Enum):
    driver = "driver"
    passenger = "passenger"
    walker = "walker"


class LegKind(str, Enum):
    main = "main"
    connection = "connection"
    wait = "wait"
    transfer = "transfer"


class LegPhase(str, Enum):
    scheduled = "scheduled"
    connecting = "connecting"
    waiting = "waiting"
    boarding = "boarding"
    in_transit = "in_transit"
    arriving = "arriving"
    arrived = "arrived"
    cancelled = "cancelled"


class NodeKind(str, Enum):
    airport = "airport"
    station = "station"
    port = "port"
    road_point = "road_point"
    place = "place"


class TransportNode(WebModel):
    """verified=False 表示示意节点（例如旧代码插值出的中转点），不得冒充真实枢纽。"""

    node_id: str
    name: str
    kind: NodeKind
    timezone: str = Field(description="IANA 时区，例如 Asia/Hong_Kong")
    lat: float | None = None
    lng: float | None = None
    verified: bool = False


class TransportReference(WebModel):
    """现实参考：仅服务端核验与来源说明使用；主界面展示 WorldService。"""

    reference_id: str
    provider: str
    operating_instance_id: str
    service_date: date
    operator_name: str | None = None
    marketing_codes: list[str] = Field(default_factory=list)
    origin: TransportNode
    destination: TransportNode
    scheduled_departure_utc: datetime | None = None
    scheduled_arrival_utc: datetime | None = None
    estimated_departure_utc: datetime | None = None
    estimated_arrival_utc: datetime | None = None
    actual_departure_utc: datetime | None = None
    actual_arrival_utc: datetime | None = None
    time_basis: TimeBasis
    freshness: DataFreshness
    source_url: str | None = None
    fetched_at: datetime | None = None
    verified_at: datetime | None = None
    usage_scope: str | None = None


class TransportReferenceSummary(WebModel):
    """发给客户端的最小来源说明，不含现实班次号作为主展示。"""

    reference_id: str | None = None
    time_basis: TimeBasis
    freshness: DataFreshness
    source_label: str
    verified_at: datetime | None = None


class WorldService(WebModel):
    """动物世界承运身份：同一运营实例稳定映射（唯一约束 + mapping_version），刷新不换号。"""

    world_service_id: str
    carrier_name: str
    service_code: str
    mode: TransportMode
    vehicle_style: str | None = None
    reference_id: str | None = None
    mapping_version: int = 1


class LegTimes(WebModel):
    origin_timezone: str
    destination_timezone: str
    planned_departure_utc: datetime
    planned_arrival_utc: datetime
    estimated_departure_utc: datetime | None = None
    estimated_arrival_utc: datetime | None = None
    actual_departure_utc: datetime | None = None
    actual_arrival_utc: datetime | None = None


class JourneyLeg(WebModel):
    leg_id: str
    journey_id: str
    sequence: int
    kind: LegKind
    mode: TransportMode
    role: TravellerRole
    world_service: WorldService | None = None
    origin: TransportNode
    destination: TransportNode
    times: LegTimes
    time_basis: TimeBasis
    freshness: DataFreshness
    position_basis: PositionBasis
    phase: LegPhase
    itinerary_version: int
    route: list[LatLng] = Field(default_factory=list, description="有几何才沿线呈现；仅节点时为示意")
    reference: TransportReferenceSummary | None = None
    rescheduled_reason: str | None = None
    time_source: LegTimeSource | None = Field(default=None, description="这段时间的精确来源（见 LegTimeSource）；world_rule 的 time_basis 为 routed_estimate",
                                              json_schema_extra={"x-additive": True})


class VehiclePosition(WebModel):
    """由服务器时间与已确认时间线计算；客户端只做平滑插值呈现，不决定到达。"""

    leg_id: str
    lat: float
    lng: float
    heading_deg: float = 0.0
    progress: float = Field(ge=0.0, le=1.0)
    computed_at: datetime
    position_basis: PositionBasis


class TravelActivityKind(str, Enum):
    listening = "listening"
    watching = "watching"
    resting = "resting"
    window_gazing = "window_gazing"
    dining = "dining"
    writing_postcard = "writing_postcard"


class TravelActivityState(str, Enum):
    active = "active"
    paused = "paused"
    interrupted = "interrupted"
    ended = "ended"


class TravelActivity(WebModel):
    activity_id: str
    leg_id: str
    kind: TravelActivityKind
    state: TravelActivityState
    starts_at: datetime
    ends_at: datetime | None = None
    media_session_id: str | None = None
    interruptible: bool = True
    version: int = 1


class ActivityBadgeKind(str, Enum):
    music = "music"
    tv = "tv"


class MapEntryAction(str, Enum):
    join = "join"
    solo = "solo"
    open_leg_card = "open_leg_card"


class MapActivityEntry(WebModel):
    """地图车辆旁的音符/电视入口；badge 由实际 TravelActivity 决定，无活动则不下发。"""

    entry_id: str
    leg_id: str
    activity_id: str
    badge: ActivityBadgeKind
    badge_state: TravelActivityState
    media_session_id: str | None = None
    label: str
    actions: list[MapEntryAction] = Field(default_factory=list)


class PetArrivalContext(WebModel):
    """Journey → FoodDiscovery 的时间契约：门到门可行到达与可停留窗口，不只看落地时刻。"""

    journey_id: str
    itinerary_version: int
    leg_id: str
    city: str
    destination_timezone: str
    feasible_arrival_utc: datetime
    stay_window_start_utc: datetime
    stay_window_end_utc: datetime


class JourneyMapSnapshot(WebModel):
    journey_id: str
    pet_id: str
    itinerary_version: int
    lifecycle: str = Field(default="active", description="active / completed / cancelled")
    destination_title: str | None = None
    current_visit_id: str | None = Field(default=None, description="宠物此刻在店里时才有值")
    planned_visit_id: str | None = Field(default=None, description="本次旅程的到访（出发即确定；到店前可按寻味推荐改选）")
    server_time: datetime
    legs: list[JourneyLeg] = Field(default_factory=list)
    current_leg_id: str | None = None
    vehicle: VehiclePosition | None = None
    activities: list[TravelActivity] = Field(default_factory=list)
    activity_entries: list[MapActivityEntry] = Field(default_factory=list)
    arrival_context: PetArrivalContext | None = None
    data_origin: DataOrigin
    catching_up: bool = Field(default=False, description="有已经到期、后台还没结算到的事实（到站、收工、回家……）：位置照常按时间显示，工资与来信稍后出现；"
                              "不是出错（0.4.1）", json_schema_extra={"x-additive": True})



class BasemapProvider(str, Enum):
    amap = "amap"


class BasemapUnavailableReason(str, Enum):
    not_configured = "not_configured"
    outside_region = "outside_region"
    daily_cap = "daily_cap"
    user_limit = "user_limit"
    upstream_error = "upstream_error"


class BasemapView(WebModel):
    """旅途地图的真实底图（服务端代理高德静态地图）。available=false 时前端退回示意地图，并说明原因。"""

    available: bool
    reason: BasemapUnavailableReason | None = None
    provider: BasemapProvider | None = None
    image_url: str | None = Field(default=None, description="同源图片地址（需登录），图片为 2 倍清晰度；图上自带供应商标志与审图号，不得遮挡或裁掉")
    center: LatLng | None = Field(default=None, description="图片中心（WGS-84）；叠加物按 WGS-84 做 Web Mercator 投影即可对齐")
    zoom: int | None = Field(default=None, description="Web Mercator 缩放级别（256 像素瓦片）")
    width: int | None = Field(default=None, description="图片逻辑宽度（CSS 像素）")
    height: int | None = Field(default=None, description="图片逻辑高度（CSS 像素）")
    attribution: str | None = None
    expires_at: datetime | None = None

__all__ = [
    "TransportMode",
    "TimeBasis",
    "LegTimeSource",
    "DataFreshness",
    "PositionBasis",
    "TravellerRole",
    "LegKind",
    "LegPhase",
    "NodeKind",
    "TransportNode",
    "TransportReference",
    "TransportReferenceSummary",
    "WorldService",
    "LegTimes",
    "JourneyLeg",
    "VehiclePosition",
    "TravelActivityKind",
    "TravelActivityState",
    "TravelActivity",
    "ActivityBadgeKind",
    "MapEntryAction",
    "MapActivityEntry",
    "PetArrivalContext",
    "JourneyMapSnapshot",
    "BasemapProvider",
    "BasemapUnavailableReason",
    "BasemapView",
]
