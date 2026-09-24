/** 路由与会话外壳：没有员工会话就只给登录页；有会话就按权限显示导航。 */
import { useCallback, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router";
import { AdminError, api } from "./api/client";
import type { SessionView } from "./api/types";
import { GlossaryProvider, Term, TechToggle } from "./labels";
import AssetsPage from "./pages/AssetsPage";
import AuditPage from "./pages/AuditPage";
import BatchesPage from "./pages/BatchesPage";
import ContentDetailPage from "./pages/ContentDetailPage";
import ContentPage from "./pages/ContentPage";
import CostsPage from "./pages/CostsPage";
import EconomyChecksPage from "./pages/EconomyChecksPage";
import HomePage from "./pages/HomePage";
import LedgersPage from "./pages/LedgersPage";
import LoginPage from "./pages/LoginPage";
import MfaPage from "./pages/MfaPage";
import OverviewPage from "./pages/OverviewPage";
import PetPage from "./pages/PetPage";
import PetsRuntimePage from "./pages/PetsRuntimePage";
import PhotosPage from "./pages/PhotosPage";
import ReportsPage from "./pages/ReportsPage";
import ResidentsPage from "./pages/ResidentsPage";
import SearchPage from "./pages/SearchPage";
import StaffPage from "./pages/StaffPage";
import SystemPage from "./pages/SystemPage";
import UserPage from "./pages/UserPage";

/** permission 可以是一条，也可以是几条任一（例如待领养居民：客服或内容运营都要看）。 */
const NAV: { group: string; items: { to: string; label: string; permission: string | string[]; end?: boolean }[] }[] = [
  { group: "排查", items: [
    { to: "/", label: "运营首页", permission: "ops.read", end: true },
    { to: "/search", label: "用户与宠物", permission: "user.read" },
    { to: "/pets-runtime", label: "宠物运行", permission: "pet.read" },
    { to: "/photos", label: "照片与任务", permission: "task.read" },
    { to: "/system", label: "系统运行", permission: "ops.read" },
  ] },
  { group: "运营", items: [
    { to: "/reports", label: "举报审核", permission: "report.read" },
    { to: "/content", label: "内容发布", permission: "content.read" },
    { to: "/residents", label: "待领养居民", permission: ["user.read", "content.read"] },
    { to: "/assets", label: "素材库", permission: "asset.read" },
    { to: "/ledgers", label: "两本账", permission: "provider.read" },
    { to: "/costs", label: "平台成本", permission: "provider.read" },
    { to: "/economy/checks", label: "经济对账", permission: "economy.read" },
    { to: "/batches", label: "批量补偿", permission: "economy.read" },
  ] },
  { group: "治理", items: [
    { to: "/audit", label: "操作记录", permission: "audit.read" },
    { to: "/staff", label: "员工与角色", permission: "staff.manage" },
  ] },
];

export default function App() {
  const [session, setSession] = useState<SessionView | null>(null);
  const [ready, setReady] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setSession(await api.get<SessionView>("/auth/session"));
    } catch (error) {
      if (error instanceof AdminError && [401, 403].includes(error.status)) setSession(null);
      else throw error;
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  if (!ready) return <div className="login-wrap"><div className="login-card">正在确认员工会话…</div></div>;
  if (!session) return <LoginPage onSignedIn={refresh} />;
  if (!session.mfa_satisfied) return <MfaPage session={session} onDone={refresh} />;
  return <GlossaryProvider><Shell session={session} onSignedOut={refresh} /></GlossaryProvider>;
}

function Shell({ session, onSignedOut }: { session: SessionView; onSignedOut: () => void }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [query, setQuery] = useState("");
  // 窄屏（手机）时侧栏是抽屉：点「菜单」打开，换页或点遮罩就收起；桌面宽度下这两样都不显示
  const [navOpen, setNavOpen] = useState(false);
  useEffect(() => { setNavOpen(false); }, [location.pathname]);
  const can = (permission: string) => session.staff.permissions.includes(permission);
  const allowed = (permission: string | string[]) => (Array.isArray(permission) ? permission.some(can) : can(permission));
  const envClass = `env-badge env-${["dev", "staging", "production"].includes(session.environment) ? session.environment : "dev"}`;

  return (
    <div className={`shell${navOpen ? " nav-open" : ""}`}>
      <div className="nav-backdrop" onClick={() => setNavOpen(false)} aria-hidden="true" />
      <aside className="sidebar" id="admin-nav">
        <div className="brand">PetSoul 运营后台<small>员工端 · 与玩家网页分开</small></div>
        <nav className="nav">
          {NAV.map((group) => {
            const items = group.items.filter((item) => allowed(item.permission));
            if (items.length === 0) return null;
            return (
              <div key={group.group}>
                <div className="nav-group">{group.group}</div>
                {items.map((item) => (
                  <NavLink key={item.to} to={item.to} end={item.end}
                           className={({ isActive }) => (isActive ? "active" : "")}>{item.label}</NavLink>
                ))}
              </div>
            );
          })}
        </nav>
        <div className="sidebar-foot">
          后端 {session.admin_version}
          <br />
          {session.staff.mfa_enabled ? "二次验证已启用" : "二次验证未启用"}
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <button type="button" className="nav-toggle ghost" aria-controls="admin-nav" aria-expanded={navOpen}
                  onClick={() => setNavOpen((open) => !open)}>☰ 菜单</button>
          <span className={envClass}>{session.environment.toUpperCase()}</span>
          {can("user.read") && (
            <form onSubmit={(e) => { e.preventDefault(); if (query.trim()) navigate(`/search?q=${encodeURIComponent(query.trim())}`); }}>
              <input value={query} onChange={(e) => setQuery(e.target.value)}
                     placeholder="搜用户编号 / 用户名 / 宠物编号 / 宠物名" aria-label="全局检索" />
              <button type="submit">查找</button>
            </form>
          )}
          <TechToggle />
          <div className="who">
            <strong>{session.staff.display_name}</strong> · {session.staff.roles.map((role, index) => (
              <span key={role}>{index > 0 && " / "}<Term family="role" code={role} /></span>))}
            <br />
            <a href="#" onClick={async (e) => { e.preventDefault(); await api.post("/auth/logout"); onSignedOut(); }}>退出</a>
          </div>
        </header>

        <main className="content">
          <Routes>
            <Route path="/" element={<OverviewPage session={session} />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/users/:userId" element={<UserPage session={session} />} />
            <Route path="/pets/:petId" element={<PetPage session={session} />} />
            <Route path="/pets-runtime" element={<PetsRuntimePage session={session} />} />
            <Route path="/homes/:homeId" element={<HomePage session={session} />} />
            <Route path="/system" element={<SystemPage />} />
            <Route path="/photos" element={<PhotosPage session={session} />} />
            <Route path="/reports" element={<ReportsPage session={session} />} />
            <Route path="/content" element={<ContentPage session={session} />} />
            <Route path="/residents" element={<ResidentsPage session={session} />} />
            <Route path="/content/:itemId" element={<ContentDetailPage session={session} />} />
            <Route path="/assets" element={<AssetsPage session={session} />} />
            <Route path="/ledgers" element={<LedgersPage />} />
            <Route path="/costs" element={<CostsPage session={session} />} />
            <Route path="/economy/checks" element={<EconomyChecksPage session={session} />} />
            <Route path="/batches" element={<BatchesPage session={session} />} />
            <Route path="/audit" element={<AuditPage />} />
            <Route path="/staff" element={<StaffPage session={session} />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
