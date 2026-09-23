import { useMemo } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router";
import { apiClient } from "@/shared/api/client";
import { env } from "@/shared/config/env";
import { createQueryClient } from "@/shared/query/queryClient";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import { buildSlotRegistry, SlotProvider } from "@/shared/slots/Slot";
import { ErrorBoundary } from "@/shared/ui";
import { loadFeatureModules } from "./modules";
import { buildRoutes } from "./router";

/** 组合根：模块发现 → 服务（按 fixture/live）→ 插槽 → 路由。只有框架窗口修改本文件。 */
export function App() {
  const { router, services, slots, queryClient } = useMemo(() => {
    const modules = loadFeatureModules();
    return {
      router: createBrowserRouter(buildRoutes(modules)),
      services: buildServices(modules, { mode: env.dataMode, api: apiClient }),
      slots: buildSlotRegistry(modules.flatMap((m) => m.slots ?? [])),
      queryClient: createQueryClient(),
    };
  }, []);
  return (
    <ErrorBoundary scope="app">
      <QueryClientProvider client={queryClient}>
        <ServicesProvider services={services}>
          <SlotProvider registry={slots}>
            <RouterProvider router={router} />
          </SlotProvider>
        </ServicesProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
