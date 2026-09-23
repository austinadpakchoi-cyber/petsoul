"""共同的家：每只宠物的入住进度（可选接待 → 可以入住 → 已经住进来）、家庭与宠物摘要、账号级的入住阶段。"""

from __future__ import annotations

from ..schemas.web.household import HouseholdBrief, HouseholdPetBrief, HouseholdRole, PetJoinStep
from ..schemas.web.identity import OnboardingState, OnboardingStep
from ..utils import parse_dt
from .model import HomeRow


class HomeOnboardingMixin:
    """需要 self.storage、self.households、self.by_pet / by_household 与注入的 presence_of、pet_summary_of、entry_of、reception_done_of。"""

    # ---- 读取 ----
    def _reception_done(self, session_id: str) -> bool:
        with self.storage.connect() as conn:
            row = conn.execute("SELECT status FROM web_reception_sessions WHERE session_id = ?", (session_id,)).fetchone()
        return bool(row and row["status"] in ("completed", "skipped"))

    # ---- 每只宠物的入住进度 ----
    def join_step(self, pet_id: str, home: HomeRow | None = None) -> PetJoinStep:
        row = self.households.onboarding_row(pet_id)
        home = home or self.by_pet(pet_id)
        if row is None:
            return PetJoinStep.moved_in if home and home.activated_at else PetJoinStep.reception_optional
        if row["moved_in_at"]:
            return PetJoinStep.moved_in
        if row["reception_skipped"] or (row["reception_session_id"] and self.reception_done_of(row["reception_session_id"])):
            return PetJoinStep.ready_to_move_in
        return PetJoinStep.reception_optional

    def record_reception(self, pet_id: str, session_id: str, skipped: bool) -> None:
        self.households.record_reception(pet_id, session_id, skipped)

    def pet_briefs(self, user_id: str, household_id: str, home: HomeRow) -> list[HouseholdPetBrief]:
        briefs: list[HouseholdPetBrief] = []
        with self.storage.connect() as conn:
            rows = conn.execute("SELECT pet_id, joined_at, added_by FROM web_household_pets WHERE household_id = ? ORDER BY position, joined_at, pet_id",
                                (household_id,)).fetchall()
        for row in rows:
            summary = self.pet_summary_of(row["pet_id"])
            if summary is None:
                continue
            step = self.join_step(row["pet_id"], home)
            presence = self.presence_of(row["pet_id"], home.activated_at is not None and step is PetJoinStep.moved_in)
            briefs.append(HouseholdPetBrief(pet_id=row["pet_id"], name=summary.name, species=summary.species, photo_url=summary.photo_url, origin=summary.origin,
                                            presence=presence, join_step=step, joined_at=parse_dt(row["joined_at"]), added_by_you=row["added_by"] == user_id))
        return briefs

    def household_brief(self, user_id: str, household_id: str) -> HouseholdBrief | None:
        access = self.households.access_household(user_id, household_id)
        home = self.by_household(household_id)
        if access is None or home is None:
            return None
        row = self.households.household_row(household_id)
        return HouseholdBrief(household_id=household_id, name=row["name"] if row else None, home_id=home.home_id, role=HouseholdRole(access.role.value),
                              home_activated=home.activated_at is not None, member_count=len(self.households.members_of(household_id)),
                              pets=self.pet_briefs(user_id, household_id, home))

    def households_of(self, user_id: str) -> list[HouseholdBrief]:
        return [b for m in self.households.memberships(user_id) if (b := self.household_brief(user_id, m.household_id)) is not None]

    # ---- 入住阶段（按账号） ----
    def onboarding(self, user_id: str) -> OnboardingState:
        """账号级的入住阶段：
        - 还没加入任何家庭 → needs_companion（带上注册入口：选中的伙伴 / 家庭邀请，等用户确认）；
        - 自己刚添进家庭、还没住进来的宠物优先 → reception_optional / ready_to_move_in；
        - 否则有已入住的家 → active（pet_id 是第一只宠物，兼容只照顾一只宠物的旧页面）。"""
        households = self.households_of(user_id)
        entry = self.entry_of(user_id)
        if not households:
            return OnboardingState(step=OnboardingStep.needs_companion, entry=entry)
        focus: tuple[HouseholdBrief, HouseholdPetBrief] | None = None
        for brief in households:
            for pet in brief.pets:
                if pet.join_step is not PetJoinStep.moved_in and (pet.added_by_you or not brief.home_activated):
                    focus = (brief, pet)
                    break
            if focus:
                break
        if focus is None:
            active = next((b for b in households if b.home_activated and b.pets), None)
            brief = active or households[0]
            if not brief.pets:
                return OnboardingState(step=OnboardingStep.needs_companion, households=households, entry=entry)
            pet = next((p for p in brief.pets if p.join_step is PetJoinStep.moved_in), brief.pets[0])
            step = OnboardingStep.active if brief.home_activated else OnboardingStep.reception_optional
        else:
            brief, pet = focus
            step = OnboardingStep.ready_to_move_in if pet.join_step is PetJoinStep.ready_to_move_in else OnboardingStep.reception_optional
        row = self.households.onboarding_row(pet.pet_id)
        home = self.by_household(brief.household_id)
        return OnboardingState(step=step, pet_id=pet.pet_id, home_id=brief.home_id,
                               reception_session_id=row["reception_session_id"] if row else None,
                               reception_skipped=bool(row["reception_skipped"]) if row else False,
                               home_activated_at=home.activated_at if home else None, pet_origin=pet.origin, households=households, entry=entry)
