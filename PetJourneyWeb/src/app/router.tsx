import { Navigate, type RouteObject } from "react-router";
import type { FeatureModule } from "@/shared/modules/types";
import { NotFoundPage, RouteErrorPage } from "./RouteErrorPage";
import { BareLayout, RootLayout } from "./RootLayout";

/** 禁止的路由：交通主界面就是 /journey 地图，不设舱室/交通场景独立页。 */
const FORBIDDEN_PATH_PATTERNS = [/cabin/i, /舱/, /^\/?transport\//i];

function collectPaths(routes: RouteObject[], owner: string, seen: Map<string, string>, prefix = "") {
  for (const route of routes) {
    const path = route.index ? prefix || "/" : route.path ? `${prefix}/${route.path}`.replace(/\/+/g, "/") : prefix;
    if (route.path || route.index) {
      if (FORBIDDEN_PATH_PATTERNS.some((re) => re.test(path))) {
        throw new Error(`模块 ${owner} 注册了不允许的路由 ${path}（一起听看只能是 /journey 地图面板）`);
      }
      const prev = seen.get(path);
      if (prev && prev !== owner) throw new Error(`路由冲突：${path} 同时由 ${prev} 与 ${owner} 注册`);
      seen.set(path, owner);
    }
    if (route.children) collectPaths(route.children, owner, seen, path);
  }
}

export function buildRoutes(modules: FeatureModule[]): RouteObject[] {
  const seen = new Map<string, string>([["/", "app"]]);
  const tabbed: RouteObject[] = [];
  const bare: RouteObject[] = [];
  for (const module of modules) {
    collectPaths(module.routes ?? [], module.id, seen);
    collectPaths(module.bareRoutes ?? [], module.id, seen);
    tabbed.push(...(module.routes ?? []));
    bare.push(...(module.bareRoutes ?? []));
  }
  return [
    {
      element: <RootLayout />,
      errorElement: <RouteErrorPage />,
      // “/” 先过主布局的登录 / 入住守卫，再进地图首页；其余路径（深链）不受首页规则影响。
      children: [{ index: true, element: <Navigate to="/map" replace /> }, ...tabbed, { path: "*", element: <NotFoundPage /> }],
    },
    {
      element: <BareLayout />,
      errorElement: <RouteErrorPage />,
      children: bare,
    },
  ];
}
