import { Navigate, NavLink, Outlet, ScrollRestoration, useLocation } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { onboardingRoute, useSessionState } from "@/shared/session/onboarding";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { ErrorState, Icon, LoadingState, Page, type IconName } from "@/shared/ui";
import "./layout.css";

/** 四个固定主入口（总方案 §4）；模块不能新增底部 Tab。 */
const TABS: Array<{ to: string; label: string; icon: IconName }> = [
  { to: "/home", label: "家", icon: "home" },
  { to: "/journey", label: "旅途", icon: "journey" },
  { to: "/circle", label: "星球", icon: "planet" },
  { to: "/communicator", label: "通讯", icon: "chat" },
];

function ModeRibbon() {
  const { platform } = useServices();
  const meta = useQuery({ queryKey: queryKeys.meta, queryFn: () => platform.meta(), staleTime: 60_000, enabled: env.dataMode === "live" });
  if (env.dataMode === "fixture") {
    return (
      <details className="ps-ribbon ps-ribbon--fixture">
        <summary>内部演示世界 · 数据说明</summary>
        <p>测试角色与数据，不代表真实账号、班次或商家；刷新后演示状态可能重置。</p>
      </details>
    );
  }
  if (!env.isDev) return null;
  if (meta.isError) {
    return (
      <div className="ps-ribbon ps-ribbon--error" role="status">
        <Icon name="alert" size={13} /> live · 未连上本地服务（{(meta.error as { code?: string }).code ?? "ERROR"}）
      </div>
    );
  }
  return (
    <div className="ps-ribbon" role="status">
      <Icon name="check" size={13} /> live · {meta.data ? `契约 ${meta.data.contract_version} · ${meta.data.backend_version} · 服务器 ${meta.data.server_time.slice(11, 19)}Z` : "连接本地服务…"}
    </div>
  );
}

/**
 * live 模式的入口守卫：带底部导航的页面只对“已登录且已入住”的账号开放；
 * 未登录去欢迎页，入住未完成回到对应的入住步骤。fixture 模式不设守卫（演示数据）。
 */
function SessionGate() {
  const session = useSessionState();
  const location = useLocation();
  if (env.dataMode !== "live") return <HouseholdProvider userId={null}><Outlet /></HouseholdProvider>;
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
  return <HouseholdProvider userId={session.data.user?.user_id ?? null}><Outlet /></HouseholdProvider>;
}

export function RootLayout() {
  return (
    <div className="ps-shell">
      <ModeRibbon />
      <SessionGate />
      <nav className="ps-tabbar" aria-label="主导航">
        {TABS.map((tab) => (
          <NavLink key={tab.to} to={tab.to} className={({ isActive }) => `ps-tab${isActive ? " is-active" : ""}`}>
            <Icon name={tab.icon} size={22} />
            <span>{tab.label}</span>
          </NavLink>
        ))}
      </nav>
      <ScrollRestoration />
    </div>
  );
}

export function BareLayout() {
  return (
    <div className="ps-shell ps-shell--bare">
      <ModeRibbon />
      <Outlet />
      <ScrollRestoration />
    </div>
  );
}
