"""家附近的日常出门：散步、喝杯咖啡、进城逛逛、打工。出发地是 TA 的家（web_home.place.HomePlace）。

- 地点：有地图服务时用高德/Google 在家附近找真实地点（带来源与取回时间），步行/打车按真实路线估时；
  没有地图服务时：散步、喝一杯、打工去星球里的地方（世界规则设定的地点与路程，明确标成“星球内”，不冒充现实地址）；
  进城逛逛和自驾兜风需要真实地点，地图不可用时不成立（明确返回原因）；演示环境（demo=True）才使用“示例”地点；
- 打工：按家的类型给出合适的活计（海边去渔港帮忙收网、草原去牧场看羊……），干完活工钱进 TA 的银行卡；
- 钱不够时只能散步或打工（散步和打工不花钱）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from ..content_overlay import OverlayCatalog
from .catalog import Destination, LegPlan, VenuePlan
from .geo_plan import region_of

# 家的类型 → (在附近散步时找的地点关键词, 口语里的叫法)
HABITAT_SPOT = {
    "seaside": ("海滩|海滨公园|观景台", "海边"),
    "grassland": ("草原|牧场|景区", "草原上"),
    "desert": ("沙漠|景区", "沙丘边"),
    "forest": ("森林公园|景区|植物园", "林子里"),
    "lakeside": ("公园|湖", "湖边"),
    "mountain": ("景区|登山|公园", "山路上"),
    "city": ("公园|广场", "附近的公园"),
    "countryside": ("古镇|景区|公园", "田边"),
}


@dataclass(frozen=True)
class LocalKind:
    key: str
    title: str
    summary: str
    fee: int
    stay_minutes: int
    mode: str  # walk / taxi
    fallback_minutes: int
    radius: int
    template: str  # park / cafe / generic


LOCAL = {
    "stroll": LocalKind("stroll", "在家附近走走", "不花钱，出门透透气，看看附近有什么新鲜事。", 0, 40, "walk", 12, 1500, "park"),
    "cafe": LocalKind("cafe", "去附近喝一杯", "走到附近的咖啡馆坐一会儿。", 8, 25, "walk", 8, 800, "cafe"),
    "city_trip": LocalKind("city_trip", "进城逛逛", "打车去城里有名的地方逛一逛。", 30, 90, "taxi", 25, 6000, "generic"),
    # 需要驾驶证（服务端校验）；租一辆小车，费用从银行卡出
    "drive_trip": LocalKind("drive_trip", "自己开车去兜风", "拿到驾照后，租一辆小车自己开去远一点的地方。", 20, 60, "drive", 30, 15000, "generic"),
}
NEEDS_LICENSE = {"local:drive_trip"}


@dataclass(frozen=True)
class Job:
    key: str
    label: str  # 例如“咖啡馆帮工”
    keyword: str
    hours: int
    pay: int
    habitats: tuple[str, ...] | None = None  # None＝哪里都有


JOB_CONTENT_TYPE = "job"
# 可发布的字段：岗位名、工时、工钱。keyword 与 habitats 是"哪里有这个活"的世界规则，不可发布。
# 工钱在 work_done 事件**发生时**被写进事件数据、随后入账，所以发新版本只影响此后新发生的打工，
# 已经结算过的工资一分都不动。
JOB_PUBLISHABLE_FIELDS = ("label", "hours", "pay")


def merge_job(base: "Job", body: dict) -> "Job":
    update = {field: body[field] for field in JOB_PUBLISHABLE_FIELDS if body.get(field) is not None}
    return replace(base, **update) if update else base


JOBS = OverlayCatalog(JOB_CONTENT_TYPE, merge_job, {
    "cafe_helper": Job("cafe_helper", "在咖啡馆帮工", "咖啡", 3, 24),
    "florist": Job("florist", "在花店帮忙", "花店", 2, 16),
    "post_office": Job("post_office", "在邮局分拣信件", "邮局", 3, 24),
    "bookstore": Job("bookstore", "在书店理书", "书店", 2, 16, ("city", "lakeside", "countryside")),
    "fishing_port": Job("fishing_port", "去渔港帮忙收网", "码头|渔港", 3, 28, ("seaside",)),
    "ranch": Job("ranch", "去牧场帮忙看羊", "牧场|农场", 4, 30, ("grassland", "countryside")),
    "ranger": Job("ranger", "跟着护林员巡山", "景区|森林公园", 3, 26, ("forest", "mountain")),
    "camel_team": Job("camel_team", "帮骆驼队牵绳", "景区", 3, 28, ("desert",)),
})

BUILT_IN_JOBS = frozenset(dict.keys(JOBS))


def jobs_for(habitat: str) -> list[Job]:
    return [job for job in JOBS.values() if job.habitats is None or habitat in job.habitats]


def is_local(key: str) -> bool:
    return key.startswith("local:") or key.startswith("work:")


def job_of(key: str) -> Job | None:
    return JOBS.get(key.split(":", 1)[1]) if key.startswith("work:") else None


@dataclass(frozen=True)
class LocalPlan:
    destination: Destination
    real_place: object | None  # PlaceCandidate
    template: str
    basis: str = "world_rule"  # 地点与路程依据：real（地图供应商）/ world_rule（星球内）/ demo_fixture（演示环境）


class LocalUnavailable(Exception):
    """需要真实地点的活动（进城、自驾）在地图不可用时不成立。"""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


NEEDS_REAL_PLACE = {"city_trip", "drive_trip"}
WORLD_SPOT = {  # 地图不可用时星球内的地方（世界规则设定，不对应现实地址）
    "stroll": "家附近的星球小路",
    "cafe": "星球居民开的小咖啡馆",
}
WORLD_CATEGORY = {  # 星球内／演示的地方：类目按**这次出门是什么种类**给，不按家的栖息地
    "cafe": "咖啡馆",  # 名字是咖啡馆、模板是 cafe，类目也必须是咖啡馆，否则照片导演认不出、一直 hold
}  # 没列在这里的（散步）落回栖息地词——散步本来就是去家附近那类地方，那个词是对的
WORLD_WALK_KMH = 4.5


def _node(node_id: str, name: str, lat: float, lng: float, tz: str) -> dict:
    return {"node_id": node_id, "name": name, "kind": "place", "timezone": tz, "lat": lat, "lng": lng, "verified": False}


def local_plan(key: str, home, geo=None, demo: bool = False) -> LocalPlan | None:
    """home: HomePlace。geo: GeoService（可为空）。未知的 key 返回 None；需要真实地点却拿不到时抛 LocalUnavailable（演示环境除外）。"""
    job = job_of(key)
    kind = LOCAL.get(key.split(":", 1)[1]) if key.startswith("local:") else None
    if job is None and kind is None:
        return None
    if job is not None and job.habitats is not None and home.habitat not in job.habitats:
        return None
    keyword = job.keyword if job else ("咖啡" if kind.key == "cafe" else ("景点|景区|地标" if kind.key in ("city_trip", "drive_trip") else HABITAT_SPOT[home.habitat][0]))
    radius = 1200 if job else kind.radius
    mode = "walk" if job else kind.mode
    region = region_of(home.timezone)
    place = None
    if geo is not None and geo.configured(region):
        for search_radius in (radius, int(radius * 2.5)):  # 附近找不到就再走远一点找；两次都没有才去星球内的地方
            place = geo.place_near(region, home.lat, home.lng, keyword=keyword, google_type="tourist_attraction", radius=search_radius)
            if place is not None:
                break
    spot_word = HABITAT_SPOT[home.habitat][1]
    if place is not None:
        name, lat, lng, category, basis = place.name, place.lat, place.lng, place.category, "real"
    elif demo:
        name = f"示例·{job.label.removeprefix('在').removeprefix('去')}（演示）" if job else f"示例·{spot_word}（演示）" if kind.key == "stroll" else (
            "示例·附近的咖啡馆（演示）" if kind.key == "cafe" else f"示例·{home.city}城里（演示）")
        lat, lng, category, basis = home.lat + (0.0045 if mode == "walk" else 0.03), home.lng + 0.003, None, "demo_fixture"
    else:
        if kind is not None and kind.key in NEEDS_REAL_PLACE:
            raise LocalUnavailable("map_unavailable", f"{kind.title}要去现实里的地方，地图服务现在不可用，这趟先不去。")
        workplace = f"星球{job.label.removeprefix('在').removeprefix('去')}的地方" if job else None
        name = workplace or WORLD_SPOT[kind.key]
        lat, lng, category, basis = home.lat + 0.0045, home.lng + 0.003, None, "world_rule"
    venue_node = _node("node-local-venue", name, lat, lng, home.timezone)
    home_node = home.node()
    role = "walker" if mode == "walk" else ("driver" if mode == "drive" else "passenger")
    minutes = 10 if job else kind.fallback_minutes
    if basis == "world_rule":  # 星球内的路程：按世界规则（步行每小时约 4.5 公里）估算
        minutes = max(5, round(_distance_km(home.lat, home.lng, lat, lng) / WORLD_WALK_KMH * 60))
    stay = job.hours * 60 if job else kind.stay_minutes
    if job:
        title, summary, fee, template = job.label, f"干 {job.hours} 小时活，工钱 {job.pay} 存进银行卡。", 0, "generic"
    else:
        title = f"去{name}走走" if kind.key == "stroll" and place is not None else kind.title
        summary, fee, template = kind.summary, kind.fee, kind.template
    place_id = place.place_id if place else (f"demo:{key}" if basis == "demo_fixture" else f"world:{key}")
    if place is not None:
        venue_category = category  # 真实地点：供应商给什么就是什么。**没给就留空**——伪造一个词等于把"不知道"说成"知道"
    elif job:
        venue_category = "打工"
    else:
        venue_category = WORLD_CATEGORY.get(kind.key, spot_word)  # 按出门的种类给；散步落回栖息地词
    venue = VenuePlan(place_id, name, lat, lng, home.timezone, venue_category, stay)
    destination = Destination(
        key=key, title=title, city=home.city, summary=summary, fee=fee,
        outbound=(LegPlan("main", mode, role, minutes, home_node, venue_node),),
        venue=venue,
        inbound=(LegPlan("main", mode, role, minutes, venue_node, home_node),),
    )
    return LocalPlan(destination=destination, real_place=place, template=template, basis=basis)


def _distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1) * math.cos(math.radians((lat1 + lat2) / 2))
    return 6371.0 * math.hypot(dlat, dlng)


def local_options(home, licensed: bool = False) -> list[tuple[str, str, str, int, int]]:
    """出发站上可以给 TA 的建议：(key, 标题, 说明, 费用, 大约时长分钟)。不调用地图服务；没有驾照时不给自驾兜风。
    需要真实地点的（进城、自驾）在地图不可用时由调用方标成不可用。"""
    options = [(f"local:{k.key}", k.title, k.summary, k.fee, k.fallback_minutes * 2 + k.stay_minutes) for k in LOCAL.values()
               if licensed or f"local:{k.key}" not in NEEDS_LICENSE]
    options += [(f"work:{j.key}", j.label, f"干 {j.hours} 小时活，工钱 {j.pay} 存进银行卡。", 0, 20 + j.hours * 60) for j in jobs_for(home.habitat)]
    return options
