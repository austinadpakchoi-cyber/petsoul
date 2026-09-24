/**
 * 新版一级页（地图 / 回忆）与“我的”共用的入口守卫（它们是不挂旧底栏的全屏页，需要自己守）。
 * 规则与主布局 SessionGate 相同：live 下未登录去欢迎页、入住未完成回入住步骤；fixture 不设守卫。
 * 主布局切换到三栏后，这里并回 app 壳。
 * 2026-09-24 巡检 P1：账号里已经有住进来的宠物时，第二只还在接待 / 入住也不拦（原来整个账号的页面都被拉回接待页，后退也出不去）；
 * 只有一只都没住进来（真正的第一次入住）才带去入住步骤。主布局 SessionGate 是同一条规则，tests/claude-6c2b-second-pet.test.tsx 两处一起钉。
 */
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import type { HouseholdPetBrief, OnboardingState } from "@/shared/contracts";
import { env } from "@/shared/config/env";
import { onboardingRoute, useSessionState } from "@/shared/session/onboarding";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { ErrorState, LoadingState, Page } from "@/shared/ui";

/** 已经住进来的宠物：已启用的家里 join_step 为 moved_in 的（与切换栏列出的是同一批）。 */
export function movedInPets(onboarding: OnboardingState | null | undefined): HouseholdPetBrief[] {
  return (onboarding?.households ?? []).flatMap((household) => (household.home_activated ? household.pets.filter((pet) => pet.join_step === "moved_in") : []));
}

/** 账号里有没有已经住进来的宠物。一只都没有（真正的第一次入住）才把页面带去入住步骤。 */
export function hasMovedInPet(onboarding: OnboardingState | null | undefined): boolean {
  return movedInPets(onboarding).length > 0;
}

/**
 * 第二只还在接待 / 入住时，“先不加了，回到 {名字}”回到的那只：地图上会显示的当前宠物——切换栏记住的那只（得是已经住进来的），
 * 没记过就是第一只住进来的（与 HouseholdProvider 挑当前宠物同一条规则）。待入住的那只不在其中，所以当前宠物不会被换成它。
 * 一只都没住进来（第一次入住）返回 null：没有可回的地方，不给这个出口。
 */
export function petToReturnTo(onboarding: OnboardingState | null | undefined, userId: string | null | undefined): HouseholdPetBrief | null {
  const settled = movedInPets(onboarding);
  if (!settled.length) return null;
  let preferred: string | null = null;
  try {
    preferred = userId ? sessionStorage.getItem(`petsoul:current-pet:${userId}`) : null;
  } catch {
    /* 读不到记住的那只，就回第一只 */
  }
  return settled.find((pet) => pet.pet_id === preferred) ?? settled[0];
}

export function WorldGate({ children }: { children: ReactNode }) {
  if (env.dataMode !== "live") return <HouseholdProvider userId={null}>{children}</HouseholdProvider>;
  return <LiveGate>{children}</LiveGate>;
}

function LiveGate({ children }: { children: ReactNode }) {
  const session = useSessionState();
  const location = useLocation();
  if (session.isPending) {
    return (
      <Page>
        <LoadingState lines={2} label="正在确认登录状态…" />
      </Page>
    );
  }
  if (session.isError) {
    return (
      <Page>
        <ErrorState error={session.error} onRetry={() => void session.refetch()} />
      </Page>
    );
  }
  if (!session.data.authenticated) return <Navigate to="/welcome" replace state={{ from: location.pathname }} />;
  const onboarding = session.data.onboarding;
  if (onboarding && onboarding.step !== "active" && !hasMovedInPet(onboarding)) return <Navigate to={onboardingRoute(onboarding)} replace />;
  return <HouseholdProvider userId={session.data.user?.user_id ?? null}>{children}</HouseholdProvider>;
}
