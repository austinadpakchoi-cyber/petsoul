/**
 * claude-6c2b · 回忆页与证件卡包共用证件列表缓存：都挂在 queryKeys.credentials（["credentials","list"]）前缀下。
 * 驾校领证时失效的正是这个前缀，回忆页“已持有 N 张”跟着刷新；不再有旧键 ["life","credentials",…] 另存一份。
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import { createApiClient } from "@/shared/api/client";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { queryKeys } from "@/shared/query/queryClient";
import { buildServices, ServicesProvider } from "@/shared/services/registry";

vi.mock("@/shared/config/env", () => ({ env: { dataMode: "fixture", isDev: false, apiBase: "/api/v1/web" } }));

afterEach(() => cleanup());

describe("证件列表缓存", () => {
  it("回忆页读证件列表用的是卡包同一个前缀，驾校领证的失效能命中它", async () => {
    const modules = loadFeatureModules();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const services = buildServices(modules, { mode: "fixture", api: createApiClient("/api/v1/web") });
    const router = createMemoryRouter(buildRoutes(modules), { initialEntries: ["/memories"] });
    render(
      <QueryClientProvider client={client}>
        <ServicesProvider services={services}>
          <RouterProvider router={router} />
        </ServicesProvider>
      </QueryClientProvider>,
    );
    await screen.findByRole("heading", { name: /回忆/ });
    await waitFor(() => expect(client.getQueryCache().findAll({ queryKey: queryKeys.credentials }).length).toBeGreaterThan(0));
    expect(client.getQueryCache().findAll({ queryKey: ["life", "credentials"] }).length).toBe(0);
  });
});
