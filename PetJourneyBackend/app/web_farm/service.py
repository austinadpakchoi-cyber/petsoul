"""菜园：种植、收获、串门互偷。

规则（首发配置，集中在 CROPS）：
- 一批作物（cycle）统一成熟；全体访客合计最多偷 steal_total 单位，每个家庭每批最多一次（同一家庭几位成员分别去也只算一次）；
- 家里此刻在家的宠物看着菜园，但它们也会休息：醒着的多半会发现小偷，打盹/睡着的几率低一些；几只一起在家时合起来更难偷，
  但不是绝对防偷（上限 MAX_CATCH）。结果按访客家庭+作物批次确定，重试不改变结果；被发现就空手而归，TA 会主动告诉家里（半夜也会说）；
  全家宠物都不在家时主人可以短时巡院（有冷却），巡院时偷不到；自家成员不能“偷”自家的菜；
- 收获与偷取得到的是物资（进家庭仓库），经杂货铺/居民订单换成旅费才进入某只宠物的星球账户；库存变动以自然键去重。
"""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from ..schemas.web.farm import CropInfo, FarmWatch, NeighborHomeSummary, NeighborHomeView, NeighborPetBrief, VisitorPlot
from ..schemas.web.common import DataOrigin
from ..schemas.web.home import PlotStage, PlotSummary, WalletSummary
from ..schemas.web.pets import PetPresence, PetSpecies
from ..content_overlay import OverlayCatalog
from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from ..web_economy import WebEconomy, WebInventory

PLOTS_PER_HOME = 3
# 宠物在家时发现小偷的几率（主人巡院时一定偷不到；宠物外出又没人巡院时一定偷得到）
CATCH_CHANCE = {FarmWatch.owner_patrol: 1.0, FarmWatch.pet_awake: 0.75, FarmWatch.pet_resting: 0.35, FarmWatch.nobody: 0.0}
MAX_CATCH = 0.9  # 几只宠物一起在家也不是绝对防偷
PATROL_MINUTES = 10
PATROL_COOLDOWN_MINUTES = 30
CROP_CONTENT_TYPE = "crop"
# 可发布的字段**只有这三项**，而且每一项都有"为什么改了不会改写既有批次"的理由：
# - label / unit_value：展示名与杂货铺此刻的收购价。收购价本来就是"现在的价"，已完成的买卖记在账本里，不受影响；
# - grow_seconds：只在 plant() 那一刻读，成熟时间以 ripe_at 落在地块行上，改了不影响已经种下的批次。
# **不可发布**：yield_units、steal_total、requires_seed。前两项在 harvest()/_summary() 里是**实时读**的，
# 改了就等于静默改写进行中的批次；第三项改了会让种子账目对不上。要开放它们必须先在种植时冻结版本（列为剩余项）。
CROP_PUBLISHABLE_FIELDS = ("label", "unit_value", "grow_seconds")


def merge_crop(base: CropInfo, body: dict) -> CropInfo:
    update = {field: body[field] for field in CROP_PUBLISHABLE_FIELDS if body.get(field) is not None}
    return base.model_copy(update=update) if update else base


CROPS: dict[str, CropInfo] = OverlayCatalog(CROP_CONTENT_TYPE, merge_crop, {
    "sun_pea": CropInfo(crop_key="sun_pea", label="太阳豌豆", grow_seconds=180, yield_units=4, unit_value=2, steal_total=1),
    "star_tomato": CropInfo(crop_key="star_tomato", label="星星番茄", grow_seconds=600, yield_units=6, unit_value=2, steal_total=2),
    "moon_radish": CropInfo(crop_key="moon_radish", label="月光萝卜", grow_seconds=1800, yield_units=8, unit_value=3, steal_total=3),
    # 稀有作物：种子只能从旅行带回（连接旅行与家园），种下时消耗一颗。
    "sea_salt_pea": CropInfo(crop_key="sea_salt_pea", label="海盐豌豆", grow_seconds=900, yield_units=6, unit_value=4, steal_total=2, requires_seed=True),
    "sakura_radish": CropInfo(crop_key="sakura_radish", label="樱色萝卜", grow_seconds=1200, yield_units=8, unit_value=5, steal_total=3, requires_seed=True),
})

BUILT_IN_CROPS = frozenset(dict.keys(CROPS))


class FarmError(Exception):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass(frozen=True, slots=True)
class HomeRef:
    """一个家（属于一个家庭）。user_id 是这次操作的成员；pet_id/pet_name 是给邻居看的那只（多宠时是第一只）；pet_ids 是家里全部宠物。"""

    home_id: str
    user_id: str
    pet_id: str
    pet_name: str
    species: str
    activated: bool
    household_id: str | None = None
    pet_ids: tuple[str, ...] = ()

    @property
    def all_pets(self) -> tuple[str, ...]:
        return self.pet_ids or (self.pet_id,)

    @property
    def thief_key(self) -> str:
        return self.household_id or self.user_id


PresenceProvider = Callable[[str], PetPresence]


def _default_roll(key: str) -> float:
    return int(hashlib.sha1(key.encode("utf-8")).hexdigest()[:8], 16) / 0x100000000


class WebFarmService:
    def __init__(self, storage: JourneyStorage, economy: WebEconomy, presence_of: PresenceProvider, inventory: WebInventory | None = None) -> None:
        self.storage = storage
        self.economy = economy
        self.inventory = inventory or WebInventory(storage)
        self.presence_of = presence_of
        # TA 在家时是否在休息（睡着/打盹）；装配时由 web_agent 的状态快照注入
        self.resting_of: Callable[[str], bool] = lambda pet_id: False
        # 有人来偷菜时通知被偷的一方（TA 赶跑了小偷 / 睡着时被摘走）：(受害家, 小偷家, 作物名, 结果, 时间)
        self.on_watch_event: Callable[[HomeRef, HomeRef, str, str, datetime], None] = lambda victim, thief, crop, outcome, now: None
        self.catch_roll: Callable[[str], float] = _default_roll
        # 稀有种子是宠物从旅行带回的收藏；种下时从这个家任意一只宠物的收藏里消耗一颗（并发失败退回同一只的）
        self.consume_seed: Callable[[HomeRef, str], str | None] = lambda home, crop_key: None
        self.refund_seed: Callable[[str, str], None] = lambda pet_id, crop_key: None

    # ---- 地块 ----
    def ensure_plots(self, home_id: str) -> None:
        with self.storage.connect() as conn:
            for slot in range(PLOTS_PER_HOME):
                conn.execute(
                    "INSERT OR IGNORE INTO web_farm_plots (plot_id, home_id, slot) VALUES (?, ?, ?)",
                    (f"{home_id}-p{slot}", home_id, slot),
                )

    def plots(self, home_id: str, now: datetime | None = None) -> list[PlotSummary]:
        now = now or utcnow()
        self.ensure_plots(home_id)
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT * FROM web_farm_plots WHERE home_id = ? ORDER BY slot", (home_id,)).fetchall()
        return [self._summary(row, now) for row in rows]

    def _summary(self, row: sqlite3.Row, now: datetime) -> PlotSummary:
        crop = CROPS.get(row["crop_key"] or "")
        if crop is None or row["cycle_id"] is None:
            stage = PlotStage.empty
        elif row["harvested_at"]:
            stage = PlotStage.harvested
        elif parse_dt(row["ripe_at"]) <= now:
            stage = PlotStage.ripe
        else:
            stage = PlotStage.growing
        return PlotSummary(
            plot_id=row["plot_id"],
            cycle_id=row["cycle_id"],
            crop_key=row["crop_key"],
            crop_label=crop.label if crop else None,
            stage=stage,
            ripe_at=parse_dt(row["ripe_at"]) if row["ripe_at"] else None,
            steal_total=crop.steal_total if crop else None,
            steal_remaining=(crop.steal_total - row["stolen_units"]) if crop else None,
        )

    def _plot_row(self, conn: sqlite3.Connection, home_id: str, plot_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM web_farm_plots WHERE plot_id = ? AND home_id = ?", (plot_id, home_id)).fetchone()
        if row is None:
            raise FarmError("not_found", "没有这块地。")
        return row

    def plant(self, home: HomeRef, plot_id: str, crop_key: str, now: datetime | None = None) -> PlotSummary:
        now = now or utcnow()
        crop = CROPS.get(crop_key)
        if crop is None:
            raise FarmError("unknown_crop", "没有这种种子。")
        self.ensure_plots(home.home_id)
        with self.storage.connect() as conn:
            row = self._plot_row(conn, home.home_id, plot_id)
        if row["cycle_id"] and not row["harvested_at"]:
            raise FarmError("occupied", "这块地还在种着。")
        # 先消耗种子（独立事务），再以版本号条件种下；并发下种失败则退回种子。
        seed_owner = self.consume_seed(home, crop_key) if crop.requires_seed else None
        if crop.requires_seed and seed_owner is None:
            raise FarmError("no_seed", f"还没有{crop.label}的种子，要等 TA 从旅行里带回来。")
        with self.storage.connect() as conn:
            planted = conn.execute(
                "UPDATE web_farm_plots SET cycle_id = ?, crop_key = ?, planted_at = ?, ripe_at = ?, stolen_units = 0, harvested_at = NULL, "
                "version = version + 1 WHERE plot_id = ? AND version = ?",
                (f"cy-{uuid.uuid4().hex[:12]}", crop_key, iso(now), iso(now + timedelta(seconds=crop.grow_seconds)), plot_id, row["version"]),
            ).rowcount
            row = self._plot_row(conn, home.home_id, plot_id)
        if planted != 1:
            if seed_owner is not None:
                self.refund_seed(seed_owner, crop_key)
            raise FarmError("occupied", "这块地刚被种上了。")
        return self._summary(row, now)

    def harvest(self, home: HomeRef, plot_id: str, now: datetime | None = None) -> tuple[PlotSummary, WalletSummary, int]:
        """收获：成熟作物（扣除被摘走的）进仓库。返回 (地块, 钱包, 入库单位数)；重放不重复入库。"""
        now = now or utcnow()
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = self._plot_row(conn, home.home_id, plot_id)
            summary = self._summary(row, now)
            if summary.stage is PlotStage.harvested:
                cycle_id = row["cycle_id"]
            elif summary.stage is not PlotStage.ripe:
                raise FarmError("not_ripe", "还没成熟。")
            else:
                cycle_id = row["cycle_id"]
                conn.execute(
                    "UPDATE web_farm_plots SET harvested_at = ?, version = version + 1 WHERE plot_id = ? AND cycle_id = ? AND harvested_at IS NULL",
                    (iso(now), plot_id, cycle_id),
                )
            row = self._plot_row(conn, home.home_id, plot_id)
        crop = CROPS[row["crop_key"]]
        units = max(0, crop.yield_units - row["stolen_units"])
        self.inventory.add(home.user_id, home.home_id, crop.crop_key, units, f"收获{crop.label}", f"harvest:{cycle_id}", now)
        return self._summary(row, now), self.economy.wallet(home.pet_id), units

    # ---- 守护与巡院 ----
    def _patrol_row(self, home_id: str):
        with self.storage.connect() as conn:
            return conn.execute("SELECT * FROM web_farm_patrols WHERE home_id = ?", (home_id,)).fetchone()

    def patrol_window(self, home_id: str, now: datetime | None = None) -> tuple[datetime | None, datetime | None]:
        """(巡院守护截止时间（进行中才有）, 下一次可巡院时间（冷却中才有）)。"""
        now = now or utcnow()
        row = self._patrol_row(home_id)
        if row is None:
            return None, None
        until = parse_dt(row["until"])
        next_at = parse_dt(row["started_at"]) + timedelta(minutes=PATROL_COOLDOWN_MINUTES)
        return (until if until > now else None), (next_at if next_at > now else None)

    def pets_home(self, target: HomeRef) -> list[str]:
        """此刻在家的宠物（按实际位置）。"""
        return [pet for pet in target.all_pets if self.presence_of(pet) is PetPresence.at_home]

    def guarding_pets(self, target: HomeRef) -> list[str]:
        """此刻在家且醒着、在看菜园的宠物。"""
        return [pet for pet in self.pets_home(target) if not self.resting_of(pet)]

    def guarded_by(self, target: HomeRef, now: datetime | None = None) -> str | None:
        """pet_at_home / owner_patrol / None。"""
        if self.pets_home(target):
            return "pet_at_home"
        until, _ = self.patrol_window(target.home_id, now)
        return "owner_patrol" if until else None

    def watch(self, target: HomeRef, now: datetime | None = None) -> FarmWatch:
        guard = self.guarded_by(target, now)
        if guard == "owner_patrol":
            return FarmWatch.owner_patrol
        if guard == "pet_at_home":
            return FarmWatch.pet_awake if self.guarding_pets(target) else FarmWatch.pet_resting
        return FarmWatch.nobody

    def catch_chance(self, target: HomeRef, watch: FarmWatch) -> float:
        """在家的每只宠物各自有机会发现小偷，合起来更难偷，但封顶 MAX_CATCH（不是绝对防偷）。"""
        if watch in (FarmWatch.owner_patrol, FarmWatch.nobody):
            return CATCH_CHANCE[watch]
        home = self.pets_home(target)
        awake = set(self.guarding_pets(target))
        miss = 1.0
        for pet in home:
            miss *= 1.0 - CATCH_CHANCE[FarmWatch.pet_awake if pet in awake else FarmWatch.pet_resting]
        return min(MAX_CATCH, 1.0 - miss)

    def patrol(self, home: HomeRef, now: datetime | None = None) -> tuple[datetime, datetime]:
        """宠物外出时主人巡院 PATROL_MINUTES 分钟；冷却 PATROL_COOLDOWN_MINUTES 分钟。进行中重复点击返回同一窗口。"""
        now = now or utcnow()
        if self.pets_home(home):
            raise FarmError("pet_home", "家里有宠物在家守着菜园，不用巡院。")
        until, next_at = self.patrol_window(home.home_id, now)
        if until:
            return until, next_at or until
        if next_at:
            raise FarmError("cooldown", "刚巡过院，歇一会儿再去。")
        until = now + timedelta(minutes=PATROL_MINUTES)
        with self.storage.connect() as conn:
            conn.execute("INSERT INTO web_farm_patrols (home_id, started_at, until) VALUES (?, ?, ?) "
                         "ON CONFLICT(home_id) DO UPDATE SET started_at = excluded.started_at, until = excluded.until",
                         (home.home_id, iso(now), iso(until)))
        return until, now + timedelta(minutes=PATROL_COOLDOWN_MINUTES)

    # ---- 串门 ----
    def steal(self, thief: HomeRef, target: HomeRef, plot_id: str, cycle_id: str, now: datetime | None = None) -> tuple[PlotSummary, str, str]:
        now = now or utcnow()
        if thief.home_id == target.home_id or (thief.household_id is not None and thief.household_id == target.household_id):
            raise FarmError("own_home", "自己家的菜不用偷。")
        if not thief.activated or not target.activated:
            raise FarmError("not_active", "还没入住的家不能串门。")
        watch = self.watch(target, now)
        if watch is FarmWatch.owner_patrol:
            raise FarmError("guarded", f"{target.pet_name} 的主人正在巡院，被发现啦，只好空手而归。")
        crop_label = self._crop_label(target.home_id, plot_id)
        if watch in (FarmWatch.pet_awake, FarmWatch.pet_resting) and self.catch_roll(f"{cycle_id}:{thief.thief_key}:{plot_id}") < self.catch_chance(target, watch):
            self.on_watch_event(target, thief, crop_label, "caught_awake" if watch is FarmWatch.pet_awake else "caught_resting", now)
            if watch is FarmWatch.pet_awake:
                raise FarmError("guarded", f"{target.pet_name} 正在家，一眼就发现了你，只好空手而归。")
            raise FarmError("guarded", f"{target.pet_name} 本来在打盹，还是被你惊醒了，只好空手而归。")
        with self.storage.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = self._plot_row(conn, target.home_id, plot_id)
            if row["cycle_id"] != cycle_id:
                raise FarmError("stale_cycle", "这批作物已经换过了，刷新看看。")
            summary = self._summary(row, now)
            if summary.stage is not PlotStage.ripe:
                raise FarmError("not_ripe", "还没成熟，偷不了。")
            try:
                conn.execute(
                    "INSERT INTO web_farm_steals (cycle_id, thief_user_id, plot_id, victim_home_id, units, created_at, thief_household_id) VALUES (?, ?, ?, ?, 1, ?, ?)",
                    (cycle_id, thief.user_id, plot_id, target.home_id, iso(now), thief.household_id),
                )
            except sqlite3.IntegrityError as exc:
                raise FarmError("already_taken", "这批你家已经摘过一次了。") from exc
            crop = CROPS[row["crop_key"]]
            updated = conn.execute(
                "UPDATE web_farm_plots SET stolen_units = stolen_units + 1, version = version + 1 "
                "WHERE plot_id = ? AND cycle_id = ? AND harvested_at IS NULL AND stolen_units < ?",
                (plot_id, cycle_id, crop.steal_total),
            ).rowcount
            if updated != 1:
                conn.rollback()
                raise FarmError("nothing_left", "这批能摘的都被摘完了。")
            row = self._plot_row(conn, target.home_id, plot_id)
        self.inventory.add(thief.user_id, thief.home_id, crop.crop_key, 1, f"从 {target.pet_name} 家摘了{crop.label}", f"steal:{cycle_id}:{thief.thief_key}", now)
        if watch is FarmWatch.pet_resting:
            self.on_watch_event(target, thief, crop.label, "stolen_while_resting", now)
            return self._summary(row, now), crop.crop_key, f"趁 {target.pet_name} 在打盹，悄悄摘走了一颗{crop.label}，放进了自己家的仓库。"
        if watch is FarmWatch.pet_awake:
            return self._summary(row, now), crop.crop_key, f"{target.pet_name} 一不留神，你悄悄摘走了一颗{crop.label}，放进了自己家的仓库。"
        return self._summary(row, now), crop.crop_key, f"悄悄摘走了一颗{crop.label}，放进了自己家的仓库。"

    def _crop_label(self, home_id: str, plot_id: str) -> str:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT crop_key FROM web_farm_plots WHERE home_id = ? AND plot_id = ?", (home_id, plot_id)).fetchone()
        crop = CROPS.get(row["crop_key"]) if row and row["crop_key"] else None
        return crop.label if crop else "菜"

    def neighbors(self, viewer: HomeRef, avatar_of: Callable[[str], str | None], home_ref_of: Callable[[str], "HomeRef | None"],
                  limit: int = 30) -> list[NeighborHomeSummary]:
        """别的家庭已入住的家（不含自己家庭的家）。presence 取“有没有宠物在家”；展示的宠物是那个家的第一只。"""
        now = utcnow()
        with self.storage.connect() as conn:
            rows = conn.execute(
                "SELECT h.home_id FROM web_homes h WHERE h.activated_at IS NOT NULL AND h.home_id != ? "
                "AND (h.household_id IS NULL OR ? IS NULL OR h.household_id != ?) ORDER BY h.activated_at DESC LIMIT ?",
                (viewer.home_id, viewer.household_id, viewer.household_id, limit),
            ).fetchall()
        result = []
        for row in rows:
            target = home_ref_of(row["home_id"])
            if target is None:
                continue
            home_pets = self.pets_home(target)
            presence = PetPresence.at_home if home_pets else self.presence_of(target.pet_id)
            patrolling = not home_pets and self.patrol_window(target.home_id, now)[0] is not None
            watch = self.watch(target, now)
            ripe = [p for p in self.plots(target.home_id, now) if p.stage is PlotStage.ripe and (p.steal_remaining or 0) > 0]
            result.append(
                NeighborHomeSummary(
                    home_id=target.home_id,
                    pet=NeighborPetBrief(pet_id=target.pet_id, name=target.pet_name, species=PetSpecies(target.species), avatar_url=avatar_of(target.pet_id)),
                    presence=presence,
                    guarded=bool(home_pets) or patrolling,
                    stealable_plots=len(ripe),
                    watch=watch,
                    data_origin=DataOrigin.live,
                )
            )
        return result

    def visit(self, viewer: HomeRef, target: HomeRef, avatar_url: str | None) -> NeighborHomeView:
        now = utcnow()
        presence = PetPresence.at_home if self.pets_home(target) else self.presence_of(target.pet_id)
        with self.storage.connect() as conn:
            taken = {
                row["cycle_id"]
                for row in conn.execute("SELECT cycle_id FROM web_farm_steals WHERE (thief_user_id = ? OR thief_household_id = ?) AND victim_home_id = ?",
                                        (viewer.user_id, viewer.household_id, target.home_id))
            }
        return NeighborHomeView(
            home_id=target.home_id,
            pet=NeighborPetBrief(pet_id=target.pet_id, name=target.pet_name, species=PetSpecies(target.species), avatar_url=avatar_url),
            presence=presence,
            guarded=self.guarded_by(target, now) is not None,
            plots=[VisitorPlot(plot=p, taken_by_me=p.cycle_id in taken) for p in self.plots(target.home_id, now)],
            watch=self.watch(target, now),
            server_time=now,
            data_origin=DataOrigin.live,
        )

    def steals_since(self, home_id: str, since: datetime) -> int:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM web_farm_steals WHERE victim_home_id = ? AND created_at >= ?", (home_id, iso(since))).fetchone()
        return int(row["n"])
