/**
 * 新版三栏（地图 · 通讯器 · 回忆）的预览底栏：挂在新版一级页（/map、/memories）底部。
 * 主布局切换前，旧页面仍挂旧四栏；切换后这里并回 app 壳的底栏。
 */
import { NavLink } from "react-router";
import { Icon, type IconName } from "@/shared/ui";
import "./world-map.css";

const TABS: Array<{ to: string; label: string; icon: IconName }> = [
  { to: "/map", label: "地图", icon: "pin" },
  { to: "/communicator", label: "通讯器", icon: "chat" },
  { to: "/memories", label: "回忆", icon: "bookmark" },
];

export function PreviewTabBar() {
  return (
    <nav className="ps-wmap-tabs" aria-label="主导航（新版预览）">
      {TABS.map((tab) => (
        <NavLink key={tab.to} to={tab.to} end className={({ isActive }) => `ps-wmap-tab${isActive ? " is-active" : ""}`}>
          <Icon name={tab.icon} size={20} />
          <span>{tab.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
