import { createContext, useContext, type ReactNode } from "react";
import type { SlotContribution } from "@/shared/modules/types";
import type { SlotName, SlotPropsMap } from "./names";
import { ErrorBoundary } from "@/shared/ui/ErrorBoundary";

type SlotRegistry = Map<SlotName, SlotContribution[]>;

const SlotContext = createContext<SlotRegistry>(new Map());

export function buildSlotRegistry(contributions: SlotContribution[]): SlotRegistry {
  const registry: SlotRegistry = new Map();
  for (const item of contributions) {
    const list = registry.get(item.slot) ?? [];
    if (list.some((existing) => existing.id === item.id)) {
      throw new Error(`插槽 ${item.slot} 中贡献 id 重复：${item.id}`);
    }
    list.push(item);
    registry.set(item.slot, list);
  }
  for (const list of registry.values()) list.sort((a, b) => (a.order ?? 100) - (b.order ?? 100));
  return registry;
}

export function SlotProvider({ registry, children }: { registry: SlotRegistry; children: ReactNode }) {
  return <SlotContext.Provider value={registry}>{children}</SlotContext.Provider>;
}

export function useSlotContributions(name: SlotName): SlotContribution[] {
  return useContext(SlotContext).get(name) ?? [];
}

/** 渲染某插槽的全部贡献；每个贡献有独立错误边界，一个模块崩溃不拖垮宿主页面。 */
export function Slot<N extends SlotName>({ name, props, fallback }: { name: N; props: SlotPropsMap[N]; fallback?: ReactNode }) {
  const items = useSlotContributions(name);
  if (items.length === 0) return <>{fallback ?? null}</>;
  return (
    <>
      {items.map(({ id, Component }) => {
        const Typed = Component as unknown as (p: SlotPropsMap[N]) => ReactNode;
        return (
          <ErrorBoundary key={id} scope={`${name}:${id}`} compact>
            <Typed {...props} />
          </ErrorBoundary>
        );
      })}
    </>
  );
}
