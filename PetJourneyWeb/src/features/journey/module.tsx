/**
 * 旅途模块：/journey 地图宿主页（插槽：地图叠加层、底部面板、常驻播放条、卡片区）与到访服务。
 * 车辆与班次来自 transport 模块；音符/电视与播放器来自 companion_media 模块；本模块不复制它们。
 * 深链接：/journey?sheet=leg:<leg_id> 或 ?sheet=media:<session_id> 定位同一张地图并打开对应面板。
 */
import type { JourneyMapSnapshot, Visit } from "@/shared/contracts";
import type { TravelWish } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { defineModule, slot } from "@/shared/modules/types";
import { fixtureVisit, fixtureVisitAct } from "@/fixtures/venue";
import { delay } from "@/fixtures/world";
import { JourneyPage } from "./JourneyPage";
import { GuideBookPage, GuideDetailPage } from "./GuideBookPage";
import { PlanPage, WishPage } from "./travelPlan/PlanPage";
import { JourneyStatusPanel } from "./JourneyStatusPanel";

export default defineModule({
  id: "journey",
  routes: [
    { path: "journey", element: <JourneyPage /> },
    { path: "guides", element: <GuideBookPage /> },
    { path: "guides/:guideId", element: <GuideDetailPage /> },
    { path: "guides/wish", element: <WishPage /> },
    { path: "guides/plan/:planId", element: <PlanPage /> },
  ],
  services: {
    visits: {
      fixture: () => ({
        visit: async (id) => delay(fixtureVisit(id)),
        act: async (id, body, key) => delay(fixtureVisitAct(id, body, key)),
        choose: async () => {
          throw ApiError.capability("journey.visit", "演示模式不改行程；live 模式下到店前可以改去推荐的分店。");
        },
        // TRV-06：演示的当前活动心愿（按需加载演示数据，主包里没有它）。
        travelWish: async () => delay((await import("./travelPlan/fixture")).DEMO_CURRENT_WISH),
      }),
      live: ({ api }) => ({
        visit: (id) => api.request<Visit>(`/visits/${encodeURIComponent(id)}`),
        act: (id, body, key) => api.request<Visit>(`/visits/${encodeURIComponent(id)}/actions`, { method: "POST", body, idempotencyKey: key }),
        choose: (id, body, key) => api.request<JourneyMapSnapshot>(`/visits/${encodeURIComponent(id)}/choice`, { method: "POST", body, idempotencyKey: key }),
        // TRV-06：GET /travel/wish（合同 §23.4），按当前宠物读；没有活动心愿时返回 200 + null（I 已定）；petId 为 null 的含义 I 未定，./travelPlan/data 在 live 下只在有当前宠物时才读、不传 null。
        travelWish: (petId, signal) => api.request<TravelWish | null>("/travel/wish", { query: { pet_id: petId }, signal }),
      }),
    },
  },
  slots: [slot("home.panels", "journey.status", JourneyStatusPanel, 5)],
});
