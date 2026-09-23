"""旅途 / 地点 / 到访契约。一次到访贯穿地图、店内、通讯、照片与动态。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from .common import CoordSystem, DataOrigin, WebModel
from .social import PhotoStatus
from .transport import LegKind, LegTimeSource, TimeBasis, TransportMode, TransportNode


class PlaceProvider(str, Enum):
    amap = "amap"
    google = "google"
    fixture = "fixture"
    world = "world"  # 0.4.0：星球内的地方（世界规则设定，不对应现实地址或商家）


class Place(WebModel):
    """事实字段可缺省，不编造。place_id 带来源命名空间。"""

    provider: PlaceProvider
    place_id: str
    name: str
    address: str | None = None
    lat: float
    lng: float
    coord_system: CoordSystem
    category: str | None = None
    source_updated_at: datetime | None = None
    attribution: str | None = None
    data_origin: DataOrigin


class VisitState(str, Enum):
    planned = "planned"
    travelling = "travelling"
    arrived = "arrived"
    active = "active"
    completed = "completed"
    cancelled = "cancelled"


class VenueTemplate(str, Enum):
    cafe = "cafe"
    restaurant = "restaurant"
    park = "park"
    generic = "generic"


class VisitActivityKind(str, Enum):
    choose_seat = "choose_seat"
    order_drink = "order_drink"
    take_photo = "take_photo"
    greet_resident = "greet_resident"


class VisitActivityState(str, Enum):
    available = "available"
    in_progress = "in_progress"
    done = "done"
    disabled = "disabled"


class VisitActivity(WebModel):
    activity_id: str
    kind: VisitActivityKind
    label: str
    state: VisitActivityState
    result_text: str | None = None


class Visit(WebModel):
    """visit_id 由 Journey 服务在确认下一站时创建；推荐 ID 不等于 visit_id。"""

    visit_id: str
    journey_id: str
    pet_id: str
    place: Place
    state: VisitState
    template: VenueTemplate
    planned_arrival_utc: datetime | None = None
    arrived_at: datetime | None = None
    leaving_at: datetime | None = None
    recommendation_id: str | None = None
    activities: list[VisitActivity] = Field(default_factory=list)
    interior_is_original: bool = Field(
        default=True, description="店内为原创动物世界场景，不代表真实商家内饰"
    )
    data_origin: DataOrigin


class VisitActionRequest(WebModel):
    """需 Idempotency-Key。"""

    activity_id: str


class JourneyLifecycle(str, Enum):
    active = "active"
    completed = "completed"
    cancelled = "cancelled"


class DestinationOption(WebModel):
    """出发站选项。time_basis 标明时长依据；demo_fixture 表示演示线路（未接入真实路线/时刻表）。"""

    destination_key: str
    title: str
    city: str
    summary: str
    fee: int = Field(description="旅费（travel_coin），出发时从统一账本扣除")
    total_minutes: int = Field(description="门到门往返总时长（真实经过时间，不压缩）")
    modes: list[str] = Field(default_factory=list)
    time_basis: str
    wish_match: str | None = Field(default=None, description="与主人确认过的愿望对应时的说明")
    affordable: bool
    available: bool = Field(default=True, description="现在能不能去（现实资料拿不到时为 false，见 unavailable_reason）", json_schema_extra={"x-additive": True})
    unavailable_reason: str | None = Field(default=None, json_schema_extra={"x-additive": True})
    reference_note: str | None = Field(default=None, description="现实参考资料的来源说明（例如运营方船期与参考票价）；星币旅费与现实票价无关",
                                       json_schema_extra={"x-additive": True})


class ReferenceFare(WebModel):
    """现实参考票价（运营方公布，含来源）；与星币旅费无关，TA 在星球上的出行只花星币。"""

    currency: str
    amount: int
    fare_class: str
    band: str = Field(description="day_weekday / day_weekend_holiday / night")
    effective_from: str
    note: str
    source_url: str


class PlannedLegPreview(WebModel):
    sequence: int
    direction: str = Field(description="outbound / return")
    kind: LegKind
    mode: TransportMode
    origin: TransportNode
    destination: TransportNode
    departs_at: datetime
    arrives_at: datetime
    time_basis: TimeBasis
    time_source: LegTimeSource | None = None
    source_label: str
    reference_id: str | None = Field(default=None, description="现实参考班次编号（已核验船期按服务日期落地）")
    world_carrier: str | None = Field(default=None, description="动物世界承运人（出发时按参考班次分配稳定编号）")
    reference_fare: ReferenceFare | None = None


class TripPlanPreview(WebModel):
    """出发前看一眼真实行程（0.4.0）：不扣钱、不生成行程、不分配编号；出门时间从开船时间反推。计划不是已发生的事。"""

    destination_key: str
    title: str
    city: str
    fee: int = Field(description="星币旅费（世界内经济）")
    leave_home_at: datetime
    returns_home_at: datetime
    stay_minutes: int
    venue: Place
    legs: list[PlannedLegPreview]
    notes: list[str] = Field(default_factory=list)
    data_origin: DataOrigin


class DepartRequest(WebModel):
    """需 Idempotency-Key；宠物必须在家、已入住，旅费足够。"""

    destination_key: str


class SuggestionStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    passed = "passed"
    replaced = "replaced"


class SuggestRequest(WebModel):
    """主人给 TA 的出门建议（出发站上选一个地方）。TA 会认真考虑，但由 TA 自己决定去不去、什么时候去。"""

    destination_key: str


class JourneySuggestion(WebModel):
    suggestion_id: str
    destination_key: str
    title: str
    status: SuggestionStatus = Field(description="pending＝TA 还在考虑（出门一次没选它不算结束，24 小时内仍算数）；"
                                                 "accepted＝TA 听了你的去了；passed＝考虑时间过了 TA 没去；replaced＝你改了建议")
    considered_at: datetime | None = Field(default=None, description="TA 最近一次出门时把这条建议一起想过的时刻（x-additive）")
    created_at: datetime
    decided_at: datetime | None = None


class TravelGuideStop(WebModel):
    name: str = Field(description="核对到的真实名称；未核实时是 TA 写的名字")
    label: str | None = Field(default=None, description="TA 在攻略里写的叫法（手账图上用它）")
    time: str | None = Field(default=None, description="大概时段，例如“上午”")
    why: str | None = Field(default=None, description="为什么适合 TA")
    tip: str | None = Field(default=None, description="给主人的实用提示；不确定的写“以现场为准”")
    verified: bool = Field(description="是否用地图核对到了真实地点；未核实的不给地址")
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    attribution: str | None = Field(default=None, description="地点资料来源，或“TA 听说的，未核实”")
    nav_url: str | None = Field(default=None, description="核实过的地点：打开地图导航（高德，WGS-84 坐标）", json_schema_extra={"x-additive": True})
    copy_text: str | None = Field(default=None, description="可复制的现实资料：名称与地址", json_schema_extra={"x-additive": True})


class GuideStatus(str, Enum):
    planned = "planned"
    in_progress = "in_progress"
    completed = "completed"


class TravelGuide(WebModel):
    """TA 的攻略手账：出门前写的一日小攻略，主人也能照着走。"""

    guide_id: str
    journey_id: str
    city: str
    destination_title: str
    title: str
    summary: str | None = None
    stops: list[TravelGuideStop] = Field(default_factory=list)
    owner_tips: list[str] = Field(default_factory=list)
    composed_by: str = Field(description="model＝TA 用自己的话写的（模型）；template＝模板")
    image_status: PhotoStatus | None = Field(default=None, description="写实手账图生成状态；没有开启“生成照片”时为空")
    image_url: str | None = None
    created_at: datetime
    status: GuideStatus | None = Field(default=None, description="这是 TA 的计划：planned 还没出发，in_progress 正在路上，completed 已经回来", json_schema_extra={"x-additive": True})
    visited: list[str] = Field(default_factory=list, description="实际到过的站点（已经发生的经历，与计划分开）", json_schema_extra={"x-additive": True})
    coin_budget: int | None = Field(default=None, description="这趟花的星币（游戏内，从 TA 的银行卡出）", json_schema_extra={"x-additive": True})
    real_budget_note: str | None = Field(default=None, description="现实出行的花费说明（不用星币换算）", json_schema_extra={"x-additive": True})
    copy_text: str | None = Field(default=None, description="整份攻略的纯文本（只含核实过的站点与地址、家人叮嘱与现实花费说明），可以直接复制给家人照着走",
                                  json_schema_extra={"x-additive": True})


class JobRecord(WebModel):
    """TA 的一份工作：岗位、地点、开始与结束时间、状态和工资（完成后才入账，按旅程只入一次）。"""

    journey_id: str
    job_key: str
    title: str
    place: str | None = None
    starts_at: datetime
    ends_at: datetime
    status: str = Field(description="going 去上班的路上 / working 在干活 / done 干完了")
    pay: int
    paid: bool = Field(description="工资是否已经进了银行卡")


class TimelineItem(WebModel):
    """生活时间线：旅行、打工、证件、驾考、朋友、明信片……都来自已经发生的记录。"""

    at: datetime
    kind: str
    title: str
    detail: str | None = None
    ref_id: str | None = None


class VisitChoiceRequest(WebModel):
    """到店前改选寻味推荐的分店：行程版本 +1，旧推荐待复核。需 Idempotency-Key。"""

    recommendation_id: str
    expected_itinerary_version: int


__all__ = [
    "SuggestionStatus",
    "SuggestRequest",
    "JourneySuggestion",
    "TravelGuideStop",
    "GuideStatus",
    "TravelGuide",
    "JobRecord",
    "TimelineItem",
    "PlaceProvider",
    "Place",
    "VisitState",
    "VenueTemplate",
    "VisitActivityKind",
    "VisitActivityState",
    "VisitActivity",
    "Visit",
    "VisitActionRequest",
    "JourneyLifecycle",
    "DestinationOption",
    "ReferenceFare",
    "PlannedLegPreview",
    "TripPlanPreview",
    "DepartRequest",
    "VisitChoiceRequest",
]
