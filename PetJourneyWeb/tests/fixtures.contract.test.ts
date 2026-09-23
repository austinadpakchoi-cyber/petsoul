/**
 * fixture ↔ 契约一致性：
 * 1) 编译期：fixture 以 generated.ts 的类型书写（typecheck 保证字段/枚举一致）；
 * 2) 运行期：把 fixture 导出到 .runtime/contract-examples/，由 `npm run contract:check`
 *    （scripts/gen_web_contract.py --check）用后端 Pydantic 模型逐条校验。
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { fixtureCandidates } from "@/fixtures/adoption";
import { fixtureRecommend } from "@/fixtures/food";
import { fixtureHomeSnapshot } from "@/fixtures/home";
import { fixtureMediaSessions } from "@/fixtures/media";
import { scriptedSession } from "@/fixtures/reception";
import { fixtureCollection, fixtureFeed, fixturePublicProfile, fixtureThread } from "@/fixtures/social";
import { FIXTURE_SCENARIOS } from "@/fixtures/transport";
import { fixtureVisit } from "@/fixtures/venue";

const here = dirname(fileURLToPath(import.meta.url));
const outDir = resolve(here, "..", ".runtime", "contract-examples");

describe("fixture export for contract validation", () => {
  it("exports every fixture domain as typed examples", () => {
    const now = Date.now();
    const scenario = FIXTURE_SCENARIOS.map((s) => ({ name: `transport.${s.id}`, type: "JourneyMapSnapshot", value: s.build(now) }));
    const train = FIXTURE_SCENARIOS.find((s) => s.id === "train")!.build(now);
    const entries = [
      { name: "home.snapshot", type: "HomeSnapshot", value: fixtureHomeSnapshot() },
      ...scenario,
      ...Object.values(fixtureMediaSessions()).map((s) => ({ name: `media.${s.session_id}`, type: "CompanionSession", value: s })),
      { name: "food.pet.light", type: "FoodRecommendationList", value: fixtureRecommend({ mode: "pet_virtual_explore", pet_id: "fx-pet-001", pet_context: train.arrival_context, max_results: 3 }, "light") },
      { name: "food.owner.rich", type: "FoodRecommendationList", value: fixtureRecommend({ mode: "owner_real_dining", pet_id: "fx-pet-001", owner_context: { plan_date: "2026-10-03", meal_time_local: "12:30", timezone: "Asia/Hong_Kong", city: "香港", area: null }, max_results: 3 }, "rich") },
      { name: "reception.own_pet", type: "ReceptionSession", value: scriptedSession("own_pet", "fx-pet-001", "示例伙伴") },
      { name: "reception.adopted", type: "ReceptionSession", value: scriptedSession("adopted", "fx-adopt-pet", "示例伙伴") },
      { name: "venue.visit", type: "Visit", value: fixtureVisit("fx-visit-001") },
      { name: "social.feed", type: "PostPage", value: fixtureFeed() },
      { name: "social.profile", type: "PetPublicProfile", value: fixturePublicProfile("fx-pet-001") },
      { name: "communicator.thread", type: "MessageThread", value: fixtureThread("fx-pet-001") },
      ...fixtureCandidates().map((c) => ({ name: `adoption.${c.candidate_id}`, type: "AdoptionCandidate", value: c })),
      ...fixtureCollection().map((c) => ({ name: `collection.${c.item_id}`, type: "CollectionItem", value: c })),
    ];
    mkdirSync(outDir, { recursive: true });
    writeFileSync(resolve(outDir, "fixtures.json"), JSON.stringify(entries, null, 1), "utf-8");
    expect(entries.length).toBeGreaterThan(20);
    for (const e of entries) expect(e.value).toBeTruthy();
  });
});
