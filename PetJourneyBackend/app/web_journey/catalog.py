"""出发站目的地目录（首发演示线路）。

全部 time_basis=demo_fixture：时长按常见现实量级设定并**按真实经过时间推进**（不压缩），
但尚未接入核验时刻表/路线服务，因此不能称为真实班次或实时车程。地点均为明确的“示例”店，
不对应真实商家。动物世界承运人（喵航/爪爪铁路/海獭轮渡）为原创身份；出租车/步行不伪造班次。
"""

from __future__ import annotations

from dataclasses import dataclass, field

HOME_NODE = {"node_id": "node-home", "name": "家", "kind": "place", "timezone": "Asia/Hong_Kong", "lat": 22.2819, "lng": 114.1581, "verified": False}


def node(node_id: str, name: str, kind: str, tz: str, lat: float, lng: float) -> dict:
    return {"node_id": node_id, "name": name, "kind": kind, "timezone": tz, "lat": lat, "lng": lng, "verified": False}


@dataclass(frozen=True)
class LegPlan:
    kind: str  # main / connection / wait / transfer
    mode: str
    role: str
    minutes: int
    origin: dict
    destination: dict
    carrier: str | None = None  # 动物世界承运人；None 表示不发放公共班次身份
    code_prefix: str | None = None
    schematic: bool = False


@dataclass(frozen=True)
class VenuePlan:
    place_id: str
    name: str
    lat: float
    lng: float
    tz: str
    category: str
    stay_minutes: int


@dataclass(frozen=True)
class Destination:
    key: str
    title: str
    city: str
    summary: str
    fee: int
    outbound: tuple[LegPlan, ...]
    venue: VenuePlan
    inbound: tuple[LegPlan, ...]
    wish_keywords: tuple[str, ...] = field(default_factory=tuple)
    food_area: str | None = None

    @property
    def total_minutes(self) -> int:
        return sum(l.minutes for l in self.outbound) + self.venue.stay_minutes + sum(l.minutes for l in self.inbound)

    @property
    def modes(self) -> list[str]:
        seen: list[str] = []
        for leg in (*self.outbound, *self.inbound):
            if leg.kind != "wait" and leg.mode not in seen:
                seen.append(leg.mode)
        return seen


HK_CAFE = node("node-hk-cafe", "示例·海边咖啡馆", "place", "Asia/Hong_Kong", 22.2855, 114.1577)
CENTRAL_PIER = node("node-central-pier", "中环码头（示意）", "port", "Asia/Hong_Kong", 22.287, 114.157)
MACAU_PIER = node("node-macau-pier", "澳门码头（示意）", "port", "Asia/Macau", 22.197, 113.557)
MACAU_CAFE = node("node-macau-cafe", "示例·街角咖啡馆（澳门）", "place", "Asia/Macau", 22.1935, 113.5405)
HKG = node("node-hkg", "香港机场（示意）", "airport", "Asia/Hong_Kong", 22.308, 113.918)
HND = node("node-hnd", "东京机场（示意）", "airport", "Asia/Tokyo", 35.549, 139.779)
TOKYO_STATION = node("node-tokyo-city", "东京市区站（示意）", "station", "Asia/Tokyo", 35.681, 139.767)
TOKYO_CAFE = node("node-tokyo-cafe", "示例·巷口咖啡馆（东京）", "place", "Asia/Tokyo", 35.6812, 139.7707)

DESTINATIONS: dict[str, Destination] = {
    "harbour_cafe": Destination(
        key="harbour_cafe",
        title="海边咖啡馆",
        city="香港",
        summary="走几分钟去示例咖啡馆坐坐，适合现场完整走一遍（约半小时往返）。",
        fee=8,
        outbound=(LegPlan("main", "walk", "walker", 6, HOME_NODE, HK_CAFE),),
        venue=VenuePlan("demo:hk-harbour-cafe", "示例·海边咖啡馆（演示店）", HK_CAFE["lat"], HK_CAFE["lng"], "Asia/Hong_Kong", "咖啡馆", 20),
        inbound=(LegPlan("main", "walk", "walker", 6, HK_CAFE, HOME_NODE),),
        wish_keywords=("咖啡", "散步"),
        food_area="hk-harbour",
    ),
    "macau_ferry": Destination(
        key="macau_ferry",
        title="坐船去澳门",
        city="澳门",
        summary="打车到码头，坐海獭轮渡看海，到街角咖啡馆坐一会儿再回来（约 4 小时）。",
        fee=40,
        outbound=(
            LegPlan("connection", "taxi", "passenger", 15, HOME_NODE, CENTRAL_PIER),
            LegPlan("wait", "ferry", "passenger", 20, CENTRAL_PIER, CENTRAL_PIER),
            LegPlan("main", "ferry", "passenger", 60, CENTRAL_PIER, MACAU_PIER, carrier="海獭轮渡", code_prefix="Otter"),
            LegPlan("connection", "walk", "walker", 10, MACAU_PIER, MACAU_CAFE),
        ),
        venue=VenuePlan("demo:macau-corner-cafe", "示例·街角咖啡馆（澳门·演示店）", MACAU_CAFE["lat"], MACAU_CAFE["lng"], "Asia/Macau", "咖啡馆", 40),
        inbound=(
            LegPlan("connection", "walk", "walker", 10, MACAU_CAFE, MACAU_PIER),
            LegPlan("wait", "ferry", "passenger", 20, MACAU_PIER, MACAU_PIER),
            LegPlan("main", "ferry", "passenger", 60, MACAU_PIER, CENTRAL_PIER, carrier="海獭轮渡", code_prefix="Otter"),
            LegPlan("connection", "taxi", "passenger", 15, CENTRAL_PIER, HOME_NODE),
        ),
        wish_keywords=("海", "船", "澳门"),
        food_area="macau-old-town",
    ),
    "tokyo_flight": Destination(
        key="tokyo_flight",
        title="飞去东京",
        city="东京",
        summary="坐喵航飞东京，再换爪爪铁路进城，喝杯咖啡后返程（约 13 小时，演示航线）。",
        fee=120,
        outbound=(
            LegPlan("connection", "taxi", "passenger", 35, HOME_NODE, HKG),
            LegPlan("wait", "flight", "passenger", 60, HKG, HKG),
            LegPlan("main", "flight", "passenger", 240, HKG, HND, carrier="喵航", code_prefix="Cat", schematic=True),
            LegPlan("main", "train", "passenger", 40, HND, TOKYO_STATION, carrier="爪爪铁路", code_prefix="Paw"),
            LegPlan("connection", "walk", "walker", 8, TOKYO_STATION, TOKYO_CAFE),
        ),
        venue=VenuePlan("demo:tokyo-alley-cafe", "示例·巷口咖啡馆（东京·演示店）", TOKYO_CAFE["lat"], TOKYO_CAFE["lng"], "Asia/Tokyo", "咖啡馆", 60),
        inbound=(
            LegPlan("connection", "walk", "walker", 8, TOKYO_CAFE, TOKYO_STATION),
            LegPlan("main", "train", "passenger", 40, TOKYO_STATION, HND, carrier="爪爪铁路", code_prefix="Paw"),
            LegPlan("wait", "flight", "passenger", 60, HND, HND),
            LegPlan("main", "flight", "passenger", 270, HND, HKG, carrier="喵航", code_prefix="Cat", schematic=True),
            LegPlan("connection", "taxi", "passenger", 35, HKG, HOME_NODE),
        ),
        wish_keywords=("飞", "东京", "日本", "飞机"),
        food_area="tokyo-alley",
    ),
}
