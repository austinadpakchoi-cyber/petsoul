"""共同的家：一个家庭一个家（多位成员、多只宠物共用），入住阶段、入住激活、HomeSnapshot 权威快照。

- 家按家庭查（web_homes.household_id）；宠物经家庭关系找到它的家，不再假定“一个账号一只宠物一个家”；
- 每只宠物有自己的入住进度（可选接待 → 可以入住 → 已经住进来）；家的激活（第一只宠物入住）只发生一次；
- 入住只激活家与生活（种下欢迎作物、这个家发一次欢迎旅费给第一只入住的宠物），不自动把宠物送去外地；
  欢迎作物与欢迎旅费以自然键去重，进程在激活后中断也能在下一次入住/读取时补齐，不会重复发放；
  之后再加进这个家的宠物不再领家庭欢迎旅费（避免不断添宠物套取奖励）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from ..schemas import EconomyTransactionType
from ..schemas.web.common import DataOrigin
from ..schemas.web.home import GuardBasis, GuardState, HomeSnapshot, HomeWelcome, InventoryItem, JourneyBrief, UnreadSignals
from ..schemas.web.household import EntryIntentView, PetJoinStep
from ..schemas.web.pets import PetPresence, PetPrivateSummary
from ..storage import JourneyStorage
from ..utils import iso, parse_dt, utcnow
from ..web_economy import WebEconomy
from ..web_farm import HomeRef, WebFarmService
from ..web_farm.service import CROPS
from ..web_household import HouseholdService, PetAccess
from .model import HomeRow, PetHome
from .onboarding import HomeOnboardingMixin

__all__ = ["WELCOME_GIFT", "HomeRow", "PetHome", "WebHomeService"]

WELCOME_GIFT = 20


class WebHomeService(HomeOnboardingMixin):
    def __init__(self, storage: JourneyStorage, economy: WebEconomy, farm: WebFarmService, households: HouseholdService) -> None:
        self.storage = storage
        self.economy = economy
        self.farm = farm
        self.households = households
        self.presence_of: Callable[[str, bool], PetPresence] = lambda pet_id, activated: PetPresence.at_home if activated else PetPresence.not_activated
        self.journey_brief_of: Callable[[str], JourneyBrief | None] = lambda pet_id: None
        self.welcome_of: Callable[[str, str], HomeWelcome | None] = lambda user_id, pet_id: None
        self.owner_title_of: Callable[[str, str], str | None] = lambda user_id, pet_id: None
        self.unread_of: Callable[[str, str], UnreadSignals] = lambda user_id, pet_id: UnreadSignals()
        self.place_of: Callable[[str], object] = lambda home_id: None  # HomePlaceSummary（TA 的家在哪）
        self.pet_summary_of: Callable[[str], PetPrivateSummary | None] = lambda pet_id: None
        self.entry_of: Callable[[str], EntryIntentView | None] = lambda user_id: None
        self.reception_done_of: Callable[[str], bool] = self._reception_done

    # ---- 读取 ----
    @staticmethod
    def _from(row) -> HomeRow | None:
        if row is None:
            return None
        return HomeRow(home_id=row["home_id"], household_id=row["household_id"], user_id=row["user_id"], pet_id=row["pet_id"],
                       activated_at=parse_dt(row["activated_at"]) if row["activated_at"] else None,
                       public_posts=bool(row["public_posts"]), version=row["version"])

    def by_home_id(self, home_id: str) -> HomeRow | None:
        with self.storage.connect() as conn:
            return self._from(conn.execute("SELECT * FROM web_homes WHERE home_id = ?", (home_id,)).fetchone())

    def by_household(self, household_id: str) -> HomeRow | None:
        with self.storage.connect() as conn:
            return self._from(conn.execute("SELECT * FROM web_homes WHERE household_id = ?", (household_id,)).fetchone())

    def by_pet(self, pet_id: str) -> HomeRow | None:
        """宠物所在家庭的家；待领养居民（没有家庭）返回 None。"""
        with self.storage.connect() as conn:
            return self._from(conn.execute(
                "SELECT h.* FROM web_homes h JOIN web_household_pets p ON p.household_id = h.household_id WHERE p.pet_id = ?", (pet_id,)).fetchone())

    def home_created_by(self, user_id: str) -> HomeRow | None:
        """这个账号建立的那个家（一个账号最多建立一个家庭）。只在确实需要“建立者”语义时使用。"""
        with self.storage.connect() as conn:
            return self._from(conn.execute("SELECT * FROM web_homes WHERE user_id = ?", (user_id,)).fetchone())

    def pet_home(self, access: PetAccess) -> PetHome:
        home = self.by_household(access.household_id)
        assert home is not None, "every household has a home"
        return PetHome(access=access, home=home)

    def ref(self, home: HomeRow, acting_user_id: str | None = None) -> HomeRef:
        pets = self.households.pets_of(home.household_id) if home.household_id else [home.pet_id]
        first = pets[0] if pets else home.pet_id
        with self.storage.connect() as conn:
            row = conn.execute("SELECT pets.name, p.species FROM pets JOIN web_pet_profiles p ON p.pet_id = pets.pet_id WHERE pets.pet_id = ?", (first,)).fetchone()
        return HomeRef(home_id=home.home_id, user_id=acting_user_id or home.user_id, pet_id=first, pet_name=row["name"], species=row["species"],
                       activated=home.activated_at is not None, household_id=home.household_id, pet_ids=tuple(pets))

    def ref_of_home(self, home_id: str) -> HomeRef | None:
        home = self.by_home_id(home_id)
        return None if home is None else self.ref(home)

    # ---- 入住 ----
    def move_in(self, pet_home: PetHome, public_posts: bool, now: datetime | None = None) -> bool:
        """这只宠物住进它的家。家还没激活时先激活（只发生一次），并补齐欢迎作物与欢迎旅费。返回这只宠物是否是这次才住进来。"""
        now = now or utcnow()
        home = pet_home.home
        if home.activated_at is None:
            with self.storage.connect() as conn:
                conn.execute("UPDATE web_homes SET activated_at = ?, public_posts = ?, version = version + 1 WHERE home_id = ? AND activated_at IS NULL",
                             (iso(now), 1 if public_posts else 0, home.home_id))
            home = self.by_home_id(home.home_id) or home
        self.ensure_welcome(home, now)
        moved = self.households.mark_moved_in(pet_home.pet_id, now)
        if moved:
            with self.storage.connect() as conn:
                conn.execute("UPDATE web_homes SET version = version + 1 WHERE home_id = ?", (home.home_id,))
        return moved

    def ensure_welcome(self, home: HomeRow, now: datetime | None = None) -> None:
        """欢迎作物（第一块地从没种过时种下）与欢迎旅费（这个家一次，给第一只宠物）；都以自然键去重，可安全重复调用。"""
        if home.activated_at is None:
            return
        now = now or utcnow()
        plots = self.farm.plots(home.home_id, now)
        if plots and plots[0].cycle_id is None:
            try:
                self.farm.plant(self.ref(home), plots[0].plot_id, "sun_pea", now)  # 欢迎作物：三分钟后可收获
            except Exception:  # noqa: BLE001 - 并发下已被种上
                pass
        self.economy.apply(home.pet_id, WELCOME_GIFT, EconomyTransactionType.web_reward, f"web:welcome_gift:{home.home_id}",
                           reason="入住欢迎旅费（每个家一次，不可交易）", source="web.home.move_in", now=home.activated_at)

    def set_public_posts(self, household_id: str, public_posts: bool) -> None:
        with self.storage.connect() as conn:
            conn.execute("UPDATE web_homes SET public_posts = ?, version = version + 1 WHERE household_id = ?", (1 if public_posts else 0, household_id))

    # ---- 快照 ----
    def guard_state(self, home: HomeRow, now: datetime) -> GuardState:
        """家里有宠物在家 → 守护（醒着的才真正看着菜园）；全家都不在家时，只有主人巡院窗口内才守护。"""
        if home.activated_at is None:
            return GuardState(guarding=False, basis=GuardBasis.none)
        ref = self.ref(home)
        at_home = self.farm.pets_home(ref)
        if at_home:
            return GuardState(guarding=True, basis=GuardBasis.pet_at_home, guarding_pets=self.farm.guarding_pets(ref))
        until, next_at = self.farm.patrol_window(home.home_id, now)
        if until:
            return GuardState(guarding=True, basis=GuardBasis.owner_patrol, until=until, next_patrol_at=next_at)
        return GuardState(guarding=False, basis=GuardBasis.none, next_patrol_at=next_at)

    def pantry_of(self, home_id: str) -> list[InventoryItem]:
        return [InventoryItem(item_key=key, label=CROPS[key].label if key in CROPS else key, qty=qty, unit_price=CROPS[key].unit_value if key in CROPS else 0)
                for key, qty in self.farm.inventory.quantities(home_id).items()]

    def snapshot(self, pet_home: PetHome, now: datetime | None = None) -> HomeSnapshot:
        now = now or utcnow()
        user_id, pet_id = pet_home.user_id, pet_home.pet_id
        pet = self.pet_summary_of(pet_id)
        assert pet is not None
        step = self.join_step(pet_id, pet_home.home)
        activated = pet_home.home.activated_at is not None
        presence = self.presence_of(pet_id, activated and step is PetJoinStep.moved_in)
        home = self.by_home_id(pet_home.home_id) or pet_home.home  # presence 可能补齐了回家事件
        self.ensure_welcome(home, now)
        pet = pet.model_copy(update={"presence": presence, "owner_title": self.owner_title_of(user_id, pet_id), "home_id": home.home_id})
        missing = [] if activated else ["home.not_activated"]
        return HomeSnapshot(
            home_id=home.home_id, server_time=now, version=home.version, pet=pet, presence=presence, guard=self.guard_state(home, now),
            wallet=self.economy.wallet(pet_id), pantry=self.pantry_of(home.home_id), plots=self.farm.plots(home.home_id, now) if activated else [],
            journey=self.journey_brief_of(pet_id) if presence in (PetPresence.in_transit, PetPresence.visiting, PetPresence.returning) else None,
            welcome=self.welcome_of(user_id, pet_id), unread=self.unread_of(user_id, pet_id), place=self.place_of(home.home_id),
            missing_capabilities=missing, data_origin=DataOrigin.live,
            household=self.household_brief(user_id, pet_home.household_id), pets=self.pet_briefs(user_id, pet_home.household_id, home),
        )
