import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import type { JourneyMapSnapshot } from "@/shared/contracts";
import { defineModule, slot } from "@/shared/modules/types";
import { apiClient } from "@/shared/api/client";
import { buildServices } from "@/shared/services/registry";
import { buildSlotRegistry, Slot, SlotProvider } from "@/shared/slots/Slot";
import type { JourneyOverlayProps } from "@/shared/slots/names";

function collectPaths(routes: ReturnType<typeof buildRoutes>): string[] {
  const out: string[] = [];
  for (const layout of routes) for (const child of layout.children ?? []) if (child.path) out.push(child.path);
  return out;
}

describe("module registry", () => {
  const modules = loadFeatureModules();

  it("auto-discovers every feature module without editing app/", () => {
    const ids = modules.map((m) => m.id);
    for (const id of ["platform", "home", "farm", "journey", "transport", "companion_media", "venue", "food_discovery", "reception", "identity", "pets", "social", "communicator", "collection"]) {
      expect(ids).toContain(id);
    }
  });

  it("registers the frozen R0 routes and no cabin/transport-scene page", () => {
    const paths = collectPaths(buildRoutes(modules));
    for (const p of ["home", "journey", "circle", "communicator", "journey/food", "journey/food/:recommendationId", "visits/:visitId", "pets/:petId", "posts/:postId", "collection", "market", "settings", "welcome", "register", "login", "onboarding", "adopt", "onboarding/reception", "onboarding/notes"]) {
      expect(paths).toContain(p);
    }
    expect(paths.some((p) => /cabin|舱/.test(p))).toBe(false);
  });

  it("rejects duplicate and forbidden routes", () => {
    const dup = defineModule({ id: "dup", routes: [{ path: "home", element: null }] });
    expect(() => buildRoutes([...modules, dup])).toThrow(/路由冲突/);
    const cabin = defineModule({ id: "cabin", routes: [{ path: "cabin/:id", element: null }] });
    expect(() => buildRoutes([...modules, cabin])).toThrow(/不允许的路由/);
  });

  it("two independent modules contribute to the same map overlay slot", () => {
    const registry = buildSlotRegistry(modules.flatMap((m) => m.slots ?? []));
    const overlayIds = (registry.get("journey.map.overlay") ?? []).map((c) => c.id);
    expect(overlayIds).toEqual(["transport.vehicle", "companion_media.badge"]);
    const sheetIds = (registry.get("journey.sheet") ?? []).map((c) => c.id);
    expect(sheetIds).toEqual(["transport.leg", "companion_media.sheet"]);
  });

  it("a brand-new module plugs in through the fixed export only", () => {
    function Probe({ snapshot }: JourneyOverlayProps) {
      return <span>probe:{snapshot.journey_id}</span>;
    }
    const extra = defineModule({ id: "probe", slots: [slot("journey.cards", "probe.card", Probe)] });
    const registry = buildSlotRegistry([...modules, extra].flatMap((m) => m.slots ?? []));
    const snapshot = { journey_id: "j-test", legs: [], activities: [], activity_entries: [] } as unknown as JourneyMapSnapshot;
    render(
      <SlotProvider registry={registry}>
        <Slot name="journey.cards" props={{ snapshot, nowMs: 0, openSheet: () => undefined }} />
      </SlotProvider>,
    );
    expect(screen.getByText("probe:j-test")).toBeTruthy();
  });

  it("live mode never falls back to fixtures for services without a live implementation", async () => {
    const onlyFixture = defineModule({ id: "only-fixture", services: {} });
    const services = buildServices([onlyFixture], { mode: "live", api: apiClient });
    await expect(services.food.recommendation("x")).rejects.toMatchObject({ code: "CAPABILITY_UNAVAILABLE" });
  });

  it("refuses two modules providing the same service", () => {
    const a = defineModule({ id: "a", services: { economy: { fixture: () => ({ collection: async () => [] }) as never } } });
    const b = defineModule({ id: "b", services: { economy: { fixture: () => ({ collection: async () => [] }) as never } } });
    expect(() => buildServices([a, b], { mode: "fixture", api: apiClient })).toThrow(/重复提供/);
  });
});
