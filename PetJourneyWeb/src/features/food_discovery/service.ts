import type { FoodFeedbackInput, FoodPreference, FoodRecommendation, FoodRecommendationList } from "@/shared/contracts";
import type { FoodDiscoveryService, ServiceContext } from "@/shared/services/types";
import { FOOD_VARIANTS, fixturePreference, fixtureRecommend, fixtureRecommendation } from "@/fixtures/food";
import { delay } from "@/fixtures/world";

export function createLiveFoodService({ api }: ServiceContext): FoodDiscoveryService {
  return {
    preference: (petId, subject) => api.request<FoodPreference>(`/food/preferences/${subject}`, { query: { pet_id: petId } }),
    recommend: (body) => api.request<FoodRecommendationList>("/food/recommendations", { method: "POST", body }),
    recommendation: (id) => api.request<FoodRecommendation>(`/food/recommendations/${encodeURIComponent(id)}`),
    feedback: (body, key) => api.request<FoodFeedbackInput>("/food/feedback", { method: "POST", body, idempotencyKey: key }),
    savePreference: (subject, preference, key) =>
      api.request<FoodPreference>(`/food/preferences/${subject}`, { method: "PUT", body: preference, idempotencyKey: key }),
    fixtureVariants: () => [],
  };
}

export function createFixtureFoodService(): FoodDiscoveryService {
  return {
    preference: (petId, subject, variant) => delay(fixturePreference(petId, subject, variant)),
    recommend: async (body, variant) => delay(fixtureRecommend(body, variant)),
    recommendation: async (id) => delay(fixtureRecommendation(id)),
    feedback: (body) => delay({ ...body, feedback_id: `fx-fb-${Date.now()}` }),
    savePreference: (_subject, preference) => delay({ ...preference, version: preference.version + 1, source: "fixture" as const, updated_at: new Date().toISOString() }),
    fixtureVariants: () => FOOD_VARIANTS.map((v) => ({ ...v })),
  };
}
