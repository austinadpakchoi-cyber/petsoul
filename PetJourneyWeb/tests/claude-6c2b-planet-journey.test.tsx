import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { JourneyLeg, JourneyMapSnapshot, PublicResident } from "@/shared/contracts";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { bubbleText, EncounterCard, PlanetMap, planetStations } from "@/features/pets/PlanetMap";
import { tripState } from "@/features/journey/JourneyPage";

vi.mock("@/shared/config/env", () => ({ env: { dataMode: "live", isDev: false, apiBase: "/api/v1/web" } }));

class FixedResizeObserver {
  constructor(private readonly callback: ResizeObserverCallback) {}
  observe() {
    this.callback([{ contentRect: { width: 390, height: 640 } } as ResizeObserverEntry], this as unknown as ResizeObserver);
  }
  disconnect() {}
  unobserve() {}
}

beforeEach(() => vi.stubGlobal("ResizeObserver", FixedResizeObserver));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function resident(overrides: Partial<PublicResident>): PublicResident {
  return {
    pet_id: "PJ-1", candidate_id: "c-1", name: "云朵", species: "dog", personality: "热情、走路会蹦", dream: "想当一次小小飞行员",
    origin: "adopted_original", source_note: null, residence: "星球居民驿站·中环", city: "香港", living_since: "2026-09-22T00:00:00Z",
    presence: "at_home", doing: "在驿站休息", place_name: null, recent_posts: [], ...overrides,
  } as PublicResident;
}

describe("planet map: residents live around their station", () => {
  it("groups by station, keeps every pin apart, and never places an unknown residence", () => {
    const { stations, unplaced } = planetStations([
      resident({ pet_id: "a", name: "阿绒" }),
      resident({ pet_id: "b", name: "豆豆" }),
      resident({ pet_id: "c", name: "海海", residence: "星球居民驿站·西贡海边" }),
      resident({ pet_id: "d", name: "不明", residence: "某个还没登记的驿站" }),
    ]);
    expect(stations.map((s) => [s.name, s.pins.length])).toEqual([["星球居民驿站·中环", 2], ["星球居民驿站·西贡海边", 1]]);
    expect(unplaced.map((r) => r.name)).toEqual(["不明"]);
    const [first, second] = stations[0].pins.map((pin) => pin.offset);
    expect(Math.hypot(first.x - second.x, first.y - second.y)).toBeGreaterThan(56);
    expect(stations[1].pins[0].offset).toEqual({ x: 0, y: 0 });
  });

  it("bubbles only say what the server says: current doing/place, or TA's own public post", () => {
    const walking = resident({ presence: "in_transit", doing: "在去码头的路上", city: "香港" });
    expect(bubbleText(walking, 0)).toBe("在去码头的路上 · 香港");
    const visiting = resident({ presence: "visiting", doing: "在海边咖啡馆", place_name: "海边咖啡馆" });
    expect(bubbleText(visiting, 0)).toBe("在海边咖啡馆 · 海边咖啡馆");
    const posting = resident({ recent_posts: [{ post_id: "p", text: "今天在码头看了很久的船。" } as PublicResident["recent_posts"][number]] });
    expect(bubbleText(posting, 0)).toBe("在驿站休息");
    expect(bubbleText(posting, 1)).toBe("“今天在码头看了很久的船。”");
  });

  it("tapping a resident opens an encounter, not an adoption page", () => {
    const onEncounter = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const services = { platform: { basemap: vi.fn() } } as unknown as ServiceMap;
    render(
      <QueryClientProvider client={client}><ServicesProvider services={services}><MemoryRouter>
        <PlanetMap residents={[resident({ pet_id: "a", name: "阿绒" }), resident({ pet_id: "b", name: "豆豆" })]} onEncounter={onEncounter} paused={false} realBasemap={false} />
      </MemoryRouter></ServicesProvider></QueryClientProvider>,
    );
    expect(screen.getAllByTestId("planet-pin")).toHaveLength(2);
    expect(screen.getByTestId("planet-bubble").textContent).toContain("阿绒");
    fireEvent.click(screen.getByRole("button", { name: /豆豆，在驿站休息/ }));
    expect(onEncounter).toHaveBeenCalledWith(expect.objectContaining({ pet_id: "b" }));
    expect(services.platform.basemap).not.toHaveBeenCalled();
  });

  it("the encounter card shows the moment and links to the public journal without adopting", () => {
    render(<MemoryRouter><EncounterCard resident={resident({ pet_id: "PJ-9", recent_posts: [{ post_id: "p", text: "今天在码头看船。" } as PublicResident["recent_posts"][number]] })} onClose={vi.fn()} /></MemoryRouter>);
    const card = screen.getByTestId("encounter-card");
    expect(card.textContent).toContain("在驿站休息");
    expect(card.textContent).toContain("想当一次小小飞行员");
    expect(card.textContent).toContain("今天在码头看船。");
    expect(screen.getByRole("link", { name: /看看 TA 的公开手账/ }).getAttribute("href")).toBe("/world/residents/PJ-9");
    expect(card.textContent).not.toMatch(/领养|迎接/);
  });
});

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
    const state = tripState(snapshot, Date.parse("2026-09-24T02:00:00Z"));
    expect(state.state).toBe("在店里");
    expect(state.place).toBe("海边咖啡馆");
    expect(state.next?.destination.name).toBe("家");
    expect(state.day).toBe(2);
  });
});
