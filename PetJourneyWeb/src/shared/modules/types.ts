import type { ComponentType } from "react";
import type { RouteObject } from "react-router";
import type { ServiceContributions } from "@/shared/services/types";
import type { SlotName, SlotPropsMap } from "@/shared/slots/names";

/**
 * 功能模块的固定导出形态。每个 src/features/<id>/module.ts(x) 默认导出一个 FeatureModule，
 * 由 app/modules.ts 通过 import.meta.glob 自动发现——模块作者不需要修改 app/ 或 shared/。
 *
 * 限制（刻意）：
 * - 不能新增底部主 Tab（家/旅途/星球圈/通讯固定在 app/TabBar）；
 * - 不能注册“舱室/交通场景”独立页面；一起听看只能是 /journey 上的面板；
 * - 路由路径必须登记在 docs/contracts/MODULE-MAP.md，冲突由 app/modules.ts 启动时检测。
 */
export interface SlotContribution<N extends SlotName = SlotName> {
  slot: N;
  id: string;
  order?: number;
  Component: ComponentType<SlotPropsMap[N]>;
}

export interface FeatureModule {
  id: string;
  /** 带底部导航的页面（RootLayout 子路由）。 */
  routes?: RouteObject[];
  /** 不带底部导航的全屏流程（欢迎、注册、入住接待）。 */
  bareRoutes?: RouteObject[];
  slots?: SlotContribution[];
  services?: ServiceContributions;
}

export function defineModule(module: FeatureModule): FeatureModule {
  return module;
}

/** 类型安全地声明插槽贡献。 */
export function slot<N extends SlotName>(
  name: N,
  id: string,
  Component: ComponentType<SlotPropsMap[N]>,
  order = 100,
): SlotContribution {
  return { slot: name, id, order, Component: Component as ComponentType<SlotPropsMap[SlotName]> };
}
