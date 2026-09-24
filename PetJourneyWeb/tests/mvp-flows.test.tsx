import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import type { DestinationOption, HomeSnapshot, JourneySuggestion } from "@/shared/contracts";
import { createApiClient } from "@/shared/api/client";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { onboardingRoute, routeAfterSession } from "@/shared/session/onboarding";
import { fixtureNeighborHome, fixtureNeighbors, fixtureSteal } from "@/fixtures/farm";
import { fixtureHomeSnapshot } from "@/fixtures/home";
import { JourneyAtHome } from "@/features/journey/DepartureStation";

describe("MVP routes", () => {
  it("registers onboarding move-in, neighbors and neighbor homes (no cabin pages)", () => {
    const routes = buildRoutes(loadFeatureModules());
    const paths = routes.flatMap((layout) => (layout.children ?? []).map((c) => c.path).filter(Boolean));
    for (const p of ["onboarding/move-in", "neighbors", "homes/:homeId"]) expect(paths).toContain(p);
    expect(paths.some((p) => /cabin|舱|^transport\//.test(p ?? ""))).toBe(false);
  });
});

describe("onboarding routing", () => {
  it("maps every onboarding step to exactly one page", () => {
    expect(onboardingRoute({ step: "needs_companion", pet_id: null, home_id: null, reception_session_id: null, reception_skipped: false, home_activated_at: null, pet_origin: null })).toBe("/onboarding");
    expect(onboardingRoute({ step: "reception_optional", pet_id: "p", home_id: "h", reception_session_id: null, reception_skipped: false, home_activated_at: null, pet_origin: null })).toBe("/onboarding/reception");
    expect(onboardingRoute({ step: "ready_to_move_in", pet_id: "p", home_id: "h", reception_session_id: "r", reception_skipped: true, home_activated_at: null, pet_origin: null })).toBe("/onboarding/move-in");
    expect(onboardingRoute({ step: "active", pet_id: "p", home_id: "h", reception_session_id: null, reception_skipped: false, home_activated_at: "2026-09-22T00:00:00Z", pet_origin: "own_pet" })).toBe("/map");
    expect(routeAfterSession({ authenticated: false, user: null, csrf_required: false, expires_at: null, onboarding: null })).toBe("/welcome");
  });
});

describe("api client uploads", () => {
  it("sends FormData as multipart (no JSON content type) with CSRF and idempotency headers", async () => {
    document.cookie = "petsoul_csrf=csrf-token-1";
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 201, headers: { "Content-Type": "application/json" } }));
    const client = createApiClient("/api/v1/web", fetchImpl as unknown as typeof fetch);
    const form = new FormData();
    form.set("name", "团子");
    await client.request("/pets", { method: "POST", body: form, idempotencyKey: "pet-create:1" });
    const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(init.body).toBe(form);
    expect(headers["Content-Type"]).toBeUndefined();
    expect(headers["X-CSRF-Token"]).toBe("csrf-token-1");
    expect(headers["Idempotency-Key"]).toBe("pet-create:1");
  });
});

describe("farm visiting rules (fixture mirrors server)", () => {
  it("guarded homes cannot be stolen from; each visitor takes once; replay returns the same result", () => {
    const guarded = fixtureNeighbors().find((n) => n.guarded)!;
    const guardedPlot = fixtureNeighborHome(guarded.home_id).plots[0].plot;
    expect(() => fixtureSteal({ home_id: guarded.home_id, plot_id: guardedPlot.plot_id, cycle_id: guardedPlot.cycle_id! }, "k-guard")).toThrow(/守着菜园/);

    const open = fixtureNeighbors().find((n) => !n.guarded && n.stealable_plots > 0)!;
    const ripe = fixtureNeighborHome(open.home_id).plots.find((p) => p.plot.stage === "ripe")!.plot;
    const body = { home_id: open.home_id, plot_id: ripe.plot_id, cycle_id: ripe.cycle_id! };
    const first = fixtureSteal(body, "k-1");
    expect(fixtureSteal(body, "k-1")).toBe(first);
    expect(() => fixtureSteal(body, "k-2")).toThrow(/摘过/);
  });
});

function makeServices(overrides: Partial<ServiceMap>): ServiceMap {
  return new Proxy(overrides as ServiceMap, {
    get(target, prop: string) {
      if (prop in target) return target[prop as keyof ServiceMap];
      throw new Error(`unexpected service ${prop}`);
    },
  });
}

describe("journey at home (TA decides when to go)", () => {
  const home: HomeSnapshot = { ...fixtureHomeSnapshot(), presence: "at_home", journey: null, wallet: { currency: "travel_coin", balance: 20, updated_at: null } };
  const destinations: DestinationOption[] = [
    { destination_key: "harbour_cafe", title: "海边咖啡馆", city: "香港", summary: "示例", fee: 8, total_minutes: 32, modes: ["walk"], time_basis: "demo_fixture", wish_match: null, affordable: true },
    { destination_key: "macau_ferry", title: "坐船去澳门", city: "澳门", summary: "示例", fee: 40, total_minutes: 250, modes: ["ferry"], time_basis: "demo_fixture", wish_match: "你交代过：想去看海", affordable: false },
  ];

  it("offers only a suggestion — never a button that departs on TA's behalf", async () => {
    // 2026-09-23 用户决定：出发由 TA 自主，主人不替 TA 选目的地出发；旧“陪 TA 立即出发”入口已移除（接口本身未改）。
    const depart = vi.fn();
    let suggested: JourneySuggestion[] = [];
    const suggest = vi.fn(async (key: string) => {
      suggested = [{ suggestion_id: "s1", destination_key: key, title: "海边咖啡馆", status: "pending", considered_at: null, created_at: "2026-09-23T00:00:00Z", decided_at: null }];
      return suggested[0];
    });
    const services = makeServices({ transport: { destinations: async () => destinations, suggestions: async () => suggested, suggest, depart, journeyMap: vi.fn(), leg: vi.fn(), fixtureScenarios: () => [] } as unknown as ServiceMap["transport"] });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <ServicesProvider services={services}>
          <MemoryRouter>
            <JourneyAtHome home={home} last={null} />
          </MemoryRouter>
        </ServicesProvider>
      </QueryClientProvider>,
    );
    expect(screen.getByText(`${home.pet.name} 在家`)).toBeTruthy();
    expect(screen.getByText(/出不出门、去哪里、什么时候走，都由 TA 自己决定/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /悄悄告诉 TA 一个地方/ }));
    await screen.findByText("海边咖啡馆");
    expect(screen.getByText("你交代过：想去看海")).toBeTruthy();
    expect(screen.queryByText(/陪 TA 出发|确认现在出发/)).toBeNull();
    fireEvent.click(screen.getAllByRole("button", { name: "悄悄告诉 TA" })[0]);
    await waitFor(() => expect(suggest).toHaveBeenCalledWith("harbour_cafe", home.pet.pet_id));
    expect(await screen.findByText(/你悄悄说过的「海边咖啡馆」，TA 还在想/)).toBeTruthy();
    expect(depart).not.toHaveBeenCalled();
  });
});
