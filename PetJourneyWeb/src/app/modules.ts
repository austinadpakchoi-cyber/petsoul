/**
 * 模块自动发现：src/features/<id>/module.ts(x) 的默认导出即接入。
 * 新模块不需要修改本文件、router 或任何 app/ 代码。
 */
import type { FeatureModule } from "@/shared/modules/types";
import platformModule from "./platform.module";

const discovered = import.meta.glob<{ default: FeatureModule }>("../features/*/module.{ts,tsx}", { eager: true });

export function loadFeatureModules(): FeatureModule[] {
  const modules = Object.entries(discovered)
    .map(([path, mod]) => {
      if (!mod.default || typeof mod.default.id !== "string") {
        throw new Error(`${path} 没有默认导出 FeatureModule`);
      }
      return mod.default;
    })
    .sort((a, b) => a.id.localeCompare(b.id));
  const ids = new Set<string>();
  for (const module of modules) {
    if (ids.has(module.id)) throw new Error(`模块 id 重复：${module.id}`);
    ids.add(module.id);
  }
  return [platformModule, ...modules];
}
