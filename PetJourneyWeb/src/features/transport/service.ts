import type { DestinationOption, JourneyLeg, JourneyMapSnapshot, JourneySuggestion, TravelGuide, TripPlanPreview } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import type { ServiceContext, TransportService } from "@/shared/services/types";
import { calibrate } from "@/shared/time/clock";
import { DEFAULT_SCENARIO, FIXTURE_SCENARIOS } from "@/fixtures/transport";
import { delay } from "@/fixtures/world";

export function createLiveTransportService({ api }: ServiceContext): TransportService {
  return {
    async journeyMap(petId) {
      const snapshot = await api.request<JourneyMapSnapshot>("/journey/map", { query: { pet_id: petId } });
      calibrate(snapshot.server_time);
      return snapshot;
    },
    leg: (legId) => api.request<JourneyLeg>(`/journey/legs/${encodeURIComponent(legId)}`),
    destinations: (petId, signal) => api.request<DestinationOption[]>("/journey/destinations", { query: { pet_id: petId }, signal }),
    plan: (destinationKey, petId, signal) => api.request<TripPlanPreview>("/journey/plan", { query: { destination_key: destinationKey, pet_id: petId }, signal }),
    suggestions: (petId, signal) => api.request<JourneySuggestion[]>("/journey/suggestions", { query: { pet_id: petId }, signal }),
    guides: (petId, signal) => api.request<TravelGuide[]>("/guides", { query: { pet_id: petId }, signal }),
    guide: (guideId, signal) => api.request<TravelGuide>(`/guides/${encodeURIComponent(guideId)}`, { signal }),
    suggest: (destinationKey, petId) => api.request<JourneySuggestion>("/journey/suggest", { method: "POST", query: { pet_id: petId }, body: { destination_key: destinationKey } }),
    async depart(destinationKey, key, petId) {
      const snapshot = await api.request<JourneyMapSnapshot>("/journey/depart", { method: "POST", query: { pet_id: petId }, body: { destination_key: destinationKey }, idempotencyKey: key });
      calibrate(snapshot.server_time);
      return snapshot;
    },
    fixtureScenarios: () => [],
  };
}

const FIXTURE_DESTINATIONS: DestinationOption[] = [
  { destination_key: "harbour_cafe", title: "海边咖啡馆", city: "香港", summary: "走几分钟去示例咖啡馆坐坐（演示）。", fee: 8, total_minutes: 32, modes: ["walk"], time_basis: "demo_fixture", wish_match: null, affordable: true },
  { destination_key: "macau_ferry", title: "坐船去澳门", city: "澳门", summary: "打车到码头，坐海獭轮渡看海（演示）。", fee: 40, total_minutes: 250, modes: ["taxi", "ferry", "walk"], time_basis: "demo_fixture", wish_match: "你交代过：想带它去看海（演示）", affordable: true },
  { destination_key: "tokyo_flight", title: "飞去东京", city: "东京", summary: "坐喵航飞东京，再换爪爪铁路进城（演示航线）。", fee: 120, total_minutes: 876, modes: ["taxi", "flight", "train", "walk"], time_basis: "demo_fixture", wish_match: null, affordable: true },
];

export function createFixtureTransportService(): TransportService {
  const pick = (id?: string) => FIXTURE_SCENARIOS.find((s) => s.id === id) ?? FIXTURE_SCENARIOS.find((s) => s.id === DEFAULT_SCENARIO)!;
  return {
    journeyMap: (_petId, options) => delay(pick(options?.fixtureScenario).build(Date.now())),
    async leg(legId, options) {
      const snapshot = pick(options?.fixtureScenario).build(Date.now());
      const found = snapshot.legs.find((l) => l.leg_id === legId);
      if (!found) throw new Error(`fixture leg ${legId} not found`);
      return delay(found);
    },
    destinations: () => delay(FIXTURE_DESTINATIONS),
    plan: async () => { throw ApiError.capability("transport.plan", "演示旅程没有可验证的真实班次计划。"); },
    suggestions: () => delay([]),
    guides: () => delay([]),
    guide: async () => { throw ApiError.capability("journey.guide", "演示行程没有真实攻略手账。"); },
    suggest: async () => { throw ApiError.capability("transport.suggest", "演示模式不向真实宠物提交出门建议。"); },
    // 演示：出发即切到对应演示场景（不扣真实旅费，不创建真实旅程）。
    depart: (destinationKey) => delay(pick(destinationKey === "tokyo_flight" ? "flight" : destinationKey === "macau_ferry" ? "ferry" : undefined).build(Date.now())),
    fixtureScenarios: () => FIXTURE_SCENARIOS.map(({ id, label }) => ({ id, label })),
  };
}
