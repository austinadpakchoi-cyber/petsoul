import { Navigate, NavLink, Outlet, ScrollRestoration, useLocation } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { onboardingRoute, useSessionState } from "@/shared/session/onboarding";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { ErrorState, Icon, LoadingState, Page, type IconName } from "@/shared/ui";
import "./layout.css";

/**
 * 三个固定主入口（地图首页方案 v2，用户 2026-09-24 确认）：地图 · 通讯器 · 回忆；“我的”在地图右上角头像。
 * 旧的“家 / 旅途 / 星球 / 通讯”四栏已退役：小窝、旅途、星球圈变成从地图或通讯器进入的二级页，深链照常可用。
 * 模块不能新增底部 Tab。
 */
const TABS: Array<{ to: string; label: string; icon: IconName }> = [
  { to: "/map", label: "地图", icon: "pin" },
  { to: "/communicator", label: "通讯器", icon: "chat" },
  { to: "/memories", label: "回忆", icon: "bookmark" },
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

/** 只有三个标签页显示底栏；二级页（小窝、菜园、朋友圈、收藏、设置……）全屏、不显示底栏（方案 2.2）。 */
function isTabPath(pathname: string): boolean {
  return TABS.some((tab) => pathname === tab.to || pathname.startsWith(`${tab.to}/`));
}

export function RootLayout() {
  const { pathname } = useLocation();
  const showTabs = isTabPath(pathname);
  return (
    <div className={`ps-shell${showTabs ? "" : " ps-shell--no-tabs"}`}>
      <ModeRibbon />
      <SessionGate />
      {showTabs ? (
        <nav className="ps-tabbar" aria-label="主导航">
          {TABS.map((tab) => (
            <NavLink key={tab.to} to={tab.to} className={({ isActive }) => `ps-tab${isActive ? " is-active" : ""}`}>
              <Icon name={tab.icon} size={22} />
              <span>{tab.label}</span>
            </NavLink>
          ))}
        </nav>
      ) : null}
      <ScrollRestoration />
    </div>
  );
}

export function BareLayout() {
  const { pathname } = useLocation();
  // 全屏页里只有地图、回忆自带新版底栏，要留出底栏高度；其余全屏页（卡包、我的、档案……）底栏高度按 0 算。
  return (
    <div className={`ps-shell ps-shell--bare${isTabPath(pathname) ? "" : " ps-shell--no-tabs"}`}>
      <ModeRibbon />
      <Outlet />
      <ScrollRestoration />
    </div>
  );
}
