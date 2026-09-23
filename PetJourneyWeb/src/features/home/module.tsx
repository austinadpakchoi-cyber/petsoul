/**
 * 家园模块：首页“共同的家”、WorldService（HomeSnapshot）。
 * 农场、旅途状态等通过 home.panels 插槽接入；入住欢迎通过 home.welcome 插槽显示。
 */
import { defineModule, slot } from "@/shared/modules/types";
import { HomePage } from "./HomePage";
import { HomeWelcomeBanner } from "./HomeWelcomeBanner";
import { createFixtureWorldService, createLiveWorldService } from "./service";

export default defineModule({
  id: "home",
  routes: [{ path: "home", element: <HomePage /> }],
  services: { world: { fixture: createFixtureWorldService, live: createLiveWorldService } },
  slots: [slot("home.welcome", "home.welcome-banner", HomeWelcomeBanner, 10)],
});
