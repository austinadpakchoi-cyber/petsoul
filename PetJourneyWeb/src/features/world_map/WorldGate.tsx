/**
 * 新版一级页（地图 / 回忆）与“我的”共用的入口守卫（它们是不挂旧底栏的全屏页，需要自己守）。
 * 规则与主布局 SessionGate 相同：live 下未登录去欢迎页、入住未完成回入住步骤；fixture 不设守卫。
 * 主布局切换到三栏后，这里并回 app 壳。
 */
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { env } from "@/shared/config/env";
import { onboardingRoute, useSessionState } from "@/shared/session/onboarding";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { ErrorState, LoadingState, Page } from "@/shared/ui";

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
  if (session.data.onboarding && session.data.onboarding.step !== "active") return <Navigate to={onboardingRoute(session.data.onboarding)} replace />;
  return <HouseholdProvider userId={session.data.user?.user_id ?? null}>{children}</HouseholdProvider>;
}
