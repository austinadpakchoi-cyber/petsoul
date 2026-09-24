/**
 * 家园模块：小窝（/home，地图下面的二级页）、WorldService（HomeSnapshot）。
 * 按方案 2.2，二级页全屏、不显示底部标签栏，所以挂 bareRoutes；登录与入住守卫沿用新版一级页共用的 WorldGate
 * （与主布局同一套规则：live 下未登录去欢迎页，入住未完成回对应的入住步骤）。
 * 入住欢迎通过 home.welcome 插槽显示；home.panels 只渲染白名单里的卡片（见 HomePage.tsx）。
 */
import { defineModule, slot } from "@/shared/modules/types";
import { WorldGate } from "@/features/world_map/WorldGate";
import { HomePage } from "./HomePage";
import { HomeWelcomeBanner } from "./HomeWelcomeBanner";
import { createFixtureWorldService, createLiveWorldService } from "./service";

export default defineModule({
  id: "home",
  bareRoutes: [
    {
      path: "home",
      element: (
        <WorldGate>
          <HomePage />
        </WorldGate>
      ),
    },
  ],
  services: { world: { fixture: createFixtureWorldService, live: createLiveWorldService } },
  slots: [slot("home.welcome", "home.welcome-banner", HomeWelcomeBanner, 10)],
});
