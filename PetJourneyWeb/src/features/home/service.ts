import type { HomeSnapshot, WorldState } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import type { ServiceContext, WorldService } from "@/shared/services/types";
import { calibrate } from "@/shared/time/clock";
import { fixtureHomeSnapshot } from "@/fixtures/home";
import { delay } from "@/fixtures/world";

/** live：GET /api/v1/web/home（R0 真实本地读取，经旧存储适配；未登录返回 AUTH_REQUIRED）；GET /world/state（W1 统一世界状态，纯读）。 */
export function createLiveWorldService({ api }: ServiceContext): WorldService {
  return {
    async home(petId, signal) {
      const snapshot = await api.request<HomeSnapshot>("/home", { query: { pet_id: petId ?? undefined }, signal });
      calibrate(snapshot.server_time);
      return snapshot;
    },
    async state(petId, signal) {
      // 给了宠物 id 就带上 pet_id（跨多个家时由它指明是哪个家）；没给就只按 household 读，同一个家由后端自己定位。
      const state = await api.request<WorldState>("/world/state", { query: { scope: "household", pet_id: petId }, signal });
      calibrate(state.server_time);
      return state;
    },
  };
}

export function createFixtureWorldService(): WorldService {
  return {
    home: () => delay(fixtureHomeSnapshot()),
    // 演示模式的地图用演示剧本（features/world_map/demoScript），不编一份“世界状态”冒充后端。
    state: async (_petId, _signal) => {
      throw ApiError.capability("world.state", "演示模式没有实时世界状态。");
    },
  };
}
