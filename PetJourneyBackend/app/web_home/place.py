"""TA 的家：一个概念，但确实落在某座城市里（用户 2026-09-22 的方向）。

- 注册/入住时问主人“希望 TA 住在哪里”：海边、草原、沙漠、森林、湖边、山里、城市、田园；
- 在对应类型的真实片区里随机一个（国内，高德可查地点与路线），只显示“城市·片区”，不给具体地址；
- 坐标在片区中心附近随机偏移（约 1 公里内），不对应任何门牌；出门就从这里出发；
- 没选过的家沿用首发默认：香港·中环（与早期演示线路一致）。
海外片区要等 Google 地图可用后再加。

真实体验（用户 2026-09-22 阶段 3）：新家只开放“真实交通与真实地点都已接通”的片区（OPEN_AREAS：香港·中环、香港·西贡——
住在这里的宠物可以按高德估时去码头、按已核验的船期去澳门）。其他片区保留给已经住在那里的家，不再分配给新家，直到对应城市接通。
待领养居民住在星球居民驿站（web_residences），驿站也是一个 HomePlace（id 以 res- 开头），出门从驿站出发。
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, replace
from datetime import datetime

from ..storage import JourneyStorage
from ..utils import iso, parse_dt

HK, CN = "Asia/Hong_Kong", "Asia/Shanghai"


@dataclass(frozen=True)
class Area:
    key: str
    label: str  # 例如“环岛路附近的海边”
    city: str
    lat: float
    lng: float
    timezone: str = CN


HABITATS: dict[str, tuple[str, tuple[Area, ...]]] = {
    "seaside": ("海边", (
        Area("hk_saikung", "西贡的海边", "香港", 22.3818, 114.2719, HK),
        Area("xm_huandao", "环岛路附近的海边", "厦门", 24.4366, 118.1135),
        Area("qd_badaguan", "八大关附近的海边", "青岛", 36.0535, 120.3526),
        Area("sy_haitang", "海棠湾的海边", "三亚", 18.3180, 109.7340),
        Area("dl_xinghai", "星海湾附近的海边", "大连", 38.8789, 121.5854),
    )),
    "grassland": ("草原", (
        Area("hulunbuir", "海拉尔附近的草原", "呼伦贝尔", 49.2150, 119.7650),
        Area("xilinhot", "锡林浩特附近的草原", "锡林郭勒", 43.9333, 116.0833),
        Area("ruoergai", "若尔盖的草原", "阿坝", 33.5780, 102.9630),
    )),
    "desert": ("沙漠", (
        Area("dunhuang", "鸣沙山附近", "敦煌", 40.0890, 94.6760),
        Area("zhongwei", "沙坡头附近", "中卫", 37.4630, 105.0000),
    )),
    "forest": ("森林", (
        Area("xishuangbanna", "雨林边的小寨子", "西双版纳", 22.0100, 100.7970),
        Area("shennongjia", "林区里", "神农架", 31.7440, 110.6760),
        Area("changbaishan", "二道白河的林边", "长白山", 42.4000, 128.1000),
    )),
    "lakeside": ("湖边", (
        Area("hz_xihu", "西湖边", "杭州", 30.2470, 120.1480),
        Area("dali_erhai", "洱海边", "大理", 25.7000, 100.1900),
        Area("sz_jinjihu", "金鸡湖边", "苏州", 31.3120, 120.6950),
    )),
    "mountain": ("山里", (
        Area("huangshan", "黄山脚下", "黄山", 30.1000, 118.1700),
        Area("yangshuo", "阳朔的山间", "桂林", 24.7780, 110.4960),
        Area("moganshan", "莫干山里", "湖州", 30.6060, 119.8740),
    )),
    "city": ("城市", (
        Area("hk_central", "中环", "香港", 22.2819, 114.1581, HK),
        Area("sh_xuhui", "徐汇的老街区", "上海", 31.2050, 121.4410),
        Area("cd_yulin", "玉林的街巷", "成都", 30.6330, 104.0630),
        Area("gz_dongshan", "东山口", "广州", 23.1290, 113.2960),
        Area("bj_hutong", "胡同里", "北京", 39.9380, 116.3990),
    )),
    "countryside": ("田园", (
        Area("wuyuan", "婺源的田野边", "上饶", 29.2480, 117.8610),
        Area("anji", "安吉的竹林村", "湖州", 30.6380, 119.6800),
        Area("wuzhen", "乌镇边上", "嘉兴", 30.7440, 120.4870),
    )),
}
AREAS = {area.key: (habitat, area) for habitat, (_, areas) in HABITATS.items() for area in areas}
DEFAULT_AREA = "hk_central"
OPEN_AREAS = frozenset({"hk_central", "hk_saikung"})  # 新家可分配的片区（真实交通与地点已接通）
FUZZ_METERS = 900


@dataclass(frozen=True)
class HomePlace:
    habitat: str
    habitat_label: str
    area_key: str
    area_label: str
    city: str
    lat: float
    lng: float
    timezone: str
    chosen: bool  # False＝主人没选过，沿用默认

    @property
    def display(self) -> str:
        return f"{self.city}·{self.area_label}"

    def node(self) -> dict:
        return {"node_id": "node-home", "name": "家", "kind": "place", "timezone": self.timezone, "lat": self.lat, "lng": self.lng, "verified": False}


def _unit(seed: str) -> float:
    return int(hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8], 16) / 0x100000000


def fuzz(lat: float, lng: float, seed: str, meters: float = FUZZ_METERS) -> tuple[float, float]:
    """片区中心附近的随机一点（不对应门牌）。"""
    angle = _unit(seed + ":a") * 2 * math.pi
    radius = (0.3 + 0.7 * _unit(seed + ":r")) * meters
    dlat = radius * math.cos(angle) / 111_320
    dlng = radius * math.sin(angle) / (111_320 * math.cos(math.radians(lat)))
    return round(lat + dlat, 5), round(lng + dlng, 5)


def default_place() -> HomePlace:
    habitat, area = AREAS[DEFAULT_AREA]
    return HomePlace(habitat, HABITATS[habitat][0], area.key, area.label, area.city, area.lat, area.lng, area.timezone, False)


def _fuzzed(place: HomePlace, seed: str) -> HomePlace:
    """把一个**没有落库**的片区参考点，按种子偏移成片区里的一点。

    为什么需要它：`default_place()` 给的是片区参考点本身，**一个片区所有没落库的家都会共用它**。
    落过库的家在 `assign()` 时已经偏移过（写进 `web_home_places`），两条路径走到这里语义就不一致了。
    种子用 `home_id` / `residence_id`：`fuzz` 是纯函数，**同一个家每次算出同一点**，
    不是每次随机——地图上不会自己漂。
    """
    lat, lng = fuzz(place.lat, place.lng, seed)
    return replace(place, lat=lat, lng=lng)


class HomePlaceStore:
    def __init__(self, storage: JourneyStorage) -> None:
        self.storage = storage

    def get(self, home_id: str) -> HomePlace:
        if home_id.startswith("res-"):
            return self.residence(home_id)
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_home_places WHERE home_id = ?", (home_id,)).fetchone()
        if row is None:
            # 没选过环境的家在这张表里没有行。**原先直接返回 `default_place()`，
            # 那是片区的参考点、没有任何偏移——于是所有这类家会落在同一个坐标上**
            # （6c2b 2026-09-24 做地图端到端时发现：`/world/state` 给的 home.center
            # 正好是中环参考点 22.2819/114.1581，多只宠物在地图上会叠在一起）。
            #
            # 这里按 `home_id` 做种子偏移一次：**同一个家每次算出同一点**（`fuzz` 是纯函数、
            # 种子稳定，不是每次随机），不同的家分散开。偏移量与 `assign()` 写库时用的是同一个
            # `FUZZ_METERS`，所以「家在片区里、不对应门牌」这条语义两条路径一致。
            return _fuzzed(default_place(), home_id)
        habitat, area = AREAS.get(row["area_key"], AREAS[DEFAULT_AREA])
        return HomePlace(habitat, HABITATS[habitat][0], area.key, area.label, area.city, row["lat"], row["lng"], area.timezone, True)

    def residence(self, residence_id: str) -> HomePlace:
        """星球居民驿站（待领养居民住的地方）：片区里的概念地点，不对应门牌。"""
        with self.storage.connect() as conn:
            row = conn.execute("SELECT * FROM web_residences WHERE residence_id = ?", (residence_id,)).fetchone()
        if row is None or row["area_key"] not in AREAS:
            return _fuzzed(default_place(), residence_id)  # 同上：不让找不到的驿站全部叠在参考点上
        habitat, area = AREAS[row["area_key"]]
        return HomePlace(habitat, HABITATS[habitat][0], area.key, row["label"].split("·", 1)[-1], area.city, row["lat"], row["lng"], row["timezone"], True)

    def assign(self, home_id: str, habitat: str, now: datetime, open_only: bool = False) -> HomePlace:
        """在该类型的片区里随机一个。家要稳定：同一类型重复提交保持原来的城市，只有换成另一类地方（迁居）才重新分配。
        open_only：只在开放片区里分配（新家与迁居）；这一类没有开放片区时 ValueError。"""
        if habitat not in HABITATS:
            raise ValueError("没有这一类地方。")
        with self.storage.connect() as conn:
            current = conn.execute("SELECT habitat FROM web_home_places WHERE home_id = ?", (home_id,)).fetchone()
        if current is not None and current["habitat"] == habitat:
            return self.get(home_id)
        _, areas = HABITATS[habitat]
        if open_only:
            areas = tuple(a for a in areas if a.key in OPEN_AREAS)
            if not areas:
                raise ValueError(f"{HABITATS[habitat][0]}还没开放：这类地方的真实交通和地点还没接通，先选海边或城市（香港）。")
        seed = f"{home_id}:{habitat}:{iso(now)}"
        area = areas[int(_unit(seed) * len(areas)) % len(areas)]
        lat, lng = fuzz(area.lat, area.lng, seed)
        with self.storage.connect() as conn:
            conn.execute(
                "INSERT INTO web_home_places (home_id, habitat, area_key, lat, lng, chosen_at) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(home_id) DO UPDATE SET habitat = excluded.habitat, area_key = excluded.area_key, lat = excluded.lat, lng = excluded.lng, "
                "chosen_at = excluded.chosen_at",
                (home_id, habitat, area.key, lat, lng, iso(now)),
            )
        return self.get(home_id)

    def chosen_at(self, home_id: str) -> datetime | None:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT chosen_at FROM web_home_places WHERE home_id = ?", (home_id,)).fetchone()
        return parse_dt(row["chosen_at"]) if row else None
