/**
 * 农场模块：home.panels 菜园（种植/收获，稀有作物消耗旅行带回的种子）+ 串门页（邻居列表、访问别人家菜园、偷菜）。
 * 只通过 FarmService 写入；钱包只读 HomeSnapshot.wallet，不自建余额。
 * 规则由服务端裁决：宠物在家守护时偷不到；每批作物全体访客共享可偷上限。
 */
import type { CropInfo, FarmActionResult, NeighborHomeSummary, NeighborHomeView, PatrolResult, StealResult } from "@/shared/contracts";
import { defineModule, slot } from "@/shared/modules/types";
import { FIXTURE_CROPS, fixtureNeighborHome, fixtureNeighbors, fixtureSteal } from "@/fixtures/farm";
import { fixtureFarmAct, fixturePatrol } from "@/fixtures/home";
import { delay } from "@/fixtures/world";
import { FarmPanel } from "./FarmPanel";
import { NeighborHomePage, NeighborsPage } from "./NeighborPages";

export default defineModule({
  id: "farm",
  routes: [
    { path: "neighbors", element: <NeighborsPage /> },
    { path: "homes/:homeId", element: <NeighborHomePage /> },
  ],
  services: {
    farm: {
      fixture: () => ({
        act: async (body, key) => delay(fixtureFarmAct(body, key)),
        crops: () => delay(FIXTURE_CROPS),
        neighbors: () => delay(fixtureNeighbors()),
        neighborHome: async (homeId) => delay(fixtureNeighborHome(homeId)),
        steal: async (body, key) => delay(fixtureSteal(body, key)),
        patrol: async () => delay(fixturePatrol()),
      }),
      live: ({ api }) => ({
        act: (body, key) => api.request<FarmActionResult>("/farm/actions", { method: "POST", body, idempotencyKey: key }),
        crops: () => api.request<CropInfo[]>("/farm/crops"),
        neighbors: () => api.request<NeighborHomeSummary[]>("/neighbors"),
        neighborHome: (homeId) => api.request<NeighborHomeView>(`/homes/${encodeURIComponent(homeId)}`),
        steal: (body, key) => api.request<StealResult>("/farm/steal", { method: "POST", body, idempotencyKey: key }),
        patrol: () => api.request<PatrolResult>("/farm/patrol", { method: "POST" }),
      }),
    },
  },
  slots: [slot("home.panels", "farm.panel", FarmPanel, 10)],
});
