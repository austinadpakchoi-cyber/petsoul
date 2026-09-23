/**
 * 旅途模块：/journey 地图宿主页（插槽：地图叠加层、底部面板、常驻播放条、卡片区）与到访服务。
 * 车辆与班次来自 transport 模块；音符/电视与播放器来自 companion_media 模块；本模块不复制它们。
 * 深链接：/journey?sheet=leg:<leg_id> 或 ?sheet=media:<session_id> 定位同一张地图并打开对应面板。
 */
import type { JourneyMapSnapshot, Visit } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { defineModule, slot } from "@/shared/modules/types";
import { fixtureVisit, fixtureVisitAct } from "@/fixtures/venue";
import { delay } from "@/fixtures/world";
import { JourneyPage } from "./JourneyPage";
import { GuideBookPage, GuideDetailPage } from "./GuideBookPage";
import { JourneyStatusPanel } from "./JourneyStatusPanel";

export default defineModule({
  id: "journey",
  routes: [
    { path: "journey", element: <JourneyPage /> },
    { path: "guides", element: <GuideBookPage /> },
    { path: "guides/:guideId", element: <GuideDetailPage /> },
  ],
  services: {
    visits: {
      fixture: () => ({
        visit: async (id) => delay(fixtureVisit(id)),
        act: async (id, body, key) => delay(fixtureVisitAct(id, body, key)),
        choose: async () => {
          throw ApiError.capability("journey.visit", "演示模式不改行程；live 模式下到店前可以改去推荐的分店。");
        },
      }),
      live: ({ api }) => ({
        visit: (id) => api.request<Visit>(`/visits/${encodeURIComponent(id)}`),
        act: (id, body, key) => api.request<Visit>(`/visits/${encodeURIComponent(id)}/actions`, { method: "POST", body, idempotencyKey: key }),
        choose: (id, body, key) => api.request<JourneyMapSnapshot>(`/visits/${encodeURIComponent(id)}/choice`, { method: "POST", body, idempotencyKey: key }),
      }),
    },
  },
  slots: [slot("home.panels", "journey.status", JourneyStatusPanel, 5)],
});
