import { describe, expect, it, vi } from "vitest";
import type { JourneyLeg, JourneyMapSnapshot } from "@/shared/contracts";
import { tripState } from "@/features/journey/JourneyPage";

vi.mock("@/shared/config/env", () => ({ env: { dataMode: "live", isDev: false, apiBase: "/api/v1/web" } }));

// 2026-09-24（claude-6c2b 星球访客页分身）：原来这里的四条“planet map”用例钉的是旧的示意地图——
// 按驿站名配的前端坐标表（planetStations）、地图气泡（bubbleText）、地图上的居民按钮（PlanetMap）和相遇卡（EncounterCard）。
// 公开接口没有居民坐标、前端不许自己写坐标，示意地图连同坐标表已删；新访客页的用例在 tests/claude-6c2b-planet.test.tsx。
// 下面旅途状态的两条与星球无关，原样保留。
function leg(overrides: Partial<JourneyLeg>): JourneyLeg {
  return {
    leg_id: "l1", journey_id: "j1", sequence: 1, kind: "main", mode: "walk", role: "walker", world_service: null,
    origin: { node_id: "o", name: "家", kind: "place", timezone: "Asia/Hong_Kong", lat: 22.28, lng: 114.15, verified: true },
    destination: { node_id: "d", name: "海边咖啡馆", kind: "place", timezone: "Asia/Hong_Kong", lat: 22.29, lng: 114.16, verified: true },
    times: { origin_timezone: "Asia/Hong_Kong", destination_timezone: "Asia/Hong_Kong", planned_departure_utc: "2026-09-23T01:00:00Z", planned_arrival_utc: "2026-09-23T01:30:00Z", estimated_departure_utc: null, estimated_arrival_utc: null, actual_departure_utc: null, actual_arrival_utc: null },
    time_basis: "routed_estimate", freshness: "fresh", position_basis: "simulated_route", phase: "in_transit", itinerary_version: 1, route: [], reference: null, rescheduled_reason: null,
    ...overrides,
  } as JourneyLeg;
}

describe("journey state is derived from the itinerary, not invented", () => {
  const base = { journey_id: "j1", pet_id: "p1", itinerary_version: 1, lifecycle: "active", destination_title: "海边咖啡馆", current_visit_id: null, planned_visit_id: "v1", server_time: "2026-09-23T01:10:00Z", current_leg_id: "l1", vehicle: null, activities: [], activity_entries: [], arrival_context: null, data_origin: "live" } as unknown as JourneyMapSnapshot;

  it("walking toward the café: on the road, next stop is the café, day one", () => {
    const snapshot = { ...base, legs: [leg({}), leg({ leg_id: "l2", sequence: 2, phase: "scheduled", origin: leg({}).destination, destination: leg({}).origin })] };
    const state = tripState(snapshot, Date.parse("2026-09-23T01:10:00Z"));
    expect(state.state).toBe("在路上");
    expect(state.next?.destination.name).toBe("海边咖啡馆");
    expect(state.day).toBe(1);
  });

  it("inside the café: in the shop, and the next stop is the way home", () => {
    const snapshot = { ...base, current_visit_id: "v1", legs: [leg({ phase: "arrived" }), leg({ leg_id: "l2", sequence: 2, phase: "scheduled", origin: leg({}).destination, destination: leg({}).origin })] };
    // 2026-09-24 第六批（驾校·页面分身，主窗口授权）：是不是店改由这次到访的场景模板决定（venue/visitKind），
    // 快照本身没有模板；这里是咖啡馆，按页面的做法把“门店”传进来，断言不变。不传时的说法见 tests/claude-6c2b-journey-fixes.test.tsx。
    const state = tripState(snapshot, Date.parse("2026-09-24T02:00:00Z"), "shop");
    expect(state.state).toBe("在店里");
    expect(state.place).toBe("海边咖啡馆");
    expect(state.next?.destination.name).toBe("家");
    expect(state.day).toBe(2);
  });
});
