/**
 * claude-6c2b · 新版导航的登录守卫（live）：“/” 先过主布局守卫——未登录去欢迎页，入住未完成回入住步骤，已入住进地图首页。
 * 换首页不能绕过欢迎页和入住（c84a 审阅第 2 条）。
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import type { SessionState } from "@/shared/contracts";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";

vi.mock("@/shared/config/env", () => ({ env: { dataMode: "live", isDev: false, apiBase: "/api/v1/web" } }));

afterEach(() => cleanup());

const modules = loadFeatureModules();
const never = () => new Promise<never>(() => undefined);

/** 只有会话是真的，其余服务一律“还在读”：这里只看路由去了哪里。 */
function servicesWith(session: SessionState): ServiceMap {
  const stub = new Proxy({}, { get: (_t, prop) => (prop === "then" ? undefined : prop === "fixtureScenarios" || prop === "fixtureVariants" ? () => [] : never) });
  return new Proxy({} as ServiceMap, {
    get: (_t, key) => {
      if (key === "session") return new Proxy(stub, { get: (t, p) => (p === "current" ? async () => session : Reflect.get(t, p)) });
      return stub;
    },
  });
}

function renderApp(path: string, session: SessionState) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(buildRoutes(modules), { initialEntries: [path] });
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={servicesWith(session)}>
        <RouterProvider router={router} />
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return router;
}

const anonymous: SessionState = { authenticated: false, user: null, csrf_required: false, expires_at: null, onboarding: null };

describe("新版导航的登录守卫（live）", () => {
  it("未登录打开“/”：去欢迎页，不进地图", async () => {
    const router = renderApp("/", anonymous);
    await waitFor(() => expect(router.state.location.pathname).toBe("/welcome"));
  });

  it("未登录直接打开 /map：同样去欢迎页（地图页自带同一套守卫）", async () => {
    const router = renderApp("/map", anonymous);
    await waitFor(() => expect(router.state.location.pathname).toBe("/welcome"));
  });

  it("访客深链 /world 不需要登录，也不被首页规则吞掉", async () => {
    const router = renderApp("/world", anonymous);
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(router.state.location.pathname).toBe("/world");
  });
});
