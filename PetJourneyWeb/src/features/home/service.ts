import type { HomeSnapshot } from "@/shared/contracts";
import type { ServiceContext, WorldService } from "@/shared/services/types";
import { calibrate } from "@/shared/time/clock";
import { fixtureHomeSnapshot } from "@/fixtures/home";
import { delay } from "@/fixtures/world";

/** live：GET /api/v1/web/home（R0 真实本地读取，经旧存储适配；未登录返回 AUTH_REQUIRED）。 */
export function createLiveWorldService({ api }: ServiceContext): WorldService {
  return {
    async home(petId, signal) {
      const snapshot = await api.request<HomeSnapshot>("/home", { query: { pet_id: petId ?? undefined }, signal });
      calibrate(snapshot.server_time);
      return snapshot;
    },
  };
}

export function createFixtureWorldService(): WorldService {
  return { home: () => delay(fixtureHomeSnapshot()) };
}
