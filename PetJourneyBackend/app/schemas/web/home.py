"""共同的家：HomeSnapshot 权威快照、统一钱包摘要、农场与入住欢迎。

钱包：首发一个家绑定一只主宠物；家园收益经 EconomyAdapter 进入既有
pet_wallets.travel_coin 账本。任何模块只读 WalletSummary，不直接操作表。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from .common import DataOrigin, WebModel
from .pets import PetPresence, PetPrivateSummary
from .household import HouseholdBrief, HouseholdPetBrief


class WalletSummary(WebModel):
    currency: str = Field(default="travel_coin", description="唯一游戏币口径")
    balance: int = 0
    updated_at: datetime | None = None


class GuardBasis(str, Enum):
    pet_at_home = "pet_at_home"
    owner_patrol = "owner_patrol"
    none = "none"


class GuardState(WebModel):
    guarding: bool
    basis: GuardBasis
    until: datetime | None = Field(default=None, description="主人巡院的守护截止时间（basis=owner_patrol 时）")
    next_patrol_at: datetime | None = Field(default=None, description="下一次可以巡院的时间；为空表示现在就可以")
    guarding_pets: list[str] = Field(default_factory=list, description="此刻在家、醒着、在守菜的宠物（多只一起守效果更好，但不是绝对防偷）",
                                     json_schema_extra={"x-additive": True})


class InventoryItem(WebModel):
    """仓库里的可出售物资（收成、串门摘来的菜）。个人纪念与照片不在这里、不可交易。"""

    item_key: str
    label: str
    qty: int
    unit_price: int = Field(description="杂货铺收购价（travel_coin/单位）")
    tradable: bool = True


class PlotStage(str, Enum):
    empty = "empty"
    growing = "growing"
    ripe = "ripe"
    harvested = "harvested"


class PlotSummary(WebModel):
    plot_id: str
    cycle_id: str | None = None
    crop_key: str | None = None
    crop_label: str | None = None
    stage: PlotStage
    ripe_at: datetime | None = None
    steal_total: int | None = Field(default=None, description="本批可偷总额（全体访客共享）")
    steal_remaining: int | None = None


class FarmActionKind(str, Enum):
    plant = "plant"
    harvest = "harvest"
    steal = "steal"


class FarmActionRequest(WebModel):
    """需 Idempotency-Key 请求头；同键同请求返回原结果。"""

    home_id: str
    plot_id: str
    cycle_id: str | None = None
    action: FarmActionKind
    crop_key: str | None = None


class FarmActionResult(WebModel):
    plot: PlotSummary
    wallet: WalletSummary
    gained_items: list[str] = Field(default_factory=list)


class WelcomeDetailKind(str, Enum):
    """当前 capability 支持兑现的欢迎细节；没有的动作动画不在此列。"""

    owner_title = "owner_title"
    favorite_object = "favorite_object"
    interaction_boundary = "interaction_boundary"


class WelcomeDetail(WebModel):
    kind: WelcomeDetailKind
    text: str
    note_id: str
    note_version: int


class HomeWelcome(WebModel):
    """只由 MemoryProjection(home_interaction) 生成；未确认/owner_private 候选不会出现。"""

    pet_id: str
    confirmation_id: str | None = None
    projection_version: int
    greeting: str
    details: list[WelcomeDetail] = Field(default_factory=list)


class UnreadSignals(WebModel):
    messages: int = 0
    circle: int = 0


class JourneyBrief(WebModel):
    journey_id: str
    itinerary_version: int
    headline: str
    current_visit_id: str | None = None
    current_leg_id: str | None = None


class HabitatKind(str, Enum):
    """主人希望 TA 住在哪一类地方（家是一个概念，落在某座城市的一个片区）。"""

    seaside = "seaside"
    grassland = "grassland"
    desert = "desert"
    forest = "forest"
    lakeside = "lakeside"
    mountain = "mountain"
    city = "city"
    countryside = "countryside"


class HomePlaceSummary(WebModel):
    habitat: HabitatKind
    habitat_label: str = Field(description="海边/草原/……")
    city: str
    area_label: str = Field(description="片区的说法，例如“环岛路附近的海边”；不是具体地址")
    display: str = Field(description="展示用：城市·片区")
    timezone: str
    chosen: bool = Field(description="主人是否选过；没选过时为默认（香港·中环）")


class HabitatOption(WebModel):
    habitat: HabitatKind
    label: str
    examples: list[str] = Field(default_factory=list, description="可能随机到的城市，例如“厦门、青岛”")
    open: bool = Field(default=True, description="新家现在能不能选这一类（只开放真实交通与地点都已接通的片区；已有的家不受影响）",
                       json_schema_extra={"x-additive": True})


class HomePlaceView(WebModel):
    place: HomePlaceSummary
    options: list[HabitatOption] = Field(default_factory=list)
    can_change: bool = Field(description="TA 在外面时不能搬家")


class HomePlaceRequest(WebModel):
    """选一类地方；服务端在对应片区里随机一个，坐标已模糊处理。重复提交会重新随机。"""

    habitat: HabitatKind


class HomeSnapshot(WebModel):
    home_id: str
    server_time: datetime
    version: int = Field(description="快照版本，写操作后递增；客户端据此失效缓存")
    pet: PetPrivateSummary
    presence: PetPresence
    guard: GuardState
    wallet: WalletSummary
    pantry: list[InventoryItem] = Field(default_factory=list, description="仓库物资；卖给杂货铺或交居民订单才变成旅费")
    plots: list[PlotSummary] = Field(default_factory=list)
    journey: JourneyBrief | None = None
    welcome: HomeWelcome | None = None
    unread: UnreadSignals = Field(default_factory=UnreadSignals)
    place: HomePlaceSummary | None = Field(default=None, description="TA 的家在哪（城市·片区，不是具体地址）", json_schema_extra={"x-additive": True})
    missing_capabilities: list[str] = Field(
        default_factory=list, description="尚未接入的能力键；前端据此显示未接入而非伪造数据"
    )
    data_origin: DataOrigin
    household: HouseholdBrief | None = Field(default=None, description="这个家属于哪个家庭、你的角色、家里有几位成员", json_schema_extra={"x-additive": True})
    pets: list[HouseholdPetBrief] = Field(default_factory=list, description="家里的全部宠物与各自此刻的状态；pet 字段是当前查看的那一只",
                                          json_schema_extra={"x-additive": True})
    catching_up: bool = Field(default=False, description="当前查看的这只宠物有已经到期、后台还没结算到的事实：世界正在更新，工资与来信稍后出现（0.4.1）",
                              json_schema_extra={"x-additive": True})


__all__ = [
    "HabitatKind",
    "HomePlaceSummary",
    "HabitatOption",
    "HomePlaceView",
    "HomePlaceRequest",
    "WalletSummary",
    "GuardBasis",
    "GuardState",
    "InventoryItem",
    "PlotStage",
    "PlotSummary",
    "FarmActionKind",
    "FarmActionRequest",
    "FarmActionResult",
    "WelcomeDetailKind",
    "WelcomeDetail",
    "HomeWelcome",
    "UnreadSignals",
    "JourneyBrief",
    "HomeSnapshot",
]
