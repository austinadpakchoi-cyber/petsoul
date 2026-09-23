import { createContext, useContext, type ReactNode } from "react";
import { ApiError } from "@/shared/api/errors";
import type { FeatureModule } from "@/shared/modules/types";
import type { ServiceContext, ServiceKey, ServiceMap } from "./types";

const SERVICE_KEYS: ServiceKey[] = [
  "platform",
  "session",
  "households",
  "life",
  "world",
  "visits",
  "economy",
  "farm",
  "pets",
  "reception",
  "transport",
  "companionMedia",
  "food",
  "social",
  "communicator",
  "driving",
];

/** 未接入的服务：任何方法都返回 CAPABILITY_UNAVAILABLE，绝不回退到 fixture。 */
function unavailableService<K extends ServiceKey>(key: K, mode: string): ServiceMap[K] {
  return new Proxy({} as ServiceMap[K], {
    get(_target, prop) {
      if (prop === "fixtureScenarios" || prop === "fixtureVariants") return () => [];
      if (prop === "then") return undefined;
      return () => Promise.reject(ApiError.capability(`${key}.${String(prop)}`, `这项能力在 ${mode} 模式下尚未接入。`));
    },
  });
}

export function buildServices(modules: FeatureModule[], ctx: ServiceContext): ServiceMap {
  const chosen: Partial<Record<ServiceKey, { owner: string; build: (c: ServiceContext) => unknown }>> = {};
  for (const module of modules) {
    for (const [key, impls] of Object.entries(module.services ?? {}) as [ServiceKey, { fixture?: unknown; live?: unknown }][]) {
      const factory = impls?.[ctx.mode] as ((c: ServiceContext) => unknown) | undefined;
      if (!factory) continue;
      const existing = chosen[key];
      if (existing) throw new Error(`服务 ${key}（${ctx.mode}）被 ${existing.owner} 与 ${module.id} 重复提供`);
      chosen[key] = { owner: module.id, build: factory };
    }
  }
  const services = {} as Record<ServiceKey, unknown>;
  for (const key of SERVICE_KEYS) {
    services[key] = chosen[key] ? chosen[key]!.build(ctx) : unavailableService(key, ctx.mode);
  }
  return services as unknown as ServiceMap;
}

const ServicesContext = createContext<ServiceMap | null>(null);

export function ServicesProvider({ services, children }: { services: ServiceMap; children: ReactNode }) {
  return <ServicesContext.Provider value={services}>{children}</ServicesContext.Provider>;
}

export function useServices(): ServiceMap {
  const services = useContext(ServicesContext);
  if (!services) throw new Error("useServices 必须在 ServicesProvider 内使用");
  return services;
}
