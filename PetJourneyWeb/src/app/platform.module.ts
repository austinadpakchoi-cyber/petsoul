import type { BasemapView, WebMeta } from "@/shared/contracts";
import { defineModule } from "@/shared/modules/types";
import { calibrate } from "@/shared/time/clock";

/**
 * 平台核心服务（框架维护，不属于任何业务模块）。
 * live：真实读取 GET /api/v1/web/meta（R0 的真实本地 Web→FastAPI 链路之一）；旅途地图底图 GET /api/v1/web/map/basemap。
 * fixture：本地生成的演示元信息，明确标注 fixture，不访问网络。
 */
export default defineModule({
  id: "platform",
  services: {
    platform: {
      live: ({ api }) => ({
        async meta() {
          const meta = await api.request<WebMeta>("/meta");
          calibrate(meta.server_time);
          return meta;
        },
        basemap(request) {
          return api.request<BasemapView>("/map/basemap", { query: { ...request } });
        },
      }),
      fixture: () => ({
        async meta() {
          return {
            api_prefix: "/api/v1/web",
            contract_version: "0.1.0",
            server_time: new Date().toISOString(),
            backend_version: "fixture",
            data_origin: "fixture",
            auth_methods_available: [],
            capabilities: [],
            applied_migrations: [],
          } satisfies WebMeta;
        },
        async basemap() {
          // 演示模式不请求真实底图：地图保持明确标注的示意图。
          return { available: false, reason: "not_configured", provider: null, image_url: null, center: null, zoom: null, width: null, height: null, attribution: null, expires_at: null } satisfies BasemapView;
        },
      }),
    },
  },
});
